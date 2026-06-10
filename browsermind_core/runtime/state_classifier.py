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

# EffectSnapshot imported lazily to avoid circular dependency on startup
try:
    from browsermind_core.exploration.effect_verifier import EffectSnapshot
except ImportError:  # exploration layer optional at import time
    EffectSnapshot = None  # type: ignore


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# URL pattern helpers
# ---------------------------------------------------------------------------

_URL_AUTH_PATTERNS = re.compile(
    r"/(?:login|signin|sign[-_]in|log[-_]in|auth|authenticate)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_2FA_PATTERNS = re.compile(
    r"/(?:2fa|two[-_]factor|mfa|otp|verify|verification|challenge)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_DASHBOARD_PATTERNS = re.compile(
    r"/(?:dashboard|home|feed|stream|timeline|inbox|welcome)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_SEARCH_PATTERNS = re.compile(
    r"/(?:search|find|results?|query|s\b)|[?&](?:q|query|search|keyword)=",
    re.IGNORECASE,
)
_URL_CHECKOUT_PATTERNS = re.compile(
    r"/(?:checkout|cart|basket|payment|order|purchase|buy)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_LISTING_PATTERNS = re.compile(
    r"/(?:jobs?|listings?|items?|products?|posts?|articles?|detail|view)(?:/|$)",
    re.IGNORECASE,
)
_URL_PROFILE_PATTERNS = re.compile(
    r"/(?:profile|account|user|me|settings?|preferences?)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_SETTINGS_PATTERNS = re.compile(
    r"/(?:settings?|preferences?|config|options?)(?:[/?#]|$)",
    re.IGNORECASE,
)
_URL_ERROR_PATTERNS = re.compile(
    r"/(?:error|404|403|500|blocked|forbidden|not[-_]found)(?:[/?#]|$)",
    re.IGNORECASE,
)

_CONTENT_GREETING = re.compile(
    r"\b(?:welcome[, ]+|hello[, ]+|hi[, ]+|good (?:morning|afternoon|evening)[, ]+)",
    re.IGNORECASE,
)
_CONTENT_BOT_WALL = re.compile(
    r"(?:cloudflare|ddos.{0,20}protect|bot detection|are you human|not a robot|security check)",
    re.IGNORECASE,
)
_CONTENT_CAPTCHA = re.compile(
    r"(?:captcha|recaptcha|prove you.{0,10}human|i.{0,5}m not a robot)",
    re.IGNORECASE,
)
_CONTENT_AGE = re.compile(
    r"(?:age verification|must be (?:18|21)|confirm your age)",
    re.IGNORECASE,
)
_CONTENT_PAYWALL = re.compile(
    r"(?:subscribe to|upgrade (?:your )?plan|premium (?:only|required)|paywall)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# SemanticStateClassifier
# ---------------------------------------------------------------------------

class SemanticStateClassifier:
    """
    Heuristic v1 semantic state classifier.

    Takes an EffectSnapshot (already collected by EffectVerifier — no extra
    page calls) plus the current URL and returns a SemanticState.

    Target accuracy: ~70%, sufficient to unlock downstream intelligence.
    """

    def classify(
        self,
        snapshot: "EffectSnapshot",
        url: str = "",
    ) -> SemanticState:
        snippet = (snapshot.content_snippet or "").lower()
        title = (snapshot.title or "").lower()

        auth_level, auth_conf = self._infer_auth(snapshot, url, snippet, title)
        page_context, ctx_conf = self._infer_context(snapshot, url, snippet)
        form_state = self._infer_form(snapshot)
        blockers = self._detect_blockers(snapshot, url, snippet)
        progress = self._detect_progress(snapshot, page_context)
        confidence = (auth_conf + ctx_conf) / 2.0

        return SemanticState(
            auth_level=auth_level,
            page_context=page_context,
            form_state=form_state,
            blockers=blockers,
            progress_markers=progress,
            confidence=confidence,
            classified_at=_utc_now(),
        )

    # ------------------------------------------------------------------
    # Auth-level inference
    # ------------------------------------------------------------------

    def _infer_auth(
        self,
        snapshot: "EffectSnapshot",
        url: str,
        snippet: str,
        title: str,
    ) -> Tuple[str, float]:
        if _URL_2FA_PATTERNS.search(url):
            return "requires_2fa", 0.95

        if _URL_AUTH_PATTERNS.search(url):
            return "unauthenticated", 0.9

        if _URL_DASHBOARD_PATTERNS.search(url) and snapshot.error_alert_count == 0:
            return "authenticated", 0.8

        if _CONTENT_GREETING.search(snippet) or _CONTENT_GREETING.search(title):
            return "authenticated", 0.75

        if snapshot.success_alert_count > 0 and snapshot.form_count > 0:
            # Form just submitted successfully — likely just authenticated
            return "authenticated", 0.70

        return "unknown", 0.4

    # ------------------------------------------------------------------
    # Page context inference
    # ------------------------------------------------------------------

    def _infer_context(
        self,
        snapshot: "EffectSnapshot",
        url: str,
        snippet: str,
    ) -> Tuple[str, float]:
        # Error states take priority
        if snapshot.error_alert_count > 0 or _URL_ERROR_PATTERNS.search(url):
            return "error", 0.9

        # Checkout flow
        if _URL_CHECKOUT_PATTERNS.search(url):
            return "checkout", 0.9

        # Settings/preferences — check before profile (more specific)
        if _URL_SETTINGS_PATTERNS.search(url):
            return "settings", 0.85

        # Profile
        if _URL_PROFILE_PATTERNS.search(url):
            return "profile", 0.8

        # Search results
        if _URL_SEARCH_PATTERNS.search(url) or snapshot.result_count > 0:
            return "search_results", 0.85

        # Item listing
        if _URL_LISTING_PATTERNS.search(url):
            return "item_listing", 0.8

        # Form active — any form present (validation errors boost confidence)
        if snapshot.form_count > 0:
            conf = 0.85 if snapshot.validation_count > 0 else 0.70
            return "form_active", conf

        # Content feed (many list items, no form)
        if snapshot.list_item_count > 5 and snapshot.form_count == 0:
            return "content_feed", 0.7

        # Dashboard (post-auth landing pages)
        if _URL_DASHBOARD_PATTERNS.search(url):
            return "dashboard", 0.75

        # Landing page heuristic
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path.rstrip("/")
            if path == "" or path == "/":
                return "landing", 0.75
        except Exception:
            pass

        return "unknown", 0.4

    # ------------------------------------------------------------------
    # Form state inference
    # ------------------------------------------------------------------

    def _infer_form(self, snapshot: "EffectSnapshot") -> str:
        if snapshot.validation_count > 0:
            return "validation_error"
        if snapshot.success_alert_count > 0:
            return "submitted"
        if snapshot.form_count > 0:
            return "filling"
        return "idle"

    # ------------------------------------------------------------------
    # Blocker detection
    # ------------------------------------------------------------------

    def _detect_blockers(
        self,
        snapshot: "EffectSnapshot",
        url: str,
        snippet: str,
    ) -> List[str]:
        blockers: List[str] = []
        text = snippet + " " + url.lower()

        if _CONTENT_CAPTCHA.search(text):
            blockers.append("captcha")

        if _CONTENT_BOT_WALL.search(text):
            blockers.append("bot_wall")

        if _CONTENT_AGE.search(text):
            blockers.append("age_verification")

        if _CONTENT_PAYWALL.search(text) and snapshot.error_alert_count > 0:
            blockers.append("paywall")

        # Crude rate-limit signal: many alerts in a small page
        if snapshot.alert_count > 3 and snapshot.element_count < 50:
            blockers.append("rate_limited")

        return blockers

    # ------------------------------------------------------------------
    # Progress detection
    # ------------------------------------------------------------------

    def _detect_progress(
        self,
        snapshot: "EffectSnapshot",
        page_context: str,
    ) -> List[str]:
        markers: List[str] = []

        if snapshot.result_count > 0:
            markers.append("results_visible")

        if snapshot.list_item_count > 0 and page_context == "search_results":
            markers.append("search_executed")

        if snapshot.success_alert_count > 0:
            if page_context in ("landing", "form_active", "unknown"):
                markers.append("auth_complete")
            else:
                markers.append("form_filled")

        return markers
