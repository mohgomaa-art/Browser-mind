"""
AffordanceDiscoverer — WR-IR Phase 2

Discovers what semantic affordances the current page offers for a given IntentFamily.

Enhanced with:
  - Scroll-triggered discovery (#1): scrolls before snapshotting to reveal lazy-loaded affordances
  - Hover-triggered detection (#2): checks for dropdown menus revealed on hover
  - Shadow DOM traversal (#3): evaluates shadowRoot elements where possible
  - Viewport-aware scoring (#7): above-the-fold affordances score higher

Design principles:
  - Discovery is per-IntentFamily, not per-workflow_role
  - Returns semantic Affordances (WHAT), not execution primitives (HOW)
  - AffordanceExecutor decides HOW at execution time
  - Returns empty list if family is UNKNOWN or page has no relevant affordances

Affordance scoring:
  0.9+  Very high confidence (e.g., focused input with value)
  0.7-0.9 High confidence (visible submit button in context)
  0.5-0.7 Medium confidence (form-level detection)
  <0.5  Skip — not enough signal
"""
from __future__ import annotations

from typing import List, TYPE_CHECKING

from browsermind_core.runtime.affordance import Affordance
from browsermind_core.runtime.intent_family import IntentFamily

if TYPE_CHECKING:
    from playwright.async_api import Page


class AffordanceDiscoverer:
    """
    Discovers affordances on the current page for a given IntentFamily.

    Usage:
        discoverer = AffordanceDiscoverer()
        affordances = await discoverer.discover(page, IntentFamily.SEARCH)
    """

    async def discover(self, page: "Page", family: IntentFamily) -> List[Affordance]:
        """Discover affordances. Scrolls first to reveal lazy-loaded elements."""
        if family == IntentFamily.UNKNOWN:
            return []

        # Scroll to reveal affordances before snapshotting (#1)
        await self._scroll_to_reveal(page)

        try:
            if family == IntentFamily.SEARCH:
                return await self._discover_search(page)
            elif family == IntentFamily.AUTH:
                return await self._discover_auth(page)
            elif family == IntentFamily.FORM:
                return await self._discover_form(page)
            elif family == IntentFamily.NAVIGATION:
                return await self._discover_navigation(page)
            elif family == IntentFamily.FILTER:
                return await self._discover_filter(page)
            elif family == IntentFamily.UPLOAD:
                return []
            elif family == IntentFamily.DATA_EXTRACTION:
                return []
        except Exception:
            pass

        return []

    async def _scroll_to_reveal(self, page: "Page") -> None:
        """Scroll down 40% of page height then back to top to trigger lazy loading."""
        try:
            await page.evaluate("""() => {
                const h = document.documentElement.scrollHeight;
                window.scrollTo({ top: h * 0.4, behavior: 'instant' });
            }""")
            await page.wait_for_timeout(300)
            await page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
            await page.wait_for_timeout(150)
        except Exception:
            pass

    async def _viewport_score_boost(self, page: "Page", locator) -> float:
        """Return +0.1 if element is in the viewport (above-the-fold boost)."""
        try:
            in_vp = await locator.evaluate("""el => {
                const r = el.getBoundingClientRect();
                return r.top >= 0 && r.bottom <= window.innerHeight;
            }""")
            return 0.1 if in_vp else 0.0
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    async def _discover_search(self, page: "Page") -> List[Affordance]:
        affordances: List[Affordance] = []

        # A1: Focused text/search input
        active_info = await page.evaluate("""() => {
            const el = document.activeElement;
            if (!el) return null;
            return {
                tag:      el.tagName.toUpperCase(),
                type:     (el.type || '').toLowerCase(),
                hasValue: (el.value || '').length > 0,
                role:     (el.getAttribute('aria-role') || el.getAttribute('role') || '').toLowerCase()
            };
        }""")

        if active_info:
            tag  = active_info.get("tag", "")
            typ  = active_info.get("type", "")
            role = active_info.get("role", "")
            is_text_input = (
                tag in ("INPUT", "TEXTAREA") and typ in ("text", "search", "")
            ) or role in ("textbox", "searchbox", "combobox")

            if is_text_input:
                score = 0.92 if active_info.get("hasValue") else 0.60
                affordances.append(Affordance(
                    type="submit_search",
                    score=score,
                    evidence={
                        "signal": "focused_input",
                        "has_value": active_info.get("hasValue"),
                        "input_type": typ,
                    }
                ))

        # A2: Visible submit button — but only if no password field present (auth forms excluded)
        try:
            page_has_password = await page.locator("input[type='password']").count() > 0
        except Exception:
            page_has_password = False

        if not page_has_password:
            submit_selectors = ["button[type='submit']", "input[type='submit']"]
            for sel in submit_selectors:
                loc = page.locator(sel)
                count = await loc.count()
                for i in range(min(count, 3)):
                    btn = loc.nth(i)
                    try:
                        if await btn.is_visible():
                            boost = await self._viewport_score_boost(page, btn)
                            affordances.append(Affordance(
                                type="submit_search",
                                score=0.72 + boost,
                                evidence={"signal": "visible_submit_button", "selector": sel},
                                locator=btn,
                            ))
                            break
                    except Exception:
                        continue

        # A3: Form enclosing a visible text input (skip auth forms that have password fields)
        try:
            forms = page.locator("form")
            fcount = await forms.count()
            for i in range(min(fcount, 3)):
                form = forms.nth(i)
                # Skip if this is an auth form (password field = not a search form)
                pwd_count = await form.locator("input[type='password']").count()
                if pwd_count > 0:
                    continue
                visible_inputs = form.locator("input[type='text'], input[type='search']")
                inp_count = await visible_inputs.count()
                if inp_count > 0:
                    first_input = visible_inputs.first
                    if await first_input.is_visible():
                        boost = await self._viewport_score_boost(page, first_input)
                        affordances.append(Affordance(
                            type="submit_search",
                            score=0.55 + boost,
                            evidence={"signal": "form_with_text_input", "input_count": inp_count},
                            locator=form,
                        ))
                        break
        except Exception:
            pass

        # A4: Shadow DOM — check for search inputs in shadow roots (#3)
        try:
            shadow_search = await page.evaluate("""() => {
                const found = [];
                const walk = (root) => {
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) {
                            const inp = el.shadowRoot.querySelector(
                                'input[type=search], input[aria-label*=search i]'
                            );
                            if (inp) found.push(el.tagName.toLowerCase());
                            walk(el.shadowRoot);
                        }
                    }
                };
                walk(document);
                return found.slice(0, 3);
            }""")
            if shadow_search:
                affordances.append(Affordance(
                    type="submit_search",
                    score=0.50,
                    evidence={"signal": "shadow_dom_search", "hosts": shadow_search},
                ))
        except Exception:
            pass

        return affordances

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    async def _discover_auth(self, page: "Page") -> List[Affordance]:
        affordances: List[Affordance] = []

        # A1: Focused credential input (highest confidence)
        active_info = await page.evaluate("""() => {
            const el = document.activeElement;
            if (!el) return null;
            return {tag: el.tagName.toUpperCase(), type: (el.type || '').toLowerCase()};
        }""")

        if active_info:
            tag = active_info.get("tag", "")
            typ = active_info.get("type", "")
            if tag == "INPUT" and typ in ("text", "email", "password"):
                affordances.append(Affordance(
                    type="submit_auth",
                    score=0.82,
                    evidence={"signal": "focused_credential_input", "type": typ},
                ))

        # A2: Form containing a password field — clearest possible auth signal
        try:
            pwd_inputs = page.locator("input[type='password']")
            pwd_count = await pwd_inputs.count()
            if pwd_count > 0 and await pwd_inputs.first.is_visible():
                boost = await self._viewport_score_boost(page, pwd_inputs.first)
                affordances.append(Affordance(
                    type="submit_auth",
                    score=0.88 + boost,
                    evidence={"signal": "form_with_password_field", "count": pwd_count},
                    locator=pwd_inputs.first,
                ))
        except Exception:
            pass

        # A3: Auth-labeled submit button (button or input[type=submit])
        # Covers sites that use <input type="submit"> instead of <button>
        try:
            btn_loc = page.locator("button[type='submit'], input[type='submit']").first
            if await btn_loc.count() > 0 and await btn_loc.is_visible():
                boost = await self._viewport_score_boost(page, btn_loc)
                affordances.append(Affordance(
                    type="submit_auth",
                    score=0.72 + boost,
                    evidence={"signal": "visible_submit_button"},
                    locator=btn_loc,
                ))
        except Exception:
            pass

        # A4: Auth-labeled button by text (Login, Sign in, Log in, Sign up)
        try:
            auth_labels = ["Login", "Log in", "Sign in", "Sign up", "Register", "Continue"]
            for label in auth_labels:
                loc = page.get_by_role("button", name=label, exact=False)
                if await loc.count() > 0 and await loc.first.is_visible():
                    boost = await self._viewport_score_boost(page, loc.first)
                    affordances.append(Affordance(
                        type="submit_auth",
                        score=0.80 + boost,
                        evidence={"signal": "auth_labeled_button", "label": label},
                        locator=loc.first,
                    ))
                    break
        except Exception:
            pass

        return affordances

    # ------------------------------------------------------------------
    # FORM (generic)
    # ------------------------------------------------------------------

    async def _discover_form(self, page: "Page") -> List[Affordance]:
        affordances: List[Affordance] = []

        try:
            # Skip if this is an auth form — auth family handles those
            pwd_count = await page.locator("input[type='password']").count()
            if pwd_count == 0:
                btn = page.locator("button[type='submit'], input[type='submit']").first
                if await btn.count() > 0 and await btn.is_visible():
                    boost = await self._viewport_score_boost(page, btn)
                    affordances.append(Affordance(
                        type="submit_form",
                        score=0.75 + boost,
                        evidence={"signal": "visible_submit_button"},
                        locator=btn,
                    ))
        except Exception:
            pass

        # Also detect multi-step forms by looking for "Next" / "Continue" buttons
        try:
            for label_pat in ["Next", "Continue", "Proceed"]:
                loc = page.get_by_role("button", name=label_pat, exact=False)
                if await loc.count() > 0 and await loc.first.is_visible():
                    affordances.append(Affordance(
                        type="submit_form",
                        score=0.60,
                        evidence={"signal": "multi_step_next_button", "label": label_pat},
                        locator=loc.first,
                    ))
                    break
        except Exception:
            pass

        return affordances

    # ------------------------------------------------------------------
    # NAVIGATION — content links and page traversal
    # ------------------------------------------------------------------

    async def _discover_navigation(self, page: "Page") -> List[Affordance]:
        """Discover primary navigation links — content items and hover dropdowns.

        Searches for:
          1. Content links: article/post/card/story/thread links (the main feed items)
          2. Hover-revealed dropdown menus
        This allows BrowserMind to navigate INTO content, not just search for it.
        """
        affordances: List[Affordance] = []

        # --- Content link discovery ---
        # Ordered from most-specific (high signal) to most-generic (low signal).
        content_selectors = [
            # Semantic article links
            ("article a[href]",                    "article_link",  0.70),
            ("[role='article'] a[href]",           "aria_article",  0.70),
            # Heading links (blog, news, forum threads, lobsters)
            ("h2 a[href]",                         "heading_h2",    0.68),
            ("h3 a[href]",                         "heading_h3",    0.65),
            # Class-based content patterns
            ("[class*='post'] a[href]",            "post_link",     0.65),
            ("[class*='story'] a[href]",           "story_link",    0.65),
            ("[class*='card'] a[href]",            "card_link",     0.63),
            ("[class*='feed'] a[href]",            "feed_link",     0.63),
            ("[class*='thread'] a[href]",          "thread_link",   0.65),
            ("[class*='item'] > a[href]",          "item_link",     0.60),
            ("[class*='entry'] a[href]",           "entry_link",    0.60),
            ("[class*='result'] a[href]",          "result_link",   0.62),
            # List items with relative links (lobsters, hacker-news style)
            ("li a[href^='/']",                    "list_item",     0.58),
            # Generic: any link with visible text > 15 chars (skip nav/icon links)
        ]

        for sel, signal, base_score in content_selectors:
            try:
                if await page.locator(sel).count() == 0:
                    continue
                loc = page.locator(sel).first
                if not await loc.is_visible():
                    continue
                try:
                    text = (await loc.inner_text()) or ""
                except Exception:
                    continue
                if len(text.strip()) < 8:
                    continue
                boost = await self._viewport_score_boost(page, loc)
                affordances.append(Affordance(
                    type="follow_link",
                    score=base_score + boost,
                    evidence={
                        "signal":   signal,
                        "selector": sel,
                        "text":     text[:50],
                    },
                    locator=loc,
                ))
                break  # one content-link affordance per page is enough
            except Exception:
                continue

        # If no typed content link was found, try any visible link with substantial text
        if not affordances:
            try:
                links = page.locator("a[href]")
                count = await links.count()
                for i in range(min(count, 20)):
                    link = links.nth(i)
                    try:
                        if not await link.is_visible():
                            continue
                        text = (await link.inner_text() or "").strip()
                        if len(text) >= 15:
                            boost = await self._viewport_score_boost(page, link)
                            affordances.append(Affordance(
                                type="follow_link",
                                score=0.55 + boost,
                                evidence={"signal": "generic_text_link", "text": text[:50]},
                                locator=link,
                            ))
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # --- Hover-revealed dropdown detection ---
        try:
            nav_items = page.locator("nav a, [role='navigation'] a").first
            if await nav_items.count() > 0 and await nav_items.is_visible():
                await nav_items.hover()
                await page.wait_for_timeout(200)
                dropdown = page.locator("[role='menu'], [role='listbox'], .dropdown-menu, .sub-menu")
                if await dropdown.count() > 0:
                    affordances.append(Affordance(
                        type="navigate",
                        score=0.60,
                        evidence={"signal": "hover_dropdown_revealed"},
                        locator=dropdown.first,
                    ))
        except Exception:
            pass

        return affordances

    # ------------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------------

    async def _discover_filter(self, page: "Page") -> List[Affordance]:
        affordances: List[Affordance] = []

        try:
            sel = page.locator("select").first
            if await sel.count() > 0 and await sel.is_visible():
                boost = await self._viewport_score_boost(page, sel)
                affordances.append(Affordance(
                    type="apply_filter",
                    score=0.65 + boost,
                    evidence={"signal": "visible_select"},
                    locator=sel,
                ))
        except Exception:
            pass

        # Also check checkbox filters (e.g. faceted search)
        try:
            checkboxes = page.locator("input[type='checkbox'][name*='filter' i], "
                                      "input[type='checkbox'][class*='filter' i]")
            cb_count = await checkboxes.count()
            if cb_count > 0:
                affordances.append(Affordance(
                    type="apply_filter",
                    score=0.55,
                    evidence={"signal": "checkbox_filters", "count": cb_count},
                    locator=checkboxes.first,
                ))
        except Exception:
            pass

        return affordances


def rank_affordances(affordances: List[Affordance]) -> List[Affordance]:
    return sorted(affordances, key=lambda a: a.score, reverse=True)


def best_affordance(affordances: List[Affordance], min_score: float = 0.5) -> Affordance | None:
    ranked = rank_affordances(affordances)
    if ranked and ranked[0].score >= min_score:
        return ranked[0]
    return None
