"""
reach_engine.py — L5 "Reach" phase: make an element interactable.

Handles overlay detection, layout quiescence, and scroll-into-view so that
ExecutionEngine.execute() can assume the locator is ready to interact with.

L5 upgrade — Overlay dismissal state machine:
  The original implementation was fire-and-forget: detect overlay, dismiss, done.
  This fails for overlays that re-appear (marketing modals that re-trigger on
  every page load, z-index traps from chat widgets, etc.).

  The upgraded engine maintains an OverlayState that persists across ALL steps
  in a single replay run. When an overlay that was already dismissed re-appears,
  the engine escalates to CSS suppression (display:none !important injected via
  page.add_style_tag) instead of attempting another UI interaction.

  The state machine has three dismissal paths per overlay selector:
    1. First encounter   → soft_dismiss (click close button or press Escape)
    2. Re-appearance     → hard_dismiss (CSS injection to force-hide)
    3. Still visible     → give up; report blocked_by so the step fails cleanly

  Session-level localStorage marker "bm_overlay_dismissed" is set after the
  first soft dismiss so GDPR/cookie banners don't reappear on navigation.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Set

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


# ---------------------------------------------------------------------------
# Result and state types
# ---------------------------------------------------------------------------

@dataclass
class ReachResult:
    success: bool
    duration_ms: int
    blocked_by: Optional[str] = None
    dismissed_overlay: bool = False
    css_suppressed: bool = False       # True if CSS injection was used
    scrolled: bool = False
    error: Optional[str] = None


@dataclass
class OverlayState:
    """
    Session-persistent dismissal state shared across all reach() calls in a run.

    dismissed_selectors: selectors that have already been soft-dismissed this run.
    css_suppressed_selectors: selectors suppressed via CSS injection.
    session_marker_set: True if localStorage["bm_overlay_dismissed"] has been set.
    """
    dismissed_selectors:        Set[str] = field(default_factory=set)
    css_suppressed_selectors:   Set[str] = field(default_factory=set)
    session_marker_set:         bool = False


# ---------------------------------------------------------------------------
# Overlay and dismiss selector lists
# ---------------------------------------------------------------------------

_OVERLAY_SELECTORS = [
    "[role='dialog']",
    "[role='alertdialog']",
    ".modal",
    ".overlay",
    ".popup",
    "[class*='modal' i]",
    "[class*='overlay' i]",
    "[class*='popup' i]",
    "[class*='cookie' i]",
    "[class*='consent' i]",
    "[class*='gdpr' i]",
    "[class*='banner' i]",
    # Chat widgets — common z-index traps
    "#intercom-container",
    "[id*='intercom' i]",
    "[class*='intercom' i]",
    "[id*='drift' i]",
    "[class*='drift-widget' i]",
    "[id*='zendesk' i]",
    "[class*='zopim' i]",
    "[id*='hubspot' i]",
    "[class*='hs-beacon' i]",
]

_DISMISS_SELECTORS = [
    "button[class*='close' i]",
    "button[aria-label*='close' i]",
    "button[aria-label*='dismiss' i]",
    "button[aria-label*='accept' i]",
    "button[aria-label*='agree' i]",
    "button[aria-label*='got it' i]",
    "button[data-testid*='close' i]",
    "[class*='close-button' i]",
    "[class*='closeButton' i]",
    "[data-dismiss]",
    "[data-close]",
    "a[id*='close' i]",
    "a[class*='close' i]",
]

# CSS injected to hard-suppress a re-appearing overlay.
# Uses maximum specificity + !important to override inline styles.
_CSS_SUPPRESS_TEMPLATE = """{selector} {{ display: none !important; visibility: hidden !important; pointer-events: none !important; }}"""


# ---------------------------------------------------------------------------
# ReachEngine
# ---------------------------------------------------------------------------

class ReachEngine:
    """
    Ensures an element is in a reachable, interactable state before action.

    Protocol:
      1. Scroll element into view
      2. Wait for layout quiescence (no DOM size changes for 2 frames)
      3. Check for blocking overlays
      4. Attempt overlay dismissal using the state machine:
           a. First encounter → soft dismiss (click close / Escape) + localStorage marker
           b. Re-appearance   → hard dismiss (CSS injection)
           c. Still visible   → fail cleanly with blocked_by reason
      5. Re-verify interactability

    OverlayState must be shared across all reach() calls in a single replay run
    so the state machine tracks re-appearances correctly. Pass the same
    OverlayState instance to every ReachEngine that serves one ReplayEngine run.
    """

    def __init__(
        self,
        page: "Page",
        overlay_state: Optional[OverlayState] = None,
        quiescence_timeout_ms: int = 500,
        overlay_timeout_ms: int = 2_000,
        dismiss_overlays: bool = True,
    ) -> None:
        self._page = page
        # If no shared state is provided, create a local one.
        # Callers should pass a shared instance for cross-step state tracking.
        self._overlay_state = overlay_state if overlay_state is not None else OverlayState()
        self._quiescence_timeout_ms = quiescence_timeout_ms
        self._overlay_timeout_ms = overlay_timeout_ms
        self._dismiss_overlays = dismiss_overlays

    async def reach(self, locator: "Locator") -> ReachResult:
        start = time.monotonic()
        scrolled = False
        dismissed = False
        css_suppressed = False

        try:
            # 1. Scroll into view
            try:
                await locator.scroll_into_view_if_needed(timeout=5_000)
                scrolled = True
            except Exception:
                pass

            # 2. Brief layout quiescence
            await self._wait_for_quiescence()

            # 3. Check whether element is visible and enabled
            if not await self._is_interactable(locator):
                if self._dismiss_overlays:
                    overlay_sel = await self._find_overlay()
                    if overlay_sel:
                        # 4. State machine dispatch
                        if overlay_sel in self._overlay_state.css_suppressed_selectors:
                            # Already CSS-suppressed yet still visible — give up
                            pass
                        elif overlay_sel in self._overlay_state.dismissed_selectors:
                            # Re-appeared after soft dismiss — escalate to CSS suppression
                            suppressed = await self._css_suppress(overlay_sel)
                            if suppressed:
                                self._overlay_state.css_suppressed_selectors.add(overlay_sel)
                                css_suppressed = True
                                await asyncio.sleep(0.2)
                        else:
                            # First encounter — try soft dismiss
                            soft_ok = await self._soft_dismiss(overlay_sel)
                            if soft_ok:
                                self._overlay_state.dismissed_selectors.add(overlay_sel)
                                dismissed = True
                                await asyncio.sleep(0.3)
                                # Set localStorage marker to suppress cookie banners on navigation
                                if not self._overlay_state.session_marker_set:
                                    await self._set_session_marker()

                # Re-check after dismissal attempt
                if not await self._is_interactable(locator):
                    overlay = await self._find_overlay()
                    duration = int((time.monotonic() - start) * 1000)
                    return ReachResult(
                        success=False,
                        duration_ms=duration,
                        blocked_by=overlay or "unknown",
                        dismissed_overlay=dismissed,
                        css_suppressed=css_suppressed,
                        scrolled=scrolled,
                        error="Element not interactable after overlay dismissal attempt",
                    )

            duration = int((time.monotonic() - start) * 1000)
            return ReachResult(
                success=True,
                duration_ms=duration,
                dismissed_overlay=dismissed,
                css_suppressed=css_suppressed,
                scrolled=scrolled,
            )

        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            return ReachResult(
                success=False,
                duration_ms=duration,
                scrolled=scrolled,
                dismissed_overlay=dismissed,
                css_suppressed=css_suppressed,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _is_interactable(self, locator: "Locator") -> bool:
        try:
            visible = await locator.is_visible(timeout=2_000)
            if not visible:
                return False
            enabled = await locator.is_enabled(timeout=2_000)
            return enabled
        except Exception:
            return False

    async def _wait_for_quiescence(self) -> None:
        """Wait until DOM element count stops changing for 2 consecutive frames."""
        deadline = time.monotonic() + self._quiescence_timeout_ms / 1000.0
        prev_count = -1
        stable_frames = 0
        while time.monotonic() < deadline:
            try:
                count = await self._page.evaluate("() => document.querySelectorAll('*').length")
                if count == prev_count:
                    stable_frames += 1
                    if stable_frames >= 2:
                        return
                else:
                    stable_frames = 0
                prev_count = count
            except Exception:
                return
            await asyncio.sleep(0.05)

    async def _find_overlay(self) -> Optional[str]:
        """Return selector of first visible overlay blocking the page, or None."""
        for sel in _OVERLAY_SELECTORS:
            try:
                count = await self._page.locator(sel).count()
                if count > 0:
                    visible = await self._page.locator(sel).first.is_visible()
                    if visible:
                        return sel
            except Exception:
                continue
        return None

    async def _soft_dismiss(self, overlay_sel: str) -> bool:
        """
        Attempt to dismiss an overlay via close/dismiss buttons or Escape.
        Returns True if a dismiss action was taken (not a guarantee it worked).
        """
        for sel in _DISMISS_SELECTORS:
            try:
                btn = self._page.locator(sel).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=2_000)
                    return True
            except Exception:
                continue
        # Try pressing Escape as fallback
        try:
            await self._page.keyboard.press("Escape")
            return True
        except Exception:
            pass
        return False

    async def _css_suppress(self, overlay_sel: str) -> bool:
        """
        Inject CSS to force-hide an overlay that re-appeared after soft dismiss.
        Uses display:none !important to override inline styles.
        """
        css = _CSS_SUPPRESS_TEMPLATE.format(selector=overlay_sel)
        try:
            await self._page.add_style_tag(content=css)
            return True
        except Exception:
            return False

    async def _set_session_marker(self) -> None:
        """
        Set localStorage["bm_overlay_dismissed"] = "1" so GDPR/cookie banners
        don't re-fire on subsequent page navigations within this session.
        """
        try:
            await self._page.evaluate(
                "() => { try { localStorage.setItem('bm_overlay_dismissed', '1'); } catch(_) {} }"
            )
            self._overlay_state.session_marker_set = True
        except Exception:
            pass
