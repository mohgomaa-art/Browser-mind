"""
ExplorerPolicy — closes the gap between affordance discovery and affordance execution.

Enhanced with:
  - Cookie/modal auto-dismissal (#16, #17): _dismiss_overlays() called before discovery
  - Human-like timing (#23): jittered pauses between actions
  - Step-level retry (#22): transient executor errors are retried once
  - Mobile viewport toggle (#21): can explore in mobile mode via run(mobile=True)
  - Negative evidence storage (#42): FAILED steps now carry evidence type for corpus
  - Evidence quality scoring (#43): quality_score propagated to FailureAttribution
  - Multi-hop exploration: after TRANSITION_SUCCESS, rescans new page and continues

Logging prefix: [ExplorerPolicy]
"""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

from browsermind_core.errors import AuthGateError
from browsermind_core.runtime.affordance import Affordance
from browsermind_core.runtime.affordance_discoverer import best_affordance
from browsermind_core.runtime.affordance_executor import AffordanceExecutor, AffordanceExecutionError
from browsermind_core.runtime.intent_family import IntentFamily

if TYPE_CHECKING:
    from playwright.async_api import Page

# Probe values — safe, obviously synthetic, won't trigger real actions
_PROBE_QUERY = "bm_probe"
_PROBE_TEXT = "BrowserMind Probe"
_PROBE_EMAIL = "probe@browsermind.io"
_PROBE_FILL_BY_TYPE = {
    "text":   _PROBE_TEXT,
    "search": _PROBE_QUERY,
    "email":  _PROBE_EMAIL,
    "tel":    "555-0100",
    "url":    "https://browsermind.io",
    "number": "1",
}

# Families the policy will attempt to execute (AUTH is intentionally excluded)
_EXECUTABLE_FAMILIES = {IntentFamily.SEARCH, IntentFamily.FORM, IntentFamily.FILTER, IntentFamily.NAVIGATION}

# Overlay dismissal selectors — ordered from most-specific to most-generic
_OVERLAY_DISMISS_SELECTORS = [
    # Cookie consent / GDPR
    "button[id*='accept' i]", "button[class*='accept' i]",
    "button[id*='agree' i]", "button[class*='agree' i]",
    "button[id*='consent' i]", "button[class*='consent' i]",
    "#onetrust-accept-btn-handler",
    "[id*='cookie'] button", "[class*='cookie'] button",
    # Generic modal close
    "button[aria-label*='close' i]", "button[aria-label*='dismiss' i]",
    "[role='dialog'] button[class*='close' i]",
    "[role='dialog'] button[class*='dismiss' i]",
    # Newsletter / subscription popups
    "[class*='popup'] button[class*='close' i]",
    "[class*='modal'] button[class*='close' i]",
    # App install banners
    "[class*='banner'] button[class*='close' i]",
    "[id*='banner'] button[class*='close' i]",
]

# Bot-wall keyword signals
# Split into SOFT (auto-recoverable) and HARD (needs human).
# _detect_bot_wall() tries Cloudflare bypass for SOFT walls before giving up.
_BOT_WALL_PHRASES_SOFT = [
    # Cloudflare JS challenge — auto-resolves in ~5s
    "just a moment", "ddos protection by cloudflare", "ray id",
    "checking your browser", "enable javascript and cookies",
    # Generic JS/redirect challenge pages
    "please wait", "redirecting you",
]
_BOT_WALL_PHRASES_HARD = [
    # Google automation detection
    "browser or app may not be secure", "try using a different browser",
    "this app may not be secure",
    # Arabic Google
    "قد يكون هذا المتصفّح",
    "غير آمن",
    # Generic bot walls
    "unusual activity", "automated", "captcha", "prove you're human",
    "verify you are", "i'm not a robot", "access denied", "403 forbidden",
    "ddos-guard", "security check required",
    # Localized bot walls
    "vérification requise",           # French
    "bitte bestätigen sie",           # German
    "verificación requerida",         # Spanish
    "verificação necessária",         # Portuguese
    "로봇이 아닙니다",                   # Korean
]
# Combined list for fast single-pass scan
_BOT_WALL_PHRASES = _BOT_WALL_PHRASES_SOFT + _BOT_WALL_PHRASES_HARD

# URL patterns that always indicate a bot wall
_BOT_WALL_URL_PATTERNS = [
    "accounts.google.com/v3/signin/rejected",
    "accounts.google.com/signin/rejected",
    "challenges.cloudflare.com",
    "/cdn-cgi/challenge-platform/",
]


class ExplorerPolicy:
    """
    Autonomous exploration policy: affordance → action proposal → execution → observation.
    """

    async def run(
        self,
        page: "Page",
        all_discovered: List[Tuple[IntentFamily, List[Affordance]]],
        budget: int,
        env_key: str,
        mobile: bool = False,
        hypothesis_store=None,
        state_classifier=None,
    ) -> List:
        """
        Run the exploration loop.

        Args:
            page:             Playwright page
            all_discovered:   [(family, [Affordance])] from AffordanceDiscoverer
            budget:           Max steps to execute
            env_key:          Site key for logging
            mobile:           If True, switch to mobile viewport before exploring (#21)
            hypothesis_store: Optional CapabilityHypothesisStore — when provided,
                              negative evidence is persisted (#42)
            state_classifier: Optional SemanticStateClassifier — when provided,
                              populates semantic_state_before/after on each step

        Returns:
            List of FailureAttribution records
        """
        steps = []
        seq = 1000
        visited_urls: set = {self._normalize_url(page.url)}

        # Check for bot wall before doing anything
        bot_signal = await self._detect_bot_wall(page)
        if bot_signal:
            print(f"  [ExplorerPolicy] BOT WALL detected: {bot_signal!r}")
            raise RuntimeError(f"bot_detected: {bot_signal}")

        # Check for auth gate: if auth is the only non-empty affordance family,
        # we can't make progress — raise so MissionWorker marks the site paused.
        auth_families = {IntentFamily.AUTH}
        has_auth = any(
            family in auth_families and len(affordances) > 0
            for family, affordances in all_discovered
        )
        has_executable = any(
            family in _EXECUTABLE_FAMILIES and len(affordances) > 0
            for family, affordances in all_discovered
        )
        if has_auth and not has_executable:
            print(f"  [ExplorerPolicy] AUTH GATE detected: no executable affordances for env={env_key}")
            raise AuthGateError(f"auth_required: login gate detected for env={env_key}")

        # Dismiss overlays before discovery (#16, #17)
        dismissed = await self._dismiss_overlays(page)
        if dismissed > 0:
            print(f"  [ExplorerPolicy] Dismissed {dismissed} overlay(s)")
            await self._human_pause(300, 600)

        # Mobile viewport toggle (#21)
        if mobile:
            await self._set_mobile_viewport(page)

        # Sort by best affordance score so highest-signal family runs first
        sorted_discovered = sorted(
            all_discovered,
            key=lambda pair: max((a.score for a in pair[1]), default=0.0),
            reverse=True,
        )

        for family, affordances in sorted_discovered:
            if len(steps) >= budget:
                break

            if family not in _EXECUTABLE_FAMILIES:
                print(f"  [ExplorerPolicy] Skipping family={family.value} (not executable)")
                continue

            best = best_affordance(affordances, min_score=0.5)
            if best is None:
                continue

            print(
                f"  [ExplorerPolicy] Selected: {best.type}(score={best.score:.2f})"
                f" family={family.value} signal={best.evidence.get('signal', '?')!r}"
            )

            # --- Fill phase ---
            fill_attr = await self._fill_input(page, family, best, seq)
            if fill_attr is not None:
                steps.append(fill_attr)
                print(
                    f"  [ExplorerPolicy] Generated Action:"
                    f" {fill_attr.action_type!r} {fill_attr.role!r}"
                    f" → {fill_attr.actual_outcome}"
                )
                seq += 1

            if len(steps) >= budget:
                break

            # Human-like pause between fill and click (#23)
            await self._human_pause(80, 250)

            # --- Execute phase (with retry) (#22) ---
            url_before = page.url
            exec_attr = await self._execute_with_retry(
                page, family, best, seq, url_before,
                state_classifier=state_classifier,
            )
            if exec_attr is not None:
                steps.append(exec_attr)
                seq += 1

                print(
                    f"  [ExplorerPolicy] Executed: {best.type}"
                    f" → {exec_attr.actual_outcome}"
                )

                if exec_attr.actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS"):
                    details = getattr(exec_attr, "effect_details", None) or {}
                    obs = details.get("evidence", "unknown")
                    print(f"  [ExplorerPolicy] Observed: {obs}")
                    exp_label = _infer_experience_label(family, exec_attr.actual_outcome, obs)
                    print(f"  [ExplorerPolicy] Experience: {exp_label}")
                    hyp_label = f"{best.type}_confirmed"
                    print(f"  [ExplorerPolicy] Hypothesis: {hyp_label}")
                    # Persist positive hypothesis (#43)
                    if hypothesis_store is not None:
                        try:
                            hypothesis_store.observe(
                                invariants=[best.type, family.value],
                                env_key=env_key,
                                source="explorer_policy",
                                context_hint=obs,
                                outcome=exec_attr.actual_outcome,
                            )
                        except Exception as _he:
                            print(f"  [ExplorerPolicy] hypothesis_store.observe failed: {_he}")

                    # Multi-hop: after a page transition, rescan and keep exploring
                    if exec_attr.actual_outcome == "TRANSITION_SUCCESS" and len(steps) < budget:
                        new_url = self._normalize_url(page.url)
                        if new_url in visited_urls:
                            print(f"  [ExplorerPolicy] Skipping already-visited URL: {new_url!r}")
                        else:
                            visited_urls.add(new_url)
                            new_steps = await self._explore_page(
                                page, budget - len(steps), env_key,
                                hypothesis_store=hypothesis_store, seq_start=seq,
                                visited_urls=visited_urls,
                                state_classifier=state_classifier,
                            )
                            steps.extend(new_steps)
                            seq += len(new_steps)
                elif exec_attr.actual_outcome == "FAILED":
                    reason = getattr(exec_attr, "failure_reason", "unknown")
                    print(f"  [ExplorerPolicy] Negative evidence: {reason!r}")
                    # Persist negative evidence to hypothesis store (#42)
                    if hypothesis_store is not None:
                        try:
                            hypothesis_store.observe(
                                invariants=[best.type, family.value, f"NEGATIVE:{reason}"],
                                env_key=env_key,
                                source="explorer_policy_negative",
                                context_hint=f"failed: {reason}",
                                outcome="FAILED",
                            )
                        except Exception as _he:
                            print(f"  [ExplorerPolicy] hypothesis_store negative persist failed: {_he}")

            # Inter-step human pause
            await self._human_pause(100, 400)

        # Budget exhaustion check: if families loop finished with remaining budget,
        # re-scan the current page to keep exploring (same depth=0, single hop).
        if len(steps) < budget:
            remaining = budget - len(steps)
            current_url = self._normalize_url(page.url)
            extra_steps = await self._explore_page(
                page, remaining, env_key,
                hypothesis_store=hypothesis_store,
                seq_start=seq,
                depth=0,
                visited_urls=visited_urls,
                state_classifier=state_classifier,
            )
            steps.extend(extra_steps)

        return steps

    # ------------------------------------------------------------------
    # Multi-hop continuation
    # ------------------------------------------------------------------

    async def _explore_page(
        self,
        page: "Page",
        remaining_budget: int,
        env_key: str,
        hypothesis_store=None,
        seq_start: int = 2000,
        depth: int = 0,
        max_depth: int = 3,
        visited_urls: Optional[set] = None,
        state_classifier=None,
    ) -> list:
        """Discover affordances on the current page and execute them.

        Called after each TRANSITION_SUCCESS to continue exploration on the
        new page. Recurses up to max_depth times so BrowserMind can explore
        multi-step flows (e.g. search → results → open post → comments).
        """
        if remaining_budget <= 0 or depth >= max_depth:
            return []

        if visited_urls is None:
            visited_urls = set()
        visited_urls.add(self._normalize_url(page.url))

        from browsermind_core.runtime.affordance_discoverer import AffordanceDiscoverer

        steps = []
        seq = seq_start

        # Brief wait for the new page to settle
        await page.wait_for_timeout(400)

        # Dismiss any overlays that appeared after navigation
        dismissed = await self._dismiss_overlays(page)
        if dismissed:
            await self._human_pause(200, 400)

        print(f"  [ExplorerPolicy/MultiHop] Rescanning page (depth={depth}) url={page.url[:60]!r}")

        discoverer = AffordanceDiscoverer()
        families_to_try = [
            IntentFamily.SEARCH, IntentFamily.NAVIGATION, IntentFamily.FORM, IntentFamily.FILTER
        ]

        for family in families_to_try:
            if len(steps) >= remaining_budget:
                break
            try:
                affordances = await discoverer.discover(page, family)
            except Exception:
                continue

            if not affordances:
                continue

            best = best_affordance(affordances, min_score=0.5)
            if best is None:
                continue

            print(
                f"  [ExplorerPolicy/MultiHop] Found: {best.type}(score={best.score:.2f})"
                f" family={family.value}"
            )

            fill_attr = await self._fill_input(page, family, best, seq)
            if fill_attr is not None:
                steps.append(fill_attr)
                seq += 1

            if len(steps) >= remaining_budget:
                break

            await self._human_pause(80, 200)

            url_before = page.url
            exec_attr = await self._execute_with_retry(
                page, family, best, seq, url_before,
                state_classifier=state_classifier,
            )
            if exec_attr is not None:
                steps.append(exec_attr)
                seq += 1

                outcome = exec_attr.actual_outcome
                details = getattr(exec_attr, "effect_details", None) or {}
                obs = details.get("evidence", "")
                exp_label = _infer_experience_label(family, outcome, obs)
                print(
                    f"  [ExplorerPolicy/MultiHop] {best.type} → {outcome}"
                    f" ({exp_label})"
                )

                if hypothesis_store is not None and outcome in ("SUCCESS", "TRANSITION_SUCCESS"):
                    try:
                        hypothesis_store.observe(
                            invariants=[best.type, family.value],
                            env_key=env_key,
                            source="explorer_policy_multihop",
                            context_hint=obs,
                            outcome=outcome,
                        )
                    except Exception:
                        pass

                # Recurse if we transitioned to yet another page
                if outcome == "TRANSITION_SUCCESS" and len(steps) < remaining_budget:
                    new_url = self._normalize_url(page.url)
                    if new_url in visited_urls:
                        print(f"  [ExplorerPolicy/MultiHop] Skipping already-visited URL: {new_url!r}")
                        # URL already visited — stop trying other families on this dead-end
                        break
                    else:
                        visited_urls.add(new_url)
                        child_steps = await self._explore_page(
                            page,
                            remaining_budget - len(steps),
                            env_key,
                            hypothesis_store=hypothesis_store,
                            seq_start=seq,
                            depth=depth + 1,
                            max_depth=max_depth,
                            visited_urls=visited_urls,
                            state_classifier=state_classifier,
                        )
                        steps.extend(child_steps)
                        seq += len(child_steps)
                        # Navigated away — stop iterating families on the now-stale page
                        break

            await self._human_pause(100, 300)

        return steps

    # ------------------------------------------------------------------
    # Overlay dismissal (#16, #17)
    # ------------------------------------------------------------------

    async def _dismiss_overlays(self, page: "Page") -> int:
        """
        Try to dismiss cookie banners, modals, and promotional overlays.
        Returns count of overlays dismissed.
        """
        dismissed = 0
        for sel in _OVERLAY_DISMISS_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=1500)
                    await page.wait_for_timeout(200)
                    dismissed += 1
                    break  # One dismissal per category is enough
            except Exception:
                continue

        # Also try pressing Escape for modals
        try:
            modal = page.locator("[role='dialog']:visible")
            if await modal.count() > 0:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)
                dismissed += 1
        except Exception:
            pass

        return dismissed

    # ------------------------------------------------------------------
    # Bot wall detection
    # ------------------------------------------------------------------

    async def _detect_bot_wall(self, page: "Page") -> Optional[str]:
        """Return the bot wall phrase detected, or None if page looks clean.

        For SOFT walls (Cloudflare JS challenge), tries auto-bypass first.
        For HARD walls (Google block, CAPTCHA), returns immediately.
        """
        signal = await self._scan_for_bot_wall(page)
        if signal is None:
            return None

        is_soft = any(p in signal for p in _BOT_WALL_PHRASES_SOFT)
        if is_soft:
            resolved = await self._try_cloudflare_bypass(page)
            if resolved:
                return None  # challenge cleared, continue normally
            return f"cloudflare_unresolved: {signal}"

        return signal

    async def _scan_for_bot_wall(self, page: "Page") -> Optional[str]:
        """Raw scan — check title, URL, and body for bot-wall phrases."""
        try:
            title = (await page.title() or "").lower()
            url   = page.url.lower()
            body  = await page.evaluate(
                "() => (document.body && document.body.innerText || '').slice(0,800).toLowerCase()"
            )
            combined = f"{title} {url} {body}"

            # URL-pattern check (fast, no string search needed)
            for pat in _BOT_WALL_URL_PATTERNS:
                if pat in url:
                    return f"url:{pat}"

            for phrase in _BOT_WALL_PHRASES:
                if phrase in combined:
                    return phrase
        except Exception:
            pass
        return None

    async def _try_cloudflare_bypass(self, page: "Page") -> bool:
        """Attempt to auto-resolve a Cloudflare challenge. Returns True if cleared.

        Three strategies in order:
          1. Wait up to 8s for the JS challenge to auto-resolve (checks every 500ms)
          2. Click the Turnstile iframe checkbox
          3. Click any visible checkbox on the page
        """
        # Phase 1: wait for JS challenge to auto-resolve
        for _ in range(16):  # 16 × 500ms = 8s
            await asyncio.sleep(0.5)
            still_blocked = await self._scan_for_bot_wall(page)
            if still_blocked is None:
                return True  # cleared!
            is_still_cf = any(p in still_blocked for p in _BOT_WALL_PHRASES_SOFT)
            if not is_still_cf:
                return False  # turned into a hard wall

        # Phase 2: try clicking Cloudflare Turnstile iframe checkbox
        try:
            frames = page.frames
            for frame in frames:
                if "challenges.cloudflare.com" in (frame.url or ""):
                    cb = frame.locator("input[type='checkbox']")
                    if await cb.count() > 0:
                        await cb.first.click(timeout=3000)
                        await asyncio.sleep(3)
                        if await self._scan_for_bot_wall(page) is None:
                            return True
        except Exception:
            pass

        # Phase 3: click any visible checkbox on the main page
        try:
            cb = page.locator("input[type='checkbox']:visible")
            if await cb.count() > 0:
                await cb.first.click(timeout=3000)
                await asyncio.sleep(3)
                if await self._scan_for_bot_wall(page) is None:
                    return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Human-like timing (#23)
    # ------------------------------------------------------------------

    async def _human_pause(self, min_ms: int = 80, max_ms: int = 300) -> None:
        """Wait a random duration to simulate human reaction time."""
        delay = random.randint(min_ms, max_ms)
        await asyncio.sleep(delay / 1000.0)

    # ------------------------------------------------------------------
    # URL normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip fragment and trailing slash for visited-URL deduplication."""
        return url.split('#')[0].rstrip('/')

    # ------------------------------------------------------------------
    # Mobile viewport (#21)
    # ------------------------------------------------------------------

    async def _set_mobile_viewport(self, page: "Page") -> None:
        try:
            await page.set_viewport_size({"width": 390, "height": 844})  # iPhone 14
            await page.wait_for_timeout(200)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fill phase
    # ------------------------------------------------------------------

    async def _fill_input(self, page: "Page", family: IntentFamily, affordance: Affordance, seq: int):
        from browsermind_core.ontology.p1_schemas import FailureAttribution

        try:
            if family == IntentFamily.SEARCH:
                return await self._fill_search_input(page, affordance, seq)
            elif family == IntentFamily.FORM:
                return await self._fill_form_inputs(page, affordance, seq)
            elif family in (IntentFamily.FILTER, IntentFamily.NAVIGATION):
                return None  # no fill step for these families
        except Exception as exc:
            return FailureAttribution(
                step_seq=seq,
                action_type="fill",
                role="textbox",
                name="probe_fill",
                predicted_tier="UNKNOWN",
                predicted_score=0.0,
                actual_outcome="FAILED",
                failure_reason=f"fill_error: {exc}",
                resolved_by="affordance_explorer",
            )

    async def _fill_search_input(self, page: "Page", affordance: Affordance, seq: int):
        from browsermind_core.ontology.p1_schemas import FailureAttribution

        signal = affordance.evidence.get("signal", "")
        if "focused_input" in signal and affordance.locator:
            try:
                await affordance.locator.fill(_PROBE_QUERY)
                return _ok_fill(seq, "searchbox")
            except Exception:
                pass

        for sel in [
            "[role='combobox'][aria-label*='Search' i]",
            "[aria-label*='Search' i][type='text']",
            "[aria-label*='Search' i]",
            "input[type='search']",
            "[role='searchbox']",
            "input[placeholder*='search' i]",
            "nav input[type='text']",
            "header input[type='text']",
            "[role='combobox']",
            "input[type='text']",
        ]:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await self._human_pause(40, 80)
                    await loc.fill(_PROBE_QUERY)
                    return _ok_fill(seq, "searchbox")
            except Exception:
                continue

        return None

    async def _fill_form_inputs(self, page: "Page", affordance: Affordance, seq: int):
        scope = affordance.locator if affordance.locator else page

        try:
            inputs = scope.locator("input, textarea")
            count = await inputs.count()
            filled = 0

            for i in range(min(count, 5)):
                inp = inputs.nth(i)
                try:
                    if not await inp.is_visible():
                        continue
                    tag = (await inp.evaluate("el => el.tagName.toLowerCase()")) or "input"
                    if tag == "textarea":
                        await inp.fill(_PROBE_TEXT)
                        filled += 1
                        await self._human_pause(30, 60)
                        continue
                    inp_type = (await inp.get_attribute("type") or "text").lower()
                    if inp_type in ("submit", "button", "checkbox", "radio", "file", "hidden"):
                        continue
                    probe = _PROBE_FILL_BY_TYPE.get(inp_type, _PROBE_TEXT)
                    await inp.fill(probe)
                    filled += 1
                    await self._human_pause(30, 60)
                except Exception:
                    continue

            if filled == 0:
                return None

            return _ok_fill(seq, "textbox")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Execute phase — with step-level retry (#22)
    # ------------------------------------------------------------------

    async def _execute_with_retry(
        self,
        page: "Page",
        family: IntentFamily,
        affordance: Affordance,
        seq: int,
        url_before: str,
        max_retries: int = 1,
        state_classifier=None,
    ):
        """Execute affordance with one transient-error retry."""
        for attempt in range(max_retries + 1):
            result = await self._execute_affordance(
                page, family, affordance, seq, url_before,
                state_classifier=state_classifier,
            )
            if result is None:
                return result
            # Retry on NO_VISIBLE_SIGNAL — could be timing issue
            if attempt < max_retries and result.actual_outcome == "FAILED" \
                    and "NO_VISIBLE_SIGNAL" in (result.failure_reason or ""):
                print(f"  [ExplorerPolicy] Retry {attempt + 1}/{max_retries} (no signal)")
                await page.wait_for_timeout(800)
                continue
            return result
        return result  # type: ignore[return-value]

    async def _execute_affordance(
        self,
        page: "Page",
        family: IntentFamily,
        affordance: Affordance,
        seq: int,
        url_before: str,
        state_classifier=None,
    ):
        from browsermind_core.ontology.p1_schemas import FailureAttribution
        from browsermind_core.exploration.effect_verifier import EffectVerifier

        _role_map = {
            IntentFamily.SEARCH:     "searchbox",
            IntentFamily.FORM:       "button",
            IntentFamily.FILTER:     "combobox",
            IntentFamily.NAVIGATION: "link",
        }
        _name_map = {
            IntentFamily.SEARCH:     "search query",
            IntentFamily.FORM:       "form submit",
            IntentFamily.FILTER:     "filter apply",
            IntentFamily.NAVIGATION: "follow link",
        }

        role = _role_map.get(family, "button")
        name = _name_map.get(family, affordance.type)

        verifier = EffectVerifier(start_url=url_before)
        before = await verifier.snapshot(page)
        _url_before_execute = page.url

        print(
            f"  [Action] type={affordance.type!r} family={family.value!r}"
            f" signal={(affordance.evidence or {}).get('signal', '?')!r}"
            f" url={_url_before_execute[:60]!r}"
        )

        # Classify semantic state before action
        _sem_before: Optional[dict] = None
        if state_classifier is not None:
            try:
                _sem_before = state_classifier.classify(before, url=_url_before_execute).to_dict()
            except Exception:
                pass

        executor = AffordanceExecutor()
        try:
            await executor.execute(page, affordance)

            _url_after_execute = page.url
            _url_changed = _url_after_execute != _url_before_execute

            # For navigation intents: if _execute_follow_link returned True but URL
            # hasn't actually changed yet, give it extra time to settle.
            # For non-navigation: just wait briefly for DOM to stabilise.
            if family == IntentFamily.NAVIGATION and not _url_changed:
                try:
                    await page.wait_for_function(
                        "url => window.location.href !== url",
                        arg=_url_before_execute,
                        timeout=3500,
                    )
                    _url_changed = True
                except Exception:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=800)
                    except Exception:
                        pass
                    await page.wait_for_timeout(300)
            else:
                try:
                    await page.wait_for_function(
                        "url => window.location.href !== url",
                        arg=_url_before_execute,
                        timeout=2500,
                    )
                    _url_changed = True
                except Exception:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=800)
                    except Exception:
                        pass
                    await page.wait_for_timeout(300)

            _url_final = page.url
            _url_changed = _url_final != _url_before_execute

            after   = await verifier.snapshot(page)
            verdict = verifier.diff(before, after)

            # For navigation (follow_link): dom_mutation/content_change without URL
            # change is a scroll artifact — treat it as no_signal (navigation failed).
            from browsermind_core.exploration.effect_verifier import EffectVerdict
            if (
                family == IntentFamily.NAVIGATION
                and not _url_changed
                and verdict.effect_type in ("dom_mutation", "content_change")
            ):
                print(
                    f"  [Action] NAVIGATION dom/content change without URL change"
                    f" — scroll artifact, overriding to no_signal"
                )
                verdict = EffectVerdict(
                    has_effect=False,
                    effect_type="no_signal",
                    confidence=0.9,
                    evidence=(
                        f"follow_link: URL unchanged ({_url_before_execute!r})"
                        f" — scroll-triggered DOM mutation, not real navigation"
                    ),
                    delta=verdict.delta,
                    quality_score=0.05,
                )

            # Classify semantic state after action
            _sem_after: Optional[dict] = None
            if state_classifier is not None:
                try:
                    _sem_after = state_classifier.classify(after, url=page.url).to_dict()
                except Exception:
                    pass

            print(
                f"  [Action] url_before={_url_before_execute[:60]!r}"
                f" url_after={_url_final[:60]!r}"
                f" url_changed={_url_changed}"
            )
            print(
                f"  [EffectVerifier] effect_type={verdict.effect_type!r}"
                f" confidence={verdict.confidence:.2f}"
                f" quality={verdict.quality_score:.2f}"
                f" evidence={verdict.evidence!r}"
            )

            return FailureAttribution(
                step_seq=seq,
                action_type="submit",
                role=role,
                name=name,
                predicted_tier="UNKNOWN",
                predicted_score=0.0,
                actual_outcome=verdict.outcome_label,
                failure_reason=verdict.failure_reason,
                resolved_by="affordance_executor",
                execution_success=verdict.has_effect,
                effect_type=verdict.effect_type,
                effect_verified=(
                    True if verdict.outcome_label in ("SUCCESS", "TRANSITION_SUCCESS") else
                    False if verdict.outcome_label == "FAILED" else None
                ),
                quality_score=verdict.quality_score,
                effect_details={
                    "delta":        verdict.delta,
                    "confidence":   verdict.confidence,
                    "evidence":     verdict.evidence,
                },
                semantic_state_before=_sem_before,
                semantic_state_after=_sem_after,
            )

        except AffordanceExecutionError as exc:
            return FailureAttribution(
                step_seq=seq,
                action_type="submit",
                role=role,
                name=affordance.type,
                predicted_tier="UNKNOWN",
                predicted_score=0.0,
                actual_outcome="FAILED",
                failure_reason=str(exc),
                resolved_by="affordance_executor",
                execution_success=False,
                semantic_state_before=_sem_before,
            )
        except Exception as exc:
            return FailureAttribution(
                step_seq=seq,
                action_type="submit",
                role=role,
                name=affordance.type,
                predicted_tier="UNKNOWN",
                predicted_score=0.0,
                actual_outcome="FAILED",
                failure_reason=f"unexpected: {exc}",
                resolved_by="affordance_executor",
                execution_success=False,
                semantic_state_before=_sem_before,
            )

    async def _observe(self, page: "Page", family: IntentFamily, url_before: str) -> str:
        try:
            url_now = page.url
            if url_now != url_before:
                return f"page navigated → {url_now}"

            if family == IntentFamily.SEARCH:
                result_count = await page.locator(
                    "[role='listitem'], .result, article, .search-result"
                ).count()
                if result_count > 0:
                    return f"results page loaded ({result_count} result items)"

            if family == IntentFamily.FORM:
                success_sels = [
                    "[class*='success']", "[class*='thank']",
                    "[role='alert']", ".alert", ".message",
                ]
                for sel in success_sels:
                    if await page.locator(sel).count() > 0:
                        return f"form response visible ({sel!r})"

            title = await page.title()
            return f"page unchanged (title={title!r})"
        except Exception as exc:
            return f"observe error: {exc}"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ok_fill(seq: int, role: str):
    from browsermind_core.ontology.p1_schemas import FailureAttribution
    return FailureAttribution(
        step_seq=seq,
        action_type="fill",
        role=role,
        name="probe_fill",
        predicted_tier="UNKNOWN",
        predicted_score=0.0,
        actual_outcome="SUCCESS",
        resolved_by="affordance_explorer",
        execution_success=True,
        effect_verified=True,
        quality_score=0.5,
    )


def _infer_experience_label(family: IntentFamily, outcome: str, observation: str) -> str:
    if outcome == "FAILED":
        return f"{family.value}_attempt_failed"

    obs_lower = observation.lower()

    if family == IntentFamily.SEARCH:
        if "navigated" in obs_lower or "results" in obs_lower:
            return "search_execution"
        return "search_interaction"

    if family == IntentFamily.FORM:
        if "navigated" in obs_lower:
            return "form_submission_redirect"
        if "success" in obs_lower or "thank" in obs_lower:
            return "form_submission_confirmed"
        return "form_interaction"

    if family == IntentFamily.FILTER:
        return "filter_applied"

    if family == IntentFamily.NAVIGATION:
        if "navigated" in obs_lower or "transition" in obs_lower:
            return "content_navigation"
        return "link_followed"

    return f"{family.value}_interaction"
