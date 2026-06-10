"""Adaptive Learning v1 — LessonReader unit tests.

Covers:
  - get_recovery_priors filters by failure_class and MIN_OBSERVATIONS
  - get_action_priors cross-filters env x action via environment_drift +
    action_failure_class
  - get_step_failure_count returns the right tally for a descriptor signature
  - notify_steps_recorded flips stale once REFRESH_AT_STEPS is crossed
  - _ensure_loaded atomically rewrites lessons.jsonl when stale AND an
    outcome_ledger is wired
  - missing / empty lessons.jsonl is handled (cold start)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from browsermind_core.runtime.lesson_reader import LessonReader


# --- Helpers ----------------------------------------------------------------


def _write_lessons(path: Path, lessons):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for l in lessons:
            f.write(json.dumps(l) + "\n")


def _recovery_lesson(failure_class, recovered_by, observations, success_rate):
    return {
        "schema_version": "browsermind.lesson.v1",
        "lesson_id": f"rs-{failure_class}-{recovered_by}",
        "kind": "recovery_strategy",
        "key": {"failure_class": failure_class, "recovered_by": recovered_by},
        "observations": observations,
        "outcomes": {"success": int(success_rate * observations),
                     "failure": observations - int(success_rate * observations)},
        "success_rate": success_rate,
        "examples": [],
        "first_seen": None,
        "last_seen": None,
    }


def _step_failure_lesson(env, action, role, name, failure_class, observations):
    return {
        "schema_version": "browsermind.lesson.v1",
        "lesson_id": f"sfd-{env}-{action}-{role}-{name}",
        "kind": "step_failure_descriptor",
        "key": {
            "environment_instance": env,
            "action": action,
            "role": role,
            "name": name,
            "failure_class": failure_class,
        },
        "observations": observations,
        "outcomes": {"success": 0, "failure": observations},
        "success_rate": 0.0,
        "examples": [],
        "first_seen": None,
        "last_seen": None,
    }


# --- get_recovery_priors -----------------------------------------------------


def test_recovery_priors_returns_strategies_above_min_observations():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        _write_lessons(path, [
            _recovery_lesson("TARGET_CHANGED", "container_proximity", 5, 0.8),
            _recovery_lesson("TARGET_CHANGED", "structural_path", 4, 0.4),
            _recovery_lesson("TARGET_CHANGED", "capability_intent", 1, 1.0),  # below MIN_OBSERVATIONS
        ])
        priors = LessonReader(lessons_path=path).get_recovery_priors("TARGET_CHANGED")
        assert priors == {"container_proximity": 0.8, "structural_path": 0.4}


def test_recovery_priors_returns_empty_on_unknown_failure_class():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        _write_lessons(path, [_recovery_lesson("TARGET_CHANGED", "x", 5, 0.8)])
        assert LessonReader(lessons_path=path).get_recovery_priors("CONTRACT_FAILURE") == {}


def test_recovery_priors_cold_start_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"  # file does not exist
        assert LessonReader(lessons_path=path).get_recovery_priors("TARGET_CHANGED") == {}


# --- get_action_priors -------------------------------------------------------


def test_action_priors_cross_filters_env_and_action():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        _write_lessons(path, [
            {
                "schema_version": "browsermind.lesson.v1",
                "lesson_id": "ed1", "kind": "environment_drift",
                "key": {"environment_instance": "saucedemo",
                        "failure_class": "TARGET_CHANGED"},
                "observations": 5, "outcomes": {"success": 0, "failure": 5},
                "success_rate": 0.0, "examples": [],
                "first_seen": None, "last_seen": None,
            },
            {
                "schema_version": "browsermind.lesson.v1",
                "lesson_id": "afc1", "kind": "action_failure_class",
                "key": {"action": "click", "failure_class": "TARGET_CHANGED"},
                "observations": 4, "outcomes": {"success": 0, "failure": 4},
                "success_rate": 0.0, "examples": [],
                "first_seen": None, "last_seen": None,
            },
            _recovery_lesson("TARGET_CHANGED", "container_proximity", 5, 0.8),
        ])
        priors = LessonReader(lessons_path=path).get_action_priors("click", "saucedemo")
        assert priors == {"container_proximity": 0.8}


def test_action_priors_unknown_action_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        _write_lessons(path, [
            _recovery_lesson("TARGET_CHANGED", "container_proximity", 5, 0.8),
        ])
        assert LessonReader(lessons_path=path).get_action_priors("", "saucedemo") == {}


# --- get_step_failure_count --------------------------------------------------


def test_step_failure_count_returns_observation_count():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        _write_lessons(path, [
            _step_failure_lesson("saucedemo", "click", "button", "Submit",
                                 "TARGET_CHANGED", 7),
        ])
        reader = LessonReader(lessons_path=path)
        assert reader.get_step_failure_count(
            env="saucedemo", action="click", role="button", name="Submit",
            failure_class="TARGET_CHANGED",
        ) == 7
        # Different signature → 0.
        assert reader.get_step_failure_count(
            env="saucedemo", action="click", role="button", name="Cancel",
            failure_class="TARGET_CHANGED",
        ) == 0


def test_step_failure_count_cold_start():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        assert LessonReader(lessons_path=path).get_step_failure_count(
            env="x", action="click", role="button", name="Submit",
            failure_class="TARGET_CHANGED",
        ) == 0


# --- notify + lazy refresh ---------------------------------------------------


def test_notify_steps_recorded_flips_stale_at_threshold():
    reader = LessonReader(lessons_path=Path("/nonexistent"))
    assert reader._stale is False
    reader.notify_steps_recorded(10)
    assert reader._stale is False
    reader.notify_steps_recorded(LessonReader.REFRESH_AT_STEPS)
    assert reader._stale is True


def test_lazy_refresh_rewrites_lessons_from_outcome_ledger():
    """When stale and an outcome_ledger is wired, the next read must
    re-extract lessons via lesson_aggregator and atomically rewrite the
    file, then load the fresh data."""
    from training.lesson_aggregator import extract_lessons  # smoke import
    from browsermind_core.ledger.outcome_ledger import OutcomeLedger, OutcomeRecord

    ledger = OutcomeLedger()
    # Seed 3 step records for the same descriptor → step_failure_descriptor lesson
    persona_id = uuid4()
    scope_id = uuid4()
    for _ in range(3):
        ledger.record(OutcomeRecord(
            scope="step",
            scope_id=scope_id,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="saucedemo",
            outcome_type="step_attempt",
            success=False,
            evidence="x",
            metrics={
                "step_id": "abc", "step_seq": 1, "action": "click",
                "role": "button", "name": "Submit",
                "predicted_tier": "HIGH", "actual_outcome": "FAILED",
                "failure_class": "TARGET_CHANGED",
                "root_cause": "target not found",
            },
        ))

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"  # absent initially
        reader = LessonReader(lessons_path=path, outcome_ledger=ledger)
        # First read on cold start → empty.
        assert reader.get_step_failure_count(
            env="saucedemo", action="click", role="button", name="Submit",
            failure_class="TARGET_CHANGED",
        ) == 0
        # Trigger lazy refresh.
        reader.notify_steps_recorded(LessonReader.REFRESH_AT_STEPS)
        assert reader._stale is True
        # Next read must rewrite + reload + report >=3.
        n = reader.get_step_failure_count(
            env="saucedemo", action="click", role="button", name="Submit",
            failure_class="TARGET_CHANGED",
        )
        assert n == 3
        # File on disk was rewritten.
        assert path.exists()
        assert reader._stale is False


def test_refresh_failure_does_not_raise():
    """A broken outcome_ledger must not crash a read."""
    broken = MagicMock()
    broken.records = MagicMock(side_effect=RuntimeError("boom"))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        reader = LessonReader(lessons_path=path, outcome_ledger=broken)
        reader.notify_steps_recorded(LessonReader.REFRESH_AT_STEPS)
        # Should not raise even though refresh internally fails.
        assert reader.get_recovery_priors("TARGET_CHANGED") == {}


def test_empty_lessons_file_handled():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.jsonl"
        path.write_text("", encoding="utf-8")
        assert LessonReader(lessons_path=path).get_recovery_priors("TARGET_CHANGED") == {}
