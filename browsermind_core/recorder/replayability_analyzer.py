"""
ReplayabilityAnalyzer — P3.1

Pure observation. No rejection. No healing.
Takes a compiled step dict and produces a ReplayabilityAssessment.

Rules are deliberately simple until we have real dataset to validate them.
A complex scoring formula built before we have data is worse than no formula.
"""
from __future__ import annotations

from typing import Any, Dict, List


# The only three tiers. Period.
TIER_HIGH        = "HIGH"
TIER_AMBIGUOUS   = "AMBIGUOUS"
TIER_UNREPLAYABLE = "UNREPLAYABLE"

# Simple score anchors (not a weighted formula — just rough ordinal signals)
_SCORE_HIGH        = 0.90
_SCORE_AMBIGUOUS   = 0.50
_SCORE_UNREPLAYABLE = 0.10


class ReplayabilityAnalyzer:
    """
    Observational analyzer. Produces a prediction per step.
    Does NOT modify steps. Does NOT reject steps. Does NOT fix anything.
    """

    def assess(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assess a single compiled step.

        Returns a dict matching the ReplayabilityAssessment schema:
          { tier, score, reasons }
        """
        role      = (step.get("target_role") or "").lower()
        name      = (step.get("target_name") or "").strip()
        action    = (step.get("action_type") or "").lower()

        # Pull descriptor and evidence if present (set by JS observer in P3.1+)
        descriptor = step.get("descriptor") or {}
        evidence   = step.get("recording_evidence") or {}

        accessible_name  = (descriptor.get("accessible_name") or "").strip()
        text_content     = (descriptor.get("text_content") or "").strip()
        placeholder      = (descriptor.get("placeholder") or "").strip()
        candidate_count  = int(evidence.get("candidate_count") or 0)

        reasons: List[str] = []

        # ------------------------------------------------------------------
        # Rule 1: Navigation and session steps are always HIGH (synthetic)
        # ------------------------------------------------------------------
        if action in ("navigate", "session"):
            return {"tier": TIER_HIGH, "score": _SCORE_HIGH, "reasons": []}

        # ------------------------------------------------------------------
        # Rule 2: Generic roles with no name at all → UNREPLAYABLE
        # ------------------------------------------------------------------
        GENERIC_ROLES_WITHOUT_NAME = {"generic", "img", "div", "span", "section", "li", "ul", "ol"}
        if role in GENERIC_ROLES_WITHOUT_NAME and not name and not accessible_name and not text_content:
            reasons.append("generic_role_with_no_name")
            return {"tier": TIER_UNREPLAYABLE, "score": _SCORE_UNREPLAYABLE, "reasons": reasons}

        # ------------------------------------------------------------------
        # Rule 3: Missing name entirely → at least AMBIGUOUS
        # ------------------------------------------------------------------
        if not name and not accessible_name:
            reasons.append("missing_name")

        # ------------------------------------------------------------------
        # Rule 4: Multiple candidates at recording time → at least AMBIGUOUS
        # ------------------------------------------------------------------
        if candidate_count > 1:
            reasons.append("multiple_candidates")

        # ------------------------------------------------------------------
        # Rule 5: Has accessible name (aria-label) → strong signal
        # ------------------------------------------------------------------
        has_strong_name = bool(accessible_name)

        # ------------------------------------------------------------------
        # Rule 6: Semantic roles with good accessible names → HIGH
        # ------------------------------------------------------------------
        STRONG_ROLES = {"button", "link", "textbox", "checkbox", "radio", "combobox"}
        if role in STRONG_ROLES and (name or accessible_name) and not reasons:
            return {"tier": TIER_HIGH, "score": _SCORE_HIGH, "reasons": []}

        # ------------------------------------------------------------------
        # Resolve tier from accumulated reasons
        # ------------------------------------------------------------------
        if not reasons:
            return {"tier": TIER_HIGH, "score": _SCORE_HIGH, "reasons": []}

        # Any UNREPLAYABLE signal already returned above.
        # Remaining reasons are AMBIGUOUS signals.
        score = _SCORE_AMBIGUOUS
        # Partial credit if at least one name source exists
        if name or accessible_name or text_content or placeholder:
            score = _SCORE_AMBIGUOUS + 0.10

        return {"tier": TIER_AMBIGUOUS, "score": score, "reasons": reasons}

    def assess_template(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Assess every step in a template. Returns list of assessments (same order)."""
        return [self.assess(step) for step in steps]
