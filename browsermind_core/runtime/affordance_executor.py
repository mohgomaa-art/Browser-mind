"""
AffordanceExecutor — WR-IR Phase 2

Executes a semantic Affordance on the current page.

Design principles:
  - Takes Affordance(type="submit_search") — NOT "keyboard_enter"
  - Re-inspects page state at execution time to pick the best execution strategy
  - Completely decoupled from TargetResolver (called only from ReplayEngine)
  - Execution strategies are ordered by reliability, not site-specific rules

Separation from AffordanceDiscoverer:
  Discovery = "What does the page offer?" (returns affordance type)
  Execution = "How do we realize this affordance right now?" (picks strategy)

This separation is critical for WR-X: the same Affordance("submit_search")
executes differently on DDG (Enter), GitHub (click dialog button), Brave (submit).
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from browsermind_core.runtime.affordance import Affordance

if TYPE_CHECKING:
    from playwright.async_api import Page


class AffordanceExecutionError(Exception):
    """Raised when all execution strategies for an affordance are exhausted."""
    pass


class AffordanceExecutor:
    """
    Executes a semantic Affordance using the best available strategy.

    Called by ReplayEngine when ResolutionResult.mode == "affordance".
    Must never be called from TargetResolver.
    """

    async def execute(self, page: "Page", affordance: Affordance) -> bool:
        """
        Execute the given affordance on the page.

        Returns True on success, raises AffordanceExecutionError on full failure.
        """
        atype = affordance.type

        if atype == "submit_search":
            return await self._execute_submit_search(page, affordance)

        elif atype == "submit_auth":
            return await self._execute_submit_auth(page, affordance)

        elif atype in ("submit_form", "generic_submit"):
            return await self._execute_submit_form(page, affordance)

        elif atype == "fill_search_query":
            return await self._execute_fill_search_query(page, affordance)

        elif atype == "fill_credential":
            return await self._execute_fill_credential(page, affordance)

        elif atype == "apply_filter":
            return await self._execute_apply_filter(page, affordance)

        elif atype == "follow_link":
            return await self._execute_follow_link(page, affordance)

        else:
            raise AffordanceExecutionError(f"No execution strategy for affordance type: {atype!r}")

    # ------------------------------------------------------------------
    # submit_search — ordered by reliability
    # ------------------------------------------------------------------

    async def _execute_submit_search(self, page: "Page", affordance: Affordance) -> bool:
        """
        Strategies for submit_search (ordered by reliability):

        S1: Press Enter on currently focused text input
            → Most reliable: the input is still active from the fill step
            → Works on: DDG (combobox+form), PyPI (#search), Python.org (#id-search-field)

        S2: Click pre-discovered submit button (if locator is set and visible)
            → Works on: sites with explicit search buttons

        S3: Find any visible submit button and click it
            → Fallback: wider search

        S4: Find form containing visible text input and requestSubmit()
            → Last resort: form-level submission
        """

        # S1: Focused input → Enter
        active_ok = await self._try_enter_on_focused(page)
        if active_ok:
            return True

        # S2: Pre-discovered locator
        if affordance.locator:
            try:
                signal = affordance.evidence.get("signal", "")
                if "submit_button" in signal:
                    if await affordance.locator.is_visible():
                        await affordance.locator.click()
                        return True
                elif "form" in signal:
                    await affordance.locator.evaluate("el => el.requestSubmit()")
                    return True
            except Exception:
                pass

        # S3: Any visible submit button
        for sel in ["button[type='submit']", "input[type='submit']"]:
            try:
                loc = page.locator(sel)
                count = await loc.count()
                for i in range(min(count, 3)):
                    btn = loc.nth(i)
                    if await btn.is_visible():
                        await btn.click()
                        return True
            except Exception:
                continue

        # S4: Form with visible input → requestSubmit
        try:
            forms = page.locator("form")
            fcount = await forms.count()
            for i in range(min(fcount, 3)):
                form = forms.nth(i)
                has_input = await form.locator(
                    "input[type='text'], input[type='search']"
                ).count()
                if has_input > 0:
                    await form.evaluate("el => el.requestSubmit()")
                    return True
        except Exception:
            pass

        raise AffordanceExecutionError("submit_search: all strategies exhausted")

    # ------------------------------------------------------------------
    # submit_auth
    # ------------------------------------------------------------------

    async def _execute_submit_auth(self, page: "Page", affordance: Affordance) -> bool:
        # S1: Enter on focused input (e.g., password field)
        active_ok = await self._try_enter_on_focused(page)
        if active_ok:
            return True

        # S2: Pre-discovered submit button
        if affordance.locator:
            try:
                if await affordance.locator.is_visible():
                    await affordance.locator.click()
                    return True
            except Exception:
                pass

        # S3: Any submit button
        try:
            btn = page.locator("button[type='submit']").first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return True
        except Exception:
            pass

        raise AffordanceExecutionError("submit_auth: all strategies exhausted")

    # ------------------------------------------------------------------
    # submit_form (generic)
    # ------------------------------------------------------------------

    async def _execute_submit_form(self, page: "Page", affordance: Affordance) -> bool:
        if affordance.locator:
            try:
                if await affordance.locator.is_visible():
                    await affordance.locator.click()
                    return True
            except Exception:
                pass

        active_ok = await self._try_enter_on_focused(page)
        if active_ok:
            return True

        raise AffordanceExecutionError("submit_form: all strategies exhausted")

    # ------------------------------------------------------------------
    # fill_search_query
    # ------------------------------------------------------------------

    async def _execute_fill_search_query(self, page: "Page", affordance: Affordance) -> bool:
        if affordance.locator:
            try:
                if await affordance.locator.is_visible():
                    await affordance.locator.click()
                    return True
            except Exception:
                pass
        raise AffordanceExecutionError("fill_search_query: no locator provided")

    # ------------------------------------------------------------------
    # fill_credential
    # ------------------------------------------------------------------

    async def _execute_fill_credential(self, page: "Page", affordance: Affordance) -> bool:
        if affordance.locator:
            try:
                if await affordance.locator.is_visible():
                    await affordance.locator.click()
                    return True
            except Exception:
                pass
        raise AffordanceExecutionError("fill_credential: no locator provided")

    # ------------------------------------------------------------------
    # apply_filter
    # ------------------------------------------------------------------

    async def _execute_apply_filter(self, page: "Page", affordance: Affordance) -> bool:
        """
        Strategies for apply_filter (ordered by reliability):

        S1: Pre-discovered locator (select or checkbox from AffordanceDiscoverer)
        S2: Any visible <select> dropdown — select first non-placeholder option
        S3: First visible filter checkbox (name/class contains "filter")
        S4: Broader checkbox sweep (any visible unchecked checkbox)
        """

        # S1: Pre-discovered locator
        if affordance.locator:
            try:
                if await affordance.locator.is_visible():
                    tag = await affordance.locator.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        await affordance.locator.select_option(index=1)
                    else:
                        await affordance.locator.click()
                    return True
            except Exception:
                pass

        # S2: Any visible <select> — select first non-placeholder option
        try:
            selects = page.locator("select")
            s_count = await selects.count()
            for i in range(min(s_count, 3)):
                sel = selects.nth(i)
                if await sel.is_visible():
                    options = await sel.evaluate(
                        "el => Array.from(el.options).map(o => o.value)"
                    )
                    non_empty = [v for v in options if v.strip()]
                    if len(non_empty) > 1:
                        await sel.select_option(value=non_empty[1])
                        return True
        except Exception:
            pass

        # S3: Filter checkboxes by name/class
        try:
            checkboxes = page.locator(
                "input[type='checkbox'][name*='filter' i], "
                "input[type='checkbox'][class*='filter' i]"
            )
            cb_count = await checkboxes.count()
            for i in range(min(cb_count, 3)):
                cb = checkboxes.nth(i)
                if await cb.is_visible():
                    await cb.click()
                    return True
        except Exception:
            pass

        # S4: Any visible unchecked checkbox
        try:
            checkboxes = page.locator("input[type='checkbox']")
            cb_count = await checkboxes.count()
            for i in range(min(cb_count, 5)):
                cb = checkboxes.nth(i)
                if await cb.is_visible():
                    checked = await cb.is_checked()
                    if not checked:
                        await cb.click()
                        return True
        except Exception:
            pass

        raise AffordanceExecutionError("apply_filter: all strategies exhausted")

    # ------------------------------------------------------------------
    # Shared utility
    # ------------------------------------------------------------------

    async def _try_enter_on_focused(self, page: "Page") -> bool:
        """
        If the currently focused element is a text/search input (or combobox),
        press Enter. This is the most reliable strategy for form submission
        after a fill action.
        """
        try:
            active_info = await page.evaluate("""() => {
                const el = document.activeElement;
                if (!el) return null;
                return {
                    tag:  el.tagName.toUpperCase(),
                    type: (el.type || '').toLowerCase(),
                    role: (el.getAttribute('aria-role') || el.getAttribute('role') || '').toLowerCase()
                };
            }""")

            if not active_info:
                return False

            tag  = active_info.get("tag", "")
            typ  = active_info.get("type", "")
            role = active_info.get("role", "")

            is_submittable = (
                tag in ("INPUT", "TEXTAREA") and typ in ("text", "search", "email", "password", "")
            ) or role in ("textbox", "searchbox", "combobox")

            if is_submittable:
                await page.keyboard.press("Enter")
                # Allow page to react
                await page.wait_for_timeout(200)
                return True

        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # follow_link — content navigation
    # ------------------------------------------------------------------

    async def _execute_follow_link(self, page: "Page", affordance: Affordance) -> bool:
        """
        Navigate to a content link.

        Strategies (ordered by reliability):
        L1: Click the pre-discovered locator (set by AffordanceDiscoverer)
        L2: Re-discover using the selector stored in evidence and click first match
        L3: Click the first visible <a> with real href that navigates to a different URL

        Pre-flight: every candidate link is filtered for:
          - href must be non-empty, not "#", not "javascript:", not same as current URL
          - target must not be "_blank"
        This prevents scroll-triggered lazy-loading from producing false SUCCESS signals.
        """
        current_url = page.url
        current_base = current_url.split('#')[0].rstrip('/')

        async def _is_new_tab_link(loc) -> bool:
            try:
                return await loc.get_attribute("target") == "_blank"
            except Exception:
                return False

        async def _href_is_navigable(loc) -> str:
            """Return the href if it would navigate away, else empty string."""
            try:
                href = (await loc.get_attribute("href") or "").strip()
            except Exception:
                return ""
            if not href:
                return ""
            if href.startswith("#") or href.startswith("javascript:"):
                return ""
            # Resolve relative → absolute for comparison
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(current_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            href_base = href.split('#')[0].rstrip('/')
            if href_base == current_base:
                return ""  # would stay on same page
            return href

        # L1: Pre-discovered locator
        if affordance.locator:
            try:
                href = await _href_is_navigable(affordance.locator)
                if await affordance.locator.is_visible() and href:
                    if not await _is_new_tab_link(affordance.locator):
                        print(f"    [follow_link/L1] href={href!r} clicking with nav guard")
                        try:
                            async with page.expect_navigation(timeout=8000, wait_until="domcontentloaded"):
                                await affordance.locator.click()
                            print(f"    [follow_link/L1] nav guard succeeded → {page.url!r}")
                            return True
                        except Exception as _e1:
                            print(f"    [follow_link/L1] nav guard failed ({_e1.__class__.__name__}), trying SPA fallback")
                            # SPA fallback — only if URL actually changes
                            try:
                                _url_pre = page.url
                                await affordance.locator.click()
                                await page.wait_for_timeout(1500)
                                if page.url != _url_pre:
                                    print(f"    [follow_link/L1-spa] URL changed → {page.url!r}")
                                    return True
                                else:
                                    print(f"    [follow_link/L1-spa] URL unchanged after click, skipping")
                            except Exception:
                                pass
            except Exception:
                pass

        # L2: Re-discover via stored selector
        sel = (affordance.evidence or {}).get("selector")
        if sel:
            try:
                loc = page.locator(sel).first
                if await page.locator(sel).count() > 0:
                    href = await _href_is_navigable(loc)
                    if href and await loc.is_visible() and not await _is_new_tab_link(loc):
                        print(f"    [follow_link/L2] sel={sel!r} href={href!r}")
                        try:
                            async with page.expect_navigation(timeout=8000, wait_until="domcontentloaded"):
                                await loc.click()
                            print(f"    [follow_link/L2] nav guard succeeded → {page.url!r}")
                            return True
                        except Exception:
                            _url_pre = page.url
                            await loc.click()
                            await page.wait_for_timeout(1500)
                            if page.url != _url_pre:
                                print(f"    [follow_link/L2-spa] URL changed → {page.url!r}")
                                return True
                            else:
                                print(f"    [follow_link/L2-spa] URL unchanged, skipping")
            except Exception:
                pass

        # L3: Any visible <a> with real navigable href and text ≥ 15 chars
        _AUTH_HREF_FRAGMENTS = ("/signin", "/login", "/sign-in", "/ap/signin", "/auth/", "/oauth")
        print(f"    [follow_link/L3] scanning links on {current_url[:60]!r}")
        tried = 0
        skipped_href = 0
        skipped_text = 0
        _l4_candidates: list = []  # hrefs where click was JS-intercepted
        try:
            links = page.locator("a[href]")
            count = await links.count()
            for i in range(min(count, 30)):
                link = links.nth(i)
                try:
                    if not await link.is_visible():
                        continue
                    if await _is_new_tab_link(link):
                        continue
                    href = await _href_is_navigable(link)
                    if not href:
                        skipped_href += 1
                        continue
                    if any(frag in href.lower() for frag in _AUTH_HREF_FRAGMENTS):
                        skipped_href += 1
                        continue
                    # Re-query text directly from the Locator to avoid stale-at-evaluate
                    try:
                        text = (await link.inner_text()) or ""
                    except Exception:
                        continue
                    if len(text.strip()) < 15:
                        skipped_text += 1
                        continue
                    tried += 1
                    print(f"    [follow_link/L3] trying link[{i}] href={href!r} text={text.strip()[:40]!r}")
                    _url_pre = page.url
                    try:
                        async with page.expect_navigation(timeout=5000, wait_until="domcontentloaded"):
                            await link.click()
                        print(f"    [follow_link/L3] nav guard succeeded → {page.url!r}")
                        return True
                    except Exception:
                        await page.wait_for_timeout(1000)
                        if page.url != _url_pre:
                            print(f"    [follow_link/L3-spa] URL changed → {page.url!r}")
                            return True
                        print(f"    [follow_link/L3] link[{i}] JS-intercepted, queueing for L4 goto")
                        _l4_candidates.append(href)
                except Exception:
                    continue
        except Exception:
            pass

        print(
            f"    [follow_link/L3] exhausted: tried={tried} skipped_href={skipped_href}"
            f" skipped_text={skipped_text} l4_candidates={len(_l4_candidates)}"
        )

        # L4: Direct page.goto() — bypasses JavaScript link interception.
        # Used when L3 found valid hrefs but click was intercepted by JS (URL unchanged).
        if _l4_candidates:
            print(f"    [follow_link/L4] trying direct goto for {len(_l4_candidates)} JS-intercepted link(s)")
            for href in _l4_candidates[:5]:
                try:
                    print(f"    [follow_link/L4] goto {href!r}")
                    await page.goto(href, wait_until="domcontentloaded", timeout=10000)
                    if page.url.split('#')[0].rstrip('/') != current_base:
                        print(f"    [follow_link/L4] succeeded → {page.url!r}")
                        return True
                    print(f"    [follow_link/L4] URL still same after goto")
                except Exception as _e4:
                    print(f"    [follow_link/L4] goto failed: {_e4.__class__.__name__}")
                    continue

        raise AffordanceExecutionError("follow_link: all strategies exhausted")
