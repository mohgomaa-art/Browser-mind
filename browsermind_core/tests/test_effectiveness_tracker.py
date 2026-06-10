"""Self-Learning v1 — EffectivenessTracker + LessonValidator unit tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from browsermind_core.ledger.outcome_ledger import OutcomeRecord

from training.effectiveness_tracker import (
    apply_effectiveness,
    compute_effectiveness,
    stamp_promotion,
    validate_for_promotion,
)


def _step(success: bool, ts: datetime, *, action="click", role="button",
          name="Submit", env="saucedemo", recovered_by="container_proximity",
          failure_class="TARGET_CHANGED"):
    """Build a step record. Recovery-context records always carry the
    failure_class — `success` indicates whether the recovery worked, not
    whether a failure occurred.
    """
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="saucedemo",
        environment_instance=env,
        outcome_type="step_attempt",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={
            "action": action, "role": role, "name": name,
            "recovered_by": recovered_by,
            "failure_class": failure_class,
            "actual_outcome": "SUCCESS" if success else "FAILED",
            "predicted_tier": "HIGH",
        },
    )


def _lesson(*, lesson_id="L1", recovered_by="container_proximity",
            failure_class="TARGET_CHANGED", success_rate=0.8,
            observations=5, promoted_at=None):
    return {
        "schema_version": "browsermind.lesson.v1",
        "lesson_id": lesson_id,
        "kind": "recovery_strategy",
        "key": {"failure_class": failure_class, "recovered_by": recovered_by},
        "observations": observations,
        "outcomes": {"success": int(observations * success_rate),
                     "failure": observations - int(observations * success_rate)},
        "success_rate": success_rate,
        "examples": [],
        "first_seen": None,
        "last_seen": None,
        "promoted_at": promoted_at,
    }


# --- compute_effectiveness ---------------------------------------------------


def test_effectiveness_lift_positive_does_not_quarantine():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    promo_ts = base_ts + timedelta(hours=1)
    records = (
        # Baseline: 3/10 success
        [_step(True, base_ts + timedelta(minutes=i)) for i in range(3)]
        + [_step(False, base_ts + timedelta(minutes=i + 3)) for i in range(7)]
        # Promoted: 9/12 success
        + [_step(True, promo_ts + timedelta(minutes=i)) for i in range(9)]
        + [_step(False, promo_ts + timedelta(minutes=i + 9)) for i in range(3)]
    )
    lessons = [_lesson(lesson_id="L+", promoted_at=promo_ts.isoformat())]
    eff = compute_effectiveness(records, lessons)
    row = eff["L+"]
    assert row["baseline_success_rate"] == 0.3
    assert row["promoted_success_rate"] == 0.75
    assert row["lift"] == 0.45
    assert row["n_after_promotion"] == 12
    assert row["should_quarantine"] is False


def test_effectiveness_negative_lift_with_enough_samples_quarantines():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    promo_ts = base_ts + timedelta(hours=1)
    records = (
        # Baseline: 8/10 success
        [_step(True, base_ts + timedelta(minutes=i)) for i in range(8)]
        + [_step(False, base_ts + timedelta(minutes=i + 8)) for i in range(2)]
        # Promoted: 2/12 success — much worse
        + [_step(True, promo_ts + timedelta(minutes=i)) for i in range(2)]
        + [_step(False, promo_ts + timedelta(minutes=i + 2)) for i in range(10)]
    )
    lessons = [_lesson(lesson_id="L-", promoted_at=promo_ts.isoformat())]
    eff = compute_effectiveness(records, lessons)
    row = eff["L-"]
    assert row["lift"] is not None and row["lift"] < 0
    assert row["n_after_promotion"] >= 10
    assert row["should_quarantine"] is True


def test_effectiveness_negative_lift_thin_sample_does_not_quarantine():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    promo_ts = base_ts + timedelta(hours=1)
    records = (
        [_step(True, base_ts + timedelta(minutes=i)) for i in range(8)]
        + [_step(False, base_ts + timedelta(minutes=i + 8)) for i in range(2)]
        # Only 3 promoted samples — below QUARANTINE_MIN_SAMPLES
        + [_step(False, promo_ts + timedelta(minutes=i)) for i in range(3)]
    )
    lessons = [_lesson(lesson_id="Lthin", promoted_at=promo_ts.isoformat())]
    eff = compute_effectiveness(records, lessons)
    assert eff["Lthin"]["should_quarantine"] is False


def test_apply_effectiveness_marks_quarantined():
    lessons = [_lesson(lesson_id="LX", promoted_at="2026-06-01T00:00:00+00:00")]
    eff = {"LX": {"baseline_success_rate": 0.8, "promoted_success_rate": 0.1,
                  "lift": -0.7, "n_after_promotion": 15,
                  "should_quarantine": True}}
    apply_effectiveness(lessons, eff)
    assert lessons[0]["quarantined"] is True
    assert lessons[0]["effectiveness"]["lift"] == -0.7


# --- validate_for_promotion --------------------------------------------------


def test_validator_rejects_below_promotion_min_samples():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    records = [_step(True, base_ts) for _ in range(20)]
    lesson = _lesson(observations=2, success_rate=1.0)
    ok, reason = validate_for_promotion(lesson, records, promotion_min_samples=5)
    assert ok is False
    assert reason == "below_promotion_min_samples"


def test_validator_rejects_negative_lift():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    records = [_step(True, base_ts + timedelta(minutes=i)) for i in range(8)] \
        + [_step(False, base_ts + timedelta(minutes=i + 8)) for i in range(2)]
    lesson = _lesson(observations=10, success_rate=0.4)  # below baseline (0.8)
    ok, _ = validate_for_promotion(lesson, records)
    assert ok is False


def test_validator_accepts_positive_lift():
    base_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    records = [_step(False, base_ts + timedelta(minutes=i)) for i in range(10)]
    lesson = _lesson(observations=10, success_rate=0.6)
    ok, reason = validate_for_promotion(lesson, records)
    assert ok is True
    assert reason.startswith("lift_ok")


def test_validator_rejects_quarantined():
    lesson = _lesson(observations=10, success_rate=0.9)
    lesson["quarantined"] = True
    ok, reason = validate_for_promotion(lesson, [])
    assert ok is False
    assert reason == "already_quarantined"


# --- stamp_promotion ---------------------------------------------------------


def test_stamp_promotion_is_idempotent():
    lesson = _lesson()
    stamp_promotion(lesson)
    first = lesson["promoted_at"]
    assert first is not None
    stamp_promotion(lesson)
    assert lesson["promoted_at"] == first
