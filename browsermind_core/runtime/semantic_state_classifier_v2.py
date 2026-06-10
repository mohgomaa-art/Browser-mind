"""
semantic_state_classifier_v2.py — L7 Semantic State Classifier v2.

Uses PageStateSignals (rich JS extraction) instead of the thin EffectSnapshot.

Key improvements over v1:
  - Auth inference uses structural signals (logout link, avatar, session cookie)
    rather than just URL patterns + greetings → ~85% accuracy target vs ~70%
  - 10 new PAGE_CONTEXTS from the expanded vocabulary
  - Blocker detection uses JS signals (has_captcha etc.) not regex-on-snippet
  - Wizard / multi-step form detection
  - Modal / dialog overlay detection
  - Backward-compatible: classify_snapshot() shim wraps EffectSnapshot for
    callers that haven't been updated (ReplayEngine v1 path)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from browsermind_core.ontology.semantic_state import (
    AUTH_LEVELS,
    FORM_STATES,
    KNOWN_BLOCKERS,
    PAGE_CONTEXTS,
    PROGRESS_MARKERS,
    SemanticState,
)
from browsermind_core.runtime.page_state_extractor import PageStateSignals


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# URL pattern helpers (kept for fallback; live signals take priority)
# ---------------------------------------------------------------------------

_URL_AUTH  = re.compile(r"/(?:login|signin|sign[-_]in|log[-_]in|auth(?:enticate)?)(?:[/?#]|$)", re.I)
_URL_2FA   = re.compile(r"/(?:2fa|two[-_]factor|mfa|otp|verify|verification|challenge)(?:[/?#]|$)", re.I)
_URL_DASH  = re.compile(r"/(?:dashboard|home|feed|stream|timeline|inbox|welcome)(?:[/?#]|$)", re.I)
_URL_SEARCH= re.compile(r"/(?:search|find|results?|query|s\b)|[?&](?:q|query|search|keyword)=", re.I)
_URL_CHECK = re.compile(r"/(?:checkout|cart|basket|payment|order|purchase|buy)(?:[/?#]|$)", re.I)
_URL_LIST  = re.compile(r"/(?:jobs?|listings?|items?|products?|posts?|articles?|detail|view)(?:/|$)", re.I)
_URL_PROF  = re.compile(r"/(?:profile|account|user|me|settings?|preferences?)(?:[/?#]|$)", re.I)
_URL_SET   = re.compile(r"/(?:settings?|preferences?|config|options?)(?:[/?#]|$)", re.I)
_URL_ERR   = re.compile(r"/(?:error|404|403|500|blocked|forbidden|not[-_]found)(?:[/?#]|$)", re.I)
_URL_PRICE = re.compile(r"/(?:pricing?|plans?|upgrade|subscription)(?:[/?#]|$)", re.I)
_URL_TOC   = re.compile(r"/(?:terms|tos|privacy|legal|cookie[-_]policy)(?:[/?#]|$)", re.I)
_URL_ONBOARD = re.compile(r"/(?:onboarding|welcome|setup|get[-_]started)(?:[/?#]|$)", re.I)


class SemanticStateClassifierV2:
    """
    Heuristic v2 semantic state classifier driven by PageStateSignals.

    Usage (live page):
        extractor = PageStateExtractor()
        signals = await extractor.extract(page)
        state = SemanticStateClassifierV2().classify(signals)

    Usage (EffectSnapshot fallback — v1 shim):
        state = SemanticStateClassifierV2().classify_snapshot(snapshot, url=url)
    """

    def classify(self, signals: PageStateSignals) -> SemanticState:
        url     = signals.url or ""
        snippet = (signals.content_snippet or "").lower()
        title   = (signals.title or "").lower()

        auth_level, auth_conf = self._infer_auth(signals, url, snippet, title)
        page_context, ctx_conf = self._infer_context(signals, url, snippet)
        form_state = self._infer_form(signals)
        blockers   = self._detect_blockers(signals, url, snippet)
        progress   = self._detect_progress(signals, page_context)
        confidence = round((auth_conf * 0.4 + ctx_conf * 0.6), 3)

        return SemanticState(
            auth_level=auth_level,
            page_context=page_context,
            form_state=form_state,
            blockers=blockers,
            progress_markers=progress,
            confidence=confidence,
            classified_at=_utc_now(),
        )

    def classify_snapshot(self, snapshot, url: str = "") -> SemanticState:
        """Backward-compatible shim — wraps EffectSnapshot into PageStateSignals."""
        from browsermind_core.runtime.page_state_extractor import PageStateSignals as _PS
        sig = _PS(
            url=url,
            title=getattr(snapshot, "title", ""),
            element_count=getattr(snapshot, "element_count", 0),
            form_count=getattr(snapshot, "form_count", 0),
            list_item_count=getattr(snapshot, "list_item_count", 0),
            result_count=getattr(snapshot, "result_count", 0),
            alert_count=getattr(snapshot, "alert_count", 0),
            success_alert_count=getattr(snapshot, "success_alert_count", 0),
            error_alert_count=getattr(snapshot, "error_alert_count", 0),
            validation_count=getattr(snapshot, "validation_count", 0),
            content_snippet=getattr(snapshot, "content_snippet", ""),
            snapshot_ok=getattr(snapshot, "snapshot_ok", True),
        )
        return self.classify(sig)

    # ------------------------------------------------------------------ #
    # Auth-level inference (priority ordered)                              #
    # ------------------------------------------------------------------ #

    def _infer_auth(
        self,
        s: PageStateSignals,
        url: str,
        snippet: str,
        title: str,
    ) -> Tuple[str, float]:
        # 2FA — strongest URL signal
        if _URL_2FA.search(url):
            return "requires_2fa", 0.95

        # Explicit logout link — user is authenticated
        if s.has_logout_link:
            return "authenticated", 0.95

        # Avatar + session cookie = authenticated
        if s.has_user_avatar and s.has_session_cookie:
            return "authenticated", 0.90

        # Username display = authenticated
        if s.has_username_display:
            return "authenticated", 0.88

        # Session cookie alone (many SPAs don't render logout button on every page)
        if s.has_session_cookie:
            return "authenticated", 0.75

        # Login form present = user is unauthenticated
        if s.has_login_form or s.password_field_count > 0:
            return "unauthenticated", 0.90

        # URL-based fallbacks
        if _URL_AUTH.search(url):
            return "unauthenticated", 0.85

        if _URL_DASH.search(url) and s.error_alert_count == 0:
            return "authenticated", 0.75

        # Dashboard URL + no login form = likely authenticated
        if s.has_user_avatar:
            return "authenticated", 0.70

        return "unknown", 0.35

    # ------------------------------------------------------------------ #
    # Page context inference                                               #
    # ------------------------------------------------------------------ #

    def _infer_context(
        self,
        s: PageStateSignals,
        url: str,
        snippet: str,
    ) -> Tuple[str, float]:
        # --- Highest-priority structural signals ---

        # Visible dialog / modal
        if s.has_visible_dialog or s.has_visible_modal:
            return "modal_open", 0.95

        # Confirmation page (post-submit success)
        if s.has_confirmation_heading or s.has_order_number:
            return "confirmation_page", 0.92

        # Error states
        if s.error_alert_count > 0 or _URL_ERR.search(url):
            return "error", 0.88

        # Maintenance mode
        if s.has_maintenance:
            return "error", 0.90

        # Wizard / multi-step
        if s.has_stepper and s.stepper_step_count > 1:
            return "multi_step_wizard", 0.90

        # Pricing page
        if s.has_pricing_tiers or _URL_PRICE.search(url):
            return "pricing_page", 0.88

        # Onboarding
        if s.has_onboarding_cue or _URL_ONBOARD.search(url):
            return "onboarding", 0.85

        # Terms / legal
        if _URL_TOC.search(url):
            return "terms_page", 0.90

        # Upload zone
        if s.has_dropzone or (s.file_input_count > 0 and s.form_count == 1):
            return "upload_zone", 0.85

        # Checkout
        if _URL_CHECK.search(url):
            return "checkout", 0.90

        # Settings — check before profile (more specific)
        if _URL_SET.search(url):
            return "settings", 0.85

        # Profile
        if _URL_PROF.search(url):
            return "profile", 0.80

        # Data table / spreadsheet
        if s.table_count > 0 and s.table_count >= s.form_count:
            return "table_view", 0.80

        # Search results
        if _URL_SEARCH.search(url) or s.result_count > 0:
            return "search_results", 0.85

        # Item listing
        if _URL_LIST.search(url):
            return "item_listing", 0.80

        # Active form
        if s.form_count > 0:
            conf = 0.85 if s.validation_count > 0 else 0.70
            return "form_active", conf

        # Content feed (many list items, no form)
        if s.list_item_count > 5 and s.form_count == 0:
            return "content_feed", 0.72

        # Dashboard
        if _URL_DASH.search(url):
            return "dashboard", 0.75

        # Landing page (root path)
        if s.path in ("", "/"):
            return "landing", 0.75

        return "unknown", 0.35

    # ------------------------------------------------------------------ #
    # Form state inference                                                 #
    # ------------------------------------------------------------------ #

    def _infer_form(self, s: PageStateSignals) -> str:
        if s.has_stepper and s.stepper_step_count > 1:
            return "multi_step"
        if s.validation_count > 0:
            return "validation_error"
        if s.success_alert_count > 0:
            return "submitted"
        if s.has_confirmation_heading:
            return "submitted"
        if s.form_count > 0 and s.submit_button_count > 0:
            return "filling"
        return "idle"

    # ------------------------------------------------------------------ #
    # Blocker detection                                                    #
    # ------------------------------------------------------------------ #

    def _detect_blockers(
        self, s: PageStateSignals, url: str, snippet: str
    ) -> List[str]:
        blockers: List[str] = []
        if s.has_captcha:
            blockers.append("captcha")
        if s.has_bot_wall:
            blockers.append("bot_wall")
        if s.has_age_gate:
            blockers.append("age_verification")
        if s.has_paywall:
            blockers.append("paywall")
        if s.has_maintenance:
            blockers.append("maintenance_mode")
        if s.has_geo_block:
            blockers.append("geo_restriction")
        # Rate-limit heuristic: many alerts + tiny page
        if s.alert_count > 3 and s.element_count < 50:
            blockers.append("rate_limited")
        return blockers

    # ------------------------------------------------------------------ #
    # Progress detection                                                   #
    # ------------------------------------------------------------------ #

    def _detect_progress(
        self, s: PageStateSignals, page_context: str
    ) -> List[str]:
        markers: List[str] = []

        if s.result_count > 0:
            markers.append("results_visible")

        if s.list_item_count > 0 and page_context == "search_results":
            markers.append("search_executed")

        if s.success_alert_count > 0:
            if page_context in ("landing", "form_active", "unknown"):
                markers.append("auth_complete")
            else:
                markers.append("form_filled")

        if page_context == "confirmation_page":
            markers.append("form_filled")
            if s.has_order_number:
                markers.append("checkout_initiated")

        if page_context == "multi_step_wizard" and s.stepper_current_step > 0:
            markers.append("wizard_advanced")

        if s.file_input_count > 0 and s.success_alert_count > 0:
            markers.append("file_uploaded")

        return markers
