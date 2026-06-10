"""EffectivenessTracker + LessonValidator — Self-Learning v1.

Closes Loops 7 and 8 of the BrowserMind self-learning audit:

  Loop 7 — Effectiveness Feedback
    Promoted lessons must be measurable. We compute the post-promotion
    success rate of any lesson tagged with a promoted_at timestamp and
    compare it against a baseline cohort gathered before promotion.

    When the post-promotion lift is negative AND the post-promotion
    sample is large enough (n_after_promotion >= QUARANTINE_MIN_SAMPLES),
    the lesson is marked `quarantined: true`. LessonReader skips
    quarantined lessons so the runtime stops acting on harmful priors.

  Loop 8 — Pre-promotion Validation
    Before flipping a lesson into the promoted state, the validator
    estimates the candidate's expected lift against the same baseline
    cohort. Lessons that would regress (lift <= 0) or that are
    statistically indistinguishable from the baseline (lift below
    MIN_LIFT) are rejected.

Strict scope: pure functions over OutcomeRecord lists. No model
training, no online learners. Re-uses existing OutcomeLedger.records
and the lesson schema (additive `promoted_at` / `quarantined` fields,
SCHEMA_VERSION unchanged).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from browsermind_core.ledger.outcome_ledger import OutcomeRecord


# Detection thresholds. Conservative on purpose — premature quarantine is
# worse than a slow detection: it tears down a working loop. Override in
# tests via keyword arguments rather than mutating these constants.
QUARANTINE_MIN_SAMPLES = 10
PROMOTION_MIN_SAMPLES = 5
MIN_LIFT = 0.0


def _is_step(rec: OutcomeRecord) -> bool:
    return rec.scope == "step" and rec.outcome_type == "step_attempt"


def _matches(rec: OutcomeRecord, key: Dict[str, Any]) -> bool:
    """True when an OutcomeRecord matches the lesson's key tuple."""
    m = rec.metrics or {}
    for k, v in key.items():
        if k == "environment_instance":
            if (rec.environment_instance or "") != (v or ""):
                return False
            continue
        # Most lesson keys map to entries on rec.metrics.
        if (m.get(k) or "") != (v or ""):
            return False
    return True


def _split_cohorts(
    records: List[OutcomeRecord],
    lesson: Dict[str, Any],
) -> Tuple[List[OutcomeRecord], List[OutcomeRecord]]:
    """Return (baseline, promoted) cohorts for a lesson.

    Baseline: records that match the lesson key but predate promotion.
    Promoted: records that match and post-date promotion.
    A lesson with no `promoted_at` returns (matched_records, []).
    """
    promoted_at = lesson.get("promoted_at")
    promo_dt: Optional[datetime] = None
    if promoted_at:
        try:
            promo_dt = datetime.fromisoformat(str(promoted_at).replace("Z", "+00:00"))
        except ValueError:
            promo_dt = None

    key = lesson.get("key", {})
    baseline: List[OutcomeRecord] = []
    promoted: List[OutcomeRecord] = []
    for rec in records:
        if not _is_step(rec):
            continue
        if not _matches(rec, key):
            continue
        if promo_dt is None:
            baseline.append(rec)
        elif rec.timestamp < promo_dt:
            baseline.append(rec)
        else:
            promoted.append(rec)
    return baseline, promoted


def _success_rate(records: List[OutcomeRecord]) -> Optional[float]:
    if not records:
        return None
    success = sum(1 for r in records if r.success)
    return round(success / len(records), 4)


def compute_effectiveness(
    records: Iterable[OutcomeRecord],
    lessons: Iterable[Dict[str, Any]],
    *,
    quarantine_min_samples: int = QUARANTINE_MIN_SAMPLES,
) -> Dict[str, Dict[str, Any]]:
    """Compute lift per promoted lesson against its baseline cohort.

    Returns: {lesson_id: {baseline_success_rate, promoted_success_rate,
                           lift, n_after_promotion, should_quarantine}}.
    Lessons without a `promoted_at` timestamp are reported with
    `n_after_promotion = 0` and `should_quarantine = False`.
    """
    records_list = list(records)
    out: Dict[str, Dict[str, Any]] = {}
    for lesson in lessons:
        lesson_id = lesson.get("lesson_id")
        if not lesson_id:
            continue
        baseline, promoted = _split_cohorts(records_list, lesson)
        b_rate = _success_rate(baseline)
        p_rate = _success_rate(promoted)
        lift = (
            round((p_rate or 0.0) - (b_rate or 0.0), 4)
            if (b_rate is not None and p_rate is not None)
            else None
        )
        n_after = len(promoted)
        should_quarantine = bool(
            lift is not None
            and lift < 0
            and n_after >= quarantine_min_samples
        )
        out[lesson_id] = {
            "baseline_success_rate": b_rate,
            "promoted_success_rate": p_rate,
            "lift": lift,
            "n_after_promotion": n_after,
            "should_quarantine": should_quarantine,
        }
    return out


def apply_effectiveness(
    lessons: List[Dict[str, Any]],
    effectiveness: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Mutate lessons in-place: set `quarantined=True` where the tracker
    flags should_quarantine=True. Existing quarantined flags are preserved.
    Returns the same list for chaining.
    """
    for lesson in lessons:
        lid = lesson.get("lesson_id")
        if not lid:
            continue
        rec = effectiveness.get(lid)
        if not rec:
            continue
        if rec.get("should_quarantine"):
            lesson["quarantined"] = True
        # Stash the most recent metrics for forensic inspection.
        lesson["effectiveness"] = {
            "baseline_success_rate": rec.get("baseline_success_rate"),
            "promoted_success_rate": rec.get("promoted_success_rate"),
            "lift": rec.get("lift"),
            "n_after_promotion": rec.get("n_after_promotion"),
        }
    return lessons


# ---------------------------------------------------------------------------
# LessonValidator — pre-promotion gate
# ---------------------------------------------------------------------------


def validate_for_promotion(
    lesson: Dict[str, Any],
    records: Iterable[OutcomeRecord],
    *,
    promotion_min_samples: int = PROMOTION_MIN_SAMPLES,
    min_lift: float = MIN_LIFT,
) -> Tuple[bool, str]:
    """Decide whether to promote a candidate lesson.

    Compares the candidate's success rate (from its existing observations)
    against the broader baseline cohort matching the same key. A lesson is
    rejected if it would fail to lift the baseline or has too thin a sample
    size to trust.

    Returns (allow_promotion, reason).
    """
    if lesson.get("observations", 0) < promotion_min_samples:
        return False, "below_promotion_min_samples"
    if lesson.get("quarantined"):
        return False, "already_quarantined"

    candidate_rate = lesson.get("success_rate")
    if candidate_rate is None:
        return False, "no_success_rate"

    baseline, _ = _split_cohorts(list(records), {**lesson, "promoted_at": None})
    base_rate = _success_rate(baseline)
    if base_rate is None:
        # No baseline → rely on candidate's intrinsic success rate.
        return (candidate_rate > min_lift, "no_baseline_uses_intrinsic")

    lift = candidate_rate - base_rate
    if lift <= min_lift:
        return False, f"lift_below_threshold:{round(lift, 4)}"
    return True, f"lift_ok:{round(lift, 4)}"


def stamp_promotion(lesson: Dict[str, Any], when: Optional[datetime] = None) -> Dict[str, Any]:
    """Set promoted_at on a lesson dict. Idempotent — does not overwrite an
    existing timestamp."""
    if lesson.get("promoted_at"):
        return lesson
    ts = (when or datetime.utcnow()).isoformat()
    lesson["promoted_at"] = ts
    return lesson
