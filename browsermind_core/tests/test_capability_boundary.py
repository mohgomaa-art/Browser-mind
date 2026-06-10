"""Tests for CapabilityBoundary extraction and merging.

Verifies:
  - Failures produce CapabilityBoundary objects with correct fields
  - Successes are ignored
  - Records without failure_class are ignored
  - Multiple failures for the same (capability_hint, failure_mode) are merged
  - merge_boundaries() correctly aggregates into existing dicts
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4


def _make_step_record(*, success, failure_class=None, name="btn", role="button",
                      action="click", execution_id=None, environment_instance="test_env"):
    r = MagicMock()
    r.success = success
    r.scope = "step"
    r.environment_instance = environment_instance
    r.execution_id = execution_id or uuid4()
    r.metrics = {
        "failure_class": failure_class,
        "failure_reason": failure_class or "",
        "name": name,
        "role": role,
        "action": action,
    }
    return r


# ── extract_boundaries_from_failures ─────────────────────────────────────────

def test_success_records_ignored():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    records = [_make_step_record(success=True, failure_class="TARGET_CHANGED") for _ in range(5)]
    result = extract_boundaries_from_failures(records)
    assert result == []


def test_no_failure_class_ignored():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    records = [_make_step_record(success=False, failure_class=None)]
    result = extract_boundaries_from_failures(records)
    assert result == []


def test_single_failure_produces_boundary():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    rec = _make_step_record(success=False, failure_class="TARGET_CHANGED", name="submit_btn")
    result = extract_boundaries_from_failures([rec])
    assert len(result) == 1
    b = result[0]
    assert b.capability_hint == "submit_btn"
    assert b.failure_mode == "TARGET_CHANGED"
    assert b.frequency == 1
    assert b.evidence_count == 1


def test_same_hint_same_class_merged():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    exec_id_1 = uuid4()
    exec_id_2 = uuid4()
    records = [
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="search_box", execution_id=exec_id_1),
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="search_box", execution_id=exec_id_1),
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="search_box", execution_id=exec_id_2),
    ]
    result = extract_boundaries_from_failures(records)
    assert len(result) == 1
    b = result[0]
    assert b.frequency == 3
    assert b.evidence_count == 2  # 2 distinct execution_ids


def test_different_failure_classes_produce_separate_boundaries():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    records = [
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="auth_btn"),
        _make_step_record(success=False, failure_class="AMBIGUOUS_TARGET", name="auth_btn"),
    ]
    result = extract_boundaries_from_failures(records)
    assert len(result) == 2
    modes = {b.failure_mode for b in result}
    assert modes == {"TARGET_CHANGED", "AMBIGUOUS_TARGET"}


def test_different_capability_hints_produce_separate_boundaries():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    records = [
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="login_btn"),
        _make_step_record(success=False, failure_class="TARGET_CHANGED", name="submit_btn"),
    ]
    result = extract_boundaries_from_failures(records)
    assert len(result) == 2


def test_fallback_to_role_when_name_empty():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    r = _make_step_record(success=False, failure_class="ENVIRONMENT_FAILURE", name="", role="textbox")
    result = extract_boundaries_from_failures([r])
    assert len(result) == 1
    assert result[0].capability_hint == "textbox"


def test_sorted_by_frequency_descending():
    from browsermind_core.learning.capability_boundary import extract_boundaries_from_failures
    records = (
        [_make_step_record(success=False, failure_class="TARGET_CHANGED", name="rare_btn")] +
        [_make_step_record(success=False, failure_class="AMBIGUOUS_TARGET", name="common_btn") for _ in range(5)]
    )
    result = extract_boundaries_from_failures(records)
    assert result[0].failure_mode == "AMBIGUOUS_TARGET"
    assert result[0].frequency == 5


# ── merge_boundaries ─────────────────────────────────────────────────────────

def test_merge_empty_existing():
    from browsermind_core.learning.capability_boundary import (
        CapabilityBoundary, merge_boundaries
    )
    b = CapabilityBoundary(
        capability_hint="auth_btn",
        failure_mode="TARGET_CHANGED",
        failure_reason="TARGET_CHANGED",
        environment_pattern="github",
        frequency=3,
        evidence_count=2,
    )
    result = merge_boundaries([], [b])
    assert len(result) == 1
    assert result[0]["capability_hint"] == "auth_btn"
    assert result[0]["frequency"] == 3


def test_merge_existing_same_key_increments():
    from browsermind_core.learning.capability_boundary import (
        CapabilityBoundary, merge_boundaries
    )
    existing = [{"capability_hint": "auth_btn", "failure_mode": "TARGET_CHANGED",
                 "frequency": 2, "evidence_count": 1}]
    b = CapabilityBoundary(
        capability_hint="auth_btn",
        failure_mode="TARGET_CHANGED",
        failure_reason="TARGET_CHANGED",
        environment_pattern="saucedemo",
        frequency=3,
        evidence_count=2,
    )
    result = merge_boundaries(existing, [b])
    assert len(result) == 1
    assert result[0]["frequency"] == 5
    assert result[0]["evidence_count"] == 3


def test_merge_existing_different_key_appends():
    from browsermind_core.learning.capability_boundary import (
        CapabilityBoundary, merge_boundaries
    )
    existing = [{"capability_hint": "auth_btn", "failure_mode": "TARGET_CHANGED",
                 "frequency": 1, "evidence_count": 1}]
    b = CapabilityBoundary(
        capability_hint="search_box",
        failure_mode="AMBIGUOUS_TARGET",
        failure_reason="AMBIGUOUS_TARGET",
        environment_pattern="github",
        frequency=1,
        evidence_count=1,
    )
    result = merge_boundaries(existing, [b])
    assert len(result) == 2
