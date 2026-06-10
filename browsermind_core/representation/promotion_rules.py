"""P5G — Candidate Promotion Rules.

Defines the formal, machine-checkable criteria for promoting a candidate
state transition through the three tiers of the Birth Ledger.

These rules exist to prevent the failure mode that killed OPEN_OBJECT,
SUBMIT_QUERY, and the original Capability Taxonomy: early promotion
before the candidate has been subjected to sufficient empirical pressure.

CRITICAL DISTINCTION:
    Meeting the PRIMITIVE threshold does NOT declare a Primitive.
    It makes the candidate ELIGIBLE FOR PRIMITIVE REVIEW.
    The review is a human judgment call backed by evidence.
    Numbers qualify. They do not grant citizenship.

SOURCE DIVERSITY RULE:
    5 GitHub Issues do not count as 5 independent rediscoveries.
    Independence requires platform diversity OR family diversity.
    Rediscovery count alone is not sufficient — sources must be distinct.

Tier thresholds:
    CANDIDATE:
        rediscovery >= 1

    STRONG_CANDIDATE:
        rediscovery >= 2
        semantic_cohesion >= 0.80
        source_diversity >= 2   (2+ distinct platforms or families)

    ELIGIBLE_FOR_REVIEW:
        rediscovery >= 5
        semantic_cohesion >= 0.90
        source_diversity >= 3   (3+ distinct platforms or families)
        stress_test_passed = True
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PromotionTier(str, Enum):
    CANDIDATE           = "CANDIDATE"
    STRONG_CANDIDATE    = "STRONG_CANDIDATE"
    ELIGIBLE_FOR_REVIEW = "ELIGIBLE_FOR_REVIEW"   # was PRIMITIVE — renamed


@dataclass
class PromotionThresholds:
    """
    The formal gates. Change these only with documented justification.
    Motivated by the lesson of OPEN_OBJECT: early promotion is lethal.
    """
    # CANDIDATE → STRONG_CANDIDATE
    strong_rediscovery:    int   = 2
    strong_cohesion:       float = 0.80
    strong_source_diversity: int = 2

    # STRONG_CANDIDATE → ELIGIBLE_FOR_REVIEW
    review_rediscovery:    int   = 5
    review_cohesion:       float = 0.90
    review_source_diversity: int = 3    # must span 3+ distinct platforms/families
    review_stress_test:    bool  = True


@dataclass
class CandidateGateResult:
    """Result of evaluating a candidate against the promotion rules."""
    candidate:       str
    current_tier:    PromotionTier
    rediscovery:     int
    cohesion:        float
    source_diversity: int
    stress_test:     bool

    missing_for_strong:  list[str] = field(default_factory=list)
    missing_for_review:  list[str] = field(default_factory=list)


def evaluate_candidate(
    candidate: str,
    rediscovery_count: int,
    semantic_cohesion: float,
    source_diversity: int,          # count of distinct platforms OR families
    stress_test_passed: bool,
    thresholds: Optional[PromotionThresholds] = None,
) -> CandidateGateResult:
    """
    Evaluates a candidate against the promotion rules.
    Returns current tier + list of missing gates.

    REMINDER: ELIGIBLE_FOR_REVIEW tier requires human evidence review
    before any Primitive declaration. The tier is a qualification, not a verdict.
    """
    t = thresholds or PromotionThresholds()

    missing_strong: list[str] = []
    missing_review: list[str] = []

    # --- STRONG_CANDIDATE gates ---
    if rediscovery_count < t.strong_rediscovery:
        missing_strong.append(f"rediscovery: {rediscovery_count}/{t.strong_rediscovery}")
    if semantic_cohesion < t.strong_cohesion:
        missing_strong.append(f"cohesion: {semantic_cohesion:.0%}/{t.strong_cohesion:.0%}")
    if source_diversity < t.strong_source_diversity:
        missing_strong.append(f"source_diversity: {source_diversity}/{t.strong_source_diversity}")

    # --- ELIGIBLE_FOR_REVIEW gates ---
    if rediscovery_count < t.review_rediscovery:
        missing_review.append(f"rediscovery: {rediscovery_count}/{t.review_rediscovery}")
    if semantic_cohesion < t.review_cohesion:
        missing_review.append(f"cohesion: {semantic_cohesion:.0%}/{t.review_cohesion:.0%}")
    if source_diversity < t.review_source_diversity:
        missing_review.append(f"source_diversity: {source_diversity}/{t.review_source_diversity} (distinct platforms/families)")
    if t.review_stress_test and not stress_test_passed:
        missing_review.append("stress_test: not passed")

    # --- Determine tier ---
    if not missing_strong:
        if not missing_review:
            tier = PromotionTier.ELIGIBLE_FOR_REVIEW
        else:
            tier = PromotionTier.STRONG_CANDIDATE
    else:
        tier = PromotionTier.CANDIDATE

    return CandidateGateResult(
        candidate=candidate,
        current_tier=tier,
        rediscovery=rediscovery_count,
        cohesion=semantic_cohesion,
        source_diversity=source_diversity,
        stress_test=stress_test_passed,
        missing_for_strong=missing_strong,
        missing_for_review=missing_review,
    )
