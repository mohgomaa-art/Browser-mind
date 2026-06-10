from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

AUTH_LEVELS = (
    "unauthenticated",
    "authenticated",
    "requires_2fa",
    "requires_elevation",
    "session_expired",
    "partially_authenticated",   # e.g. email entered, password step pending
    "guest",                     # explicit guest checkout / guest mode
    "unknown",
)

PAGE_CONTEXTS = (
    "landing",
    "dashboard",
    "search_results",
    "item_listing",
    "form_active",
    "checkout",
    "profile",
    "error",
    "content_feed",
    "settings",
    # Phase 2 additions
    "modal_open",            # a dialog/modal overlay is active
    "multi_step_wizard",     # wizard/stepper UI (step 1/3, etc.)
    "confirmation_page",     # "order confirmed", "thank you", post-submit success
    "notification_center",   # notifications / messages inbox
    "onboarding",            # new-user first-run flow
    "pricing_page",          # subscription/pricing tiers
    "terms_page",            # ToS / privacy policy page
    "upload_zone",           # primary file-upload interface
    "table_view",            # data table / spreadsheet UI
    "unknown",
)

FORM_STATES = (
    "idle",
    "filling",
    "validation_error",
    "submitted",
    "multi_step",    # wizard / multi-step form — not yet on final step
    "review",        # review / confirm step before final submit
    "processing",    # submitted; spinner / loading indicator visible
    "unknown",
)

KNOWN_BLOCKERS = (
    "captcha",
    "bot_wall",
    "paywall",
    "age_verification",
    "rate_limited",
    "geo_restriction",   # access denied from this region
    "ip_blocked",        # IP-level block
    "maintenance_mode",  # site is under scheduled maintenance
)

PROGRESS_MARKERS = (
    "search_executed",
    "results_visible",
    "item_selected",
    "cart_filled",
    "auth_complete",
    "form_filled",
    "file_uploaded",
    # Phase 2 additions
    "checkout_initiated",
    "payment_entered",
    "account_created",
    "profile_updated",
    "wizard_advanced",
)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# SemanticState
# ---------------------------------------------------------------------------

@dataclass
class SemanticState:
    """
    The semantic situation the system is in — not a DOM snapshot.

    fingerprint == "auth_level:page_context" is the canonical node name
    for the Semantic State Transition Graph.
    """

    auth_level: str = "unknown"
    page_context: str = "unknown"
    form_state: str = "unknown"
    blockers: List[str] = field(default_factory=list)
    progress_markers: List[str] = field(default_factory=list)
    confidence: float = 0.5
    classified_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def fingerprint(self) -> str:
        """Canonical SSTG node name, e.g. 'authenticated:search_results'."""
        return f"{self.auth_level}:{self.page_context}"

    @property
    def is_unknown(self) -> bool:
        return self.auth_level == "unknown" and self.page_context == "unknown"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "auth_level": self.auth_level,
            "page_context": self.page_context,
            "form_state": self.form_state,
            "blockers": list(self.blockers),
            "progress_markers": list(self.progress_markers),
            "confidence": self.confidence,
            "classified_at": self.classified_at.isoformat() if self.classified_at else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticState":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        if "classified_at" in filtered and isinstance(filtered["classified_at"], str):
            try:
                filtered["classified_at"] = datetime.fromisoformat(filtered["classified_at"])
            except (ValueError, TypeError):
                filtered["classified_at"] = None
        return cls(**filtered)

    def __repr__(self) -> str:
        blockers = f" [{','.join(self.blockers)}]" if self.blockers else ""
        return (
            f"SemanticState({self.fingerprint!r}"
            f" form={self.form_state!r}"
            f"{blockers}"
            f" conf={self.confidence:.2f})"
        )
