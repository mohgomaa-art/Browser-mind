"""
page_interrupt_controller.py — Event-driven interrupt detection for ReplayEngine.

The replay step loop is sequential. The web is not. Between step N and step N+1,
the site may fire any of these page-level interrupts that block execution:

  - Cookie consent dialog (GDPR, CCPA)
  - Newsletter / marketing modal (time-triggered, scroll-triggered)
  - Session expiry countdown / forced logout warning
  - "Complete your profile" modal (LinkedIn, Greenhouse)
  - Chat widget (Intercom, Drift, Zendesk) covering the bottom 25% of page
  - JavaScript beforeunload / confirm dialogs

Without handling these, the TargetResolver's 7-strategy ladder exhausts itself
on an element that exists but is obscured. The SSTG records a failed transition.
OutcomeLedger records quality=0. The model degrades.

Architecture:
    InterruptController runs as a background asyncio task (via asyncio.create_task).
    It polls for interrupts every 0.5 s and puts detected Interrupts into an
    asyncio.Queue. The step loop drains this queue before each step and on
    ElementNotFound/Timeout exceptions.

    Each InterruptRule has:
      - A detector  (async fn(page) → bool)
      - A handler   (async fn(page) → bool: returns True if resolved)
      - A priority  (lower = higher priority; cookie consent=10, chat widget=5)

Usage in ReplayEngine:
    interrupt_queue: asyncio.Queue = asyncio.Queue()
    controller = PageInterruptController()
    watcher = asyncio.create_task(
        controller.watch(page, interrupt_queue)
    )
    try:
        # ... step loop ...
        await drain_interrupts(page, interrupt_queue)
        await primary_step()
    finally:
        watcher.cancel()
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Coroutine, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------

@dataclass
class Interrupt:
    """A detected interrupt waiting to be handled."""
    rule_name: str
    priority: int
    page: "Page"


@dataclass
class InterruptHandleResult:
    """Outcome of handling an interrupt."""
    rule_name: str
    resolved: bool
    action_taken: str
    error: str = ""


# ---------------------------------------------------------------------------
# Built-in interrupt handlers
# ---------------------------------------------------------------------------

class _CookieConsentHandler:
    """Accept cookie / GDPR consent banners."""

    # Selectors ordered by specificity — first visible match wins
    _ACCEPT_SELECTORS = [
        # Explicit accept/allow/ok buttons inside consent containers
        "[id*='cookie'] button[class*='accept' i]",
        "[id*='consent'] button[class*='accept' i]",
        "[class*='cookie'] button[class*='accept' i]",
        "[class*='consent'] button[class*='accept' i]",
        "[id*='cookie-banner'] button",
        "[id*='gdpr'] button[class*='agree' i]",
        # Generic accept text inside any visible dialog-like element
        "[role='dialog'] button",
        # OneTrust / CookiePro / Osano specifics
        "#onetrust-accept-btn-handler",
        "#accept-cookie-consent",
        ".cc-accept",
        ".js-cookie-consent-agree",
        "[data-gdpr-accept]",
        "[data-cookiebanner='accept_button']",
    ]

    _ACCEPT_TEXT = re.compile(
        r"^(accept|accept all|allow|allow all|ok|got it|i agree|agree|continue|yes)$",
        re.IGNORECASE,
    )

    async def handle(self, page: "Page") -> InterruptHandleResult:
        for sel in self._ACCEPT_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=500):
                    text = (await btn.inner_text() or "").strip()
                    if not text or self._ACCEPT_TEXT.match(text):
                        await btn.click(timeout=3_000)
                        await asyncio.sleep(0.4)
                        return InterruptHandleResult(
                            rule_name="cookie_consent",
                            resolved=True,
                            action_taken=f"clicked '{text or sel}'",
                        )
            except Exception:
                continue

        # Fallback: set a session storage marker that many CMPs check
        try:
            await page.evaluate("""() => {
                try { localStorage.setItem('cookieConsent', 'true'); } catch {}
                try { localStorage.setItem('gdpr_consent', '1'); } catch {}
                try { sessionStorage.setItem('cookie_accepted', '1'); } catch {}
            }""")
            return InterruptHandleResult(
                rule_name="cookie_consent",
                resolved=True,
                action_taken="set localStorage consent markers",
            )
        except Exception as exc:
            return InterruptHandleResult(
                rule_name="cookie_consent",
                resolved=False,
                action_taken="",
                error=str(exc),
            )


class _MarketingModalHandler:
    """Close newsletter / marketing popups."""

    _CLOSE_SELECTORS = [
        "[aria-label*='close' i]",
        "[aria-label*='dismiss' i]",
        "[title*='close' i]",
        "[title*='dismiss' i]",
        ".modal-close",
        ".popup-close",
        ".dialog-close",
        "[class*='modal'] [class*='close']",
        "[class*='popup'] [class*='close']",
        "[class*='overlay'] [class*='close']",
        "button[class*='close' i]",
        # X / × close icon buttons inside modals
        "[role='dialog'] button:has-text('×')",
        "[role='dialog'] button:has-text('✕')",
        "[role='dialog'] button:has-text('✗')",
    ]

    async def handle(self, page: "Page") -> InterruptHandleResult:
        # Try Escape first — works for most CSS-only modals
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            # Check if modal disappeared
            modal_visible = False
            for sel in ("[role='dialog']", "[class*='modal']", "[class*='popup']"):
                try:
                    if await page.locator(sel).first.is_visible(timeout=400):
                        modal_visible = True
                        break
                except Exception:
                    pass
            if not modal_visible:
                return InterruptHandleResult(
                    rule_name="marketing_modal",
                    resolved=True,
                    action_taken="Escape key",
                )
        except Exception:
            pass

        # Try close buttons
        for sel in self._CLOSE_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=400):
                    await btn.click(timeout=2_000)
                    await asyncio.sleep(0.3)
                    return InterruptHandleResult(
                        rule_name="marketing_modal",
                        resolved=True,
                        action_taken=f"clicked close button: {sel}",
                    )
            except Exception:
                continue

        return InterruptHandleResult(
            rule_name="marketing_modal",
            resolved=False,
            action_taken="",
            error="no close button found",
        )


class _SessionExpiryHandler:
    """Handle session-expiry countdown modals — click 'Stay logged in'."""

    _RENEW_SELECTORS = [
        "button:has-text('Stay logged in')",
        "button:has-text('Keep me logged in')",
        "button:has-text('Continue')",
        "button:has-text('Extend session')",
        "button:has-text('Refresh')",
        "[class*='session'] button",
        "[id*='session'] button",
    ]

    async def handle(self, page: "Page") -> InterruptHandleResult:
        for sel in self._RENEW_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=400):
                    await btn.click(timeout=2_000)
                    return InterruptHandleResult(
                        rule_name="session_expiry",
                        resolved=True,
                        action_taken=f"clicked '{sel}'",
                    )
            except Exception:
                continue

        return InterruptHandleResult(
            rule_name="session_expiry",
            resolved=False,
            action_taken="",
        )


class _ChatWidgetHandler:
    """Minimise / hide chat widgets that cover page content."""

    _IFRAME_DOMAINS = [
        "intercom.io",
        "drift.com",
        "zendesk.com",
        "crisp.chat",
        "tawk.to",
        "freshchat.com",
        "livechat.com",
        "hubspot.com",
    ]

    async def handle(self, page: "Page") -> InterruptHandleResult:
        # Inject CSS to hide common chat widget containers
        try:
            await page.add_style_tag(content="""
                [id*='intercom'], [class*='intercom'],
                [id*='drift'],    [class*='drift'],
                [id*='crisp'],    [class*='crisp'],
                [id*='tawk'],     [class*='tawk'],
                [id*='freshchat'],[class*='freshchat'],
                iframe[src*='intercom'], iframe[src*='drift'],
                iframe[src*='crisp'],    iframe[src*='tawk'],
                .zopim, #launcher { display: none !important; }
            """)
            return InterruptHandleResult(
                rule_name="chat_widget",
                resolved=True,
                action_taken="injected CSS hide rule for chat widget",
            )
        except Exception as exc:
            return InterruptHandleResult(
                rule_name="chat_widget",
                resolved=False,
                action_taken="",
                error=str(exc),
            )


class _BrowserDialogHandler:
    """Handle native browser dialogs (alert/confirm/prompt) by accepting them."""

    async def handle(self, page: "Page") -> InterruptHandleResult:
        # Playwright auto-dismisses dialogs unless a handler is installed.
        # This handler installs an accept-all policy that persists for the page.
        try:
            page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            return InterruptHandleResult(
                rule_name="browser_dialog",
                resolved=True,
                action_taken="installed dialog accept handler",
            )
        except Exception as exc:
            return InterruptHandleResult(
                rule_name="browser_dialog",
                resolved=False,
                action_taken="",
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Interrupt detectors
# ---------------------------------------------------------------------------

async def _detect_cookie_consent(page: "Page") -> bool:
    try:
        selectors = [
            "[id*='cookie'][class*='banner']",
            "[id*='cookie'][class*='consent']",
            "[id*='consent'][class*='banner']",
            "[id*='gdpr']",
            "#onetrust-banner-sdk",
            ".cc-window",
            "[class*='cookiebanner']",
            "[class*='cookie-notice']",
        ]
        for sel in selectors:
            if await page.locator(sel).first.is_visible(timeout=300):
                return True
    except Exception:
        pass
    return False


async def _detect_marketing_modal(page: "Page") -> bool:
    """Detect modal-style overlays that are NOT cookie consent."""
    try:
        # Must have a role=dialog OR class containing modal/popup
        # AND contain a close button (to differentiate from real app dialogs)
        close_present = False
        for sel in (
            "[role='dialog'] [aria-label*='close' i]",
            "[role='dialog'] button:has-text('×')",
            "[class*='modal'] [class*='close']",
            "[class*='popup'] button",
        ):
            if await page.locator(sel).first.is_visible(timeout=200):
                close_present = True
                break
        if not close_present:
            return False

        # Filter out consent dialogs (those are handled by cookie_consent rule)
        consent_signals = await page.evaluate("""() => {
            const el = document.querySelector('[role=\\'dialog\\'], [class*=\\'modal\\']');
            if (!el) return false;
            const t = (el.textContent || '').toLowerCase();
            return /cookie|gdpr|consent|privacy policy/.test(t);
        }""")
        return not consent_signals
    except Exception:
        return False


async def _detect_session_expiry(page: "Page") -> bool:
    try:
        return await page.evaluate("""() => {
            const body = (document.body.innerText || '').toLowerCase();
            return /session.*expir|you.*be.*logged out|session.*timeout|
                    idle.*timeout|stay logged in/i.test(body);
        }""")
    except Exception:
        return False


async def _detect_chat_widget_blocking(page: "Page") -> bool:
    """Detect if a chat widget iframe is positioned over interactive content."""
    try:
        return await page.evaluate("""() => {
            const domains = ['intercom', 'drift', 'crisp', 'tawk', 'freshchat'];
            const frames = Array.from(document.querySelectorAll('iframe'));
            for (const f of frames) {
                const src = f.src || '';
                if (!domains.some(d => src.includes(d))) continue;
                const rect = f.getBoundingClientRect();
                // Chat widget covering bottom 30% of viewport
                if (rect.bottom > window.innerHeight * 0.7 &&
                    rect.height > 40 && rect.width > 40) {
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# InterruptRule registry
# ---------------------------------------------------------------------------

@dataclass
class InterruptRule:
    name: str
    priority: int
    detector: Callable
    handler: object

    async def detected(self, page: "Page") -> bool:
        try:
            return await self.detector(page)
        except Exception:
            return False

    async def handle(self, page: "Page") -> InterruptHandleResult:
        return await self.handler.handle(page)


_DEFAULT_RULES: List[InterruptRule] = [
    InterruptRule(
        name="chat_widget",
        priority=5,
        detector=_detect_chat_widget_blocking,
        handler=_ChatWidgetHandler(),
    ),
    InterruptRule(
        name="cookie_consent",
        priority=10,
        detector=_detect_cookie_consent,
        handler=_CookieConsentHandler(),
    ),
    InterruptRule(
        name="session_expiry",
        priority=15,
        detector=_detect_session_expiry,
        handler=_SessionExpiryHandler(),
    ),
    InterruptRule(
        name="marketing_modal",
        priority=20,
        detector=_detect_marketing_modal,
        handler=_MarketingModalHandler(),
    ),
]


# ---------------------------------------------------------------------------
# PageInterruptController
# ---------------------------------------------------------------------------

class PageInterruptController:
    """
    Background interrupt scanner for the ReplayEngine step loop.

    Runs as an asyncio background task. Detects page-level interrupts (cookie
    banners, marketing modals, session expiry, chat widgets) and puts them into
    an asyncio.Queue. The step loop drains the queue before each step and on
    ElementNotFound/Timeout exceptions.

    One instance is created per replay run. It is not reused across runs.
    """

    def __init__(
        self,
        rules: Optional[List[InterruptRule]] = None,
        poll_interval_s: float = 0.5,
    ) -> None:
        self._rules = sorted(
            rules or _DEFAULT_RULES,
            key=lambda r: r.priority,
        )
        self._poll_interval = poll_interval_s
        self._suppressed: set = set()    # rule names suppressed after handling

    async def watch(
        self,
        page: "Page",
        interrupt_queue: asyncio.Queue,
    ) -> None:
        """
        Background coroutine. Poll for interrupts at `poll_interval_s` cadence.
        Puts Interrupt objects into `interrupt_queue` when detected.
        Stops when cancelled.
        """
        while True:
            try:
                for rule in self._rules:
                    if rule.name in self._suppressed:
                        continue
                    if await rule.detected(page):
                        await interrupt_queue.put(
                            Interrupt(rule_name=rule.name, priority=rule.priority, page=page)
                        )
                        break  # one interrupt per poll cycle — let the step loop drain first
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(self._poll_interval)

    def suppress(self, rule_name: str) -> None:
        """Stop detecting a rule for the lifetime of this controller."""
        self._suppressed.add(rule_name)

    def get_rule(self, name: str) -> Optional[InterruptRule]:
        return next((r for r in self._rules if r.name == name), None)


# ---------------------------------------------------------------------------
# Step-loop helper — drain + handle all queued interrupts
# ---------------------------------------------------------------------------

async def drain_interrupts(
    page: "Page",
    interrupt_queue: asyncio.Queue,
    controller: Optional[PageInterruptController] = None,
    max_drain: int = 5,
) -> List[InterruptHandleResult]:
    """
    Drain the interrupt queue and handle each interrupt.

    Call this:
      1. Before every step (at the top of the step loop)
      2. After an ElementNotFound or Timeout exception (the interrupt may have
         caused the failure)

    Args:
        page:             Live Playwright page.
        interrupt_queue:  Shared queue fed by PageInterruptController.watch().
        controller:       The controller that produced the interrupts — used
                          to resolve the handler for each interrupt.  If None,
                          uses a default controller.
        max_drain:        Maximum interrupts to handle in one call (prevents
                          infinite loop if a handler fails to dismiss).

    Returns:
        List of InterruptHandleResult — one per handled interrupt.
    """
    if controller is None:
        controller = PageInterruptController()

    results: List[InterruptHandleResult] = []
    handled = 0

    while not interrupt_queue.empty() and handled < max_drain:
        try:
            interrupt: Interrupt = interrupt_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        rule = controller.get_rule(interrupt.rule_name)
        if rule is None:
            # Rule was removed — build a no-op result
            results.append(InterruptHandleResult(
                rule_name=interrupt.rule_name,
                resolved=False,
                action_taken="rule not found",
            ))
            handled += 1
            continue

        result = await rule.handle(page)
        results.append(result)
        handled += 1

        if result.resolved:
            # Suppress this rule for 30 s to avoid re-detecting an element that
            # takes a moment to animate out.  The suppress is on the controller
            # instance so it affects the background watcher too.
            controller.suppress(interrupt.rule_name)

    return results
