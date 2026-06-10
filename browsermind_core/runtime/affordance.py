"""
Affordance & ResolutionResult — WR-IR Phase 2

Affordance:
  A semantic opportunity the page currently offers.
  Type = WHAT can be done (not HOW).
  Example: Affordance(type="submit_search") — NOT Affordance(type="keyboard_enter")

  AffordanceExecutor decides HOW at execution time based on current page state.

ResolutionResult:
  Replaces the tuple returned by TargetResolver.resolve().
  Either carries a Locator (mode="locator") or an Affordance (mode="affordance").

  This prevents the proliferation of:
    if locator is None and resolved_by == "affordance_intent": ...
  by making the mode explicit and typed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator


# ---------------------------------------------------------------------------
# Affordance types — semantic vocabulary (WHAT, not HOW)
# ---------------------------------------------------------------------------
# These are the only valid affordance types.
# They describe the intent the affordance fulfills,
# not the DOM interaction mechanism.

AffordanceType = Literal[
    # SEARCH family
    "submit_search",        # submit the current search query
    "fill_search_query",    # fill a search query input

    # AUTH family
    "submit_auth",          # submit authentication credentials
    "fill_credential",      # fill a credential field (email/user/password/OTP)

    # FORM family
    "submit_form",          # submit a generic form
    "confirm_action",       # confirm a destructive or multi-step action

    # NAVIGATION family
    "follow_link",          # follow a navigation link

    # FILTER family
    "apply_filter",         # select or apply a filter/sort option

    # Generic (used when family is known but affordance is ambiguous)
    "generic_submit",       # catch-all form submit
]


@dataclass
class Affordance:
    """
    A semantic affordance the page offers for a given intent.

    Attributes:
        type:       WHAT can be done (semantic, not execution primitive)
        score:      Confidence [0.0 → 1.0] that this is the right affordance
        evidence:   Dict of supporting signals discovered on the page
                    (e.g., {"has_focused_input": True, "has_submit_button": False})
        locator:    Optional — pre-discovered locator if available.
                    AffordanceExecutor MAY use it but will re-probe if None.
    """
    type:     str              # AffordanceType
    score:    float            # 0.0 → 1.0
    evidence: dict = field(default_factory=dict)
    locator:  Optional["Locator"] = None

    def __repr__(self) -> str:
        return f"Affordance(type={self.type!r}, score={self.score:.2f})"


# ---------------------------------------------------------------------------
# ResolutionResult — replaces (locator, recovered_by, resolved_by, depth, count)
# ---------------------------------------------------------------------------

@dataclass
class ResolutionResult:
    """
    The output of TargetResolver.resolve().

    mode:
        "locator"    — resolved to a DOM element; locator is set
        "affordance" — resolved to a page affordance; affordance is set
        "skipped"    — step type requires no target (e.g. navigate)
        "failed"     — resolution exhausted all strategies

    Note: For mode="affordance", the ReplayEngine delegates to AffordanceExecutor
    instead of ActionExecutor. The locator field is None in this case.
    """
    mode:          Literal["locator", "affordance", "skipped", "failed"]

    # Locator path
    locator:       Optional["Locator"] = None

    # Affordance path
    affordance:    Optional[Affordance] = None

    # Common metadata (mirrors old tuple fields)
    resolved_by:   Optional[str] = None
    recovered_by:  Optional[str] = None
    depth:         Optional[int] = None
    candidate_count: int = 0

    # Failure metadata
    failure_reason: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.mode in ("locator", "affordance", "skipped")

    @property
    def is_failed(self) -> bool:
        return self.mode == "failed"

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_locator(
        cls,
        locator: "Locator",
        resolved_by: str,
        recovered_by: Optional[str] = None,
        depth: int = 0,
        candidate_count: int = 1,
    ) -> "ResolutionResult":
        return cls(
            mode="locator",
            locator=locator,
            resolved_by=resolved_by,
            recovered_by=recovered_by,
            depth=depth,
            candidate_count=candidate_count,
        )

    @classmethod
    def from_affordance(
        cls,
        affordance: Affordance,
        depth: int = 4,
    ) -> "ResolutionResult":
        return cls(
            mode="affordance",
            affordance=affordance,
            resolved_by="affordance_intent",
            depth=depth,
        )

    @classmethod
    def skipped(cls) -> "ResolutionResult":
        return cls(mode="skipped", resolved_by="navigate")

    @classmethod
    def failed(cls, reason: str) -> "ResolutionResult":
        return cls(mode="failed", failure_reason=reason)
