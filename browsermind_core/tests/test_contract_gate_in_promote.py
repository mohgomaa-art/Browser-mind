"""Tests: _compile_and_promote() uses OutcomeGate for stress_test_passed.

Verifies:
  - stress_test_passed=False when OUTCOME_GATE_PROMOTION=True and no contract found
  - stress_test_passed=True when OUTCOME_GATE_PROMOTION=True and contract verified ratio >= 0.80
  - Existing stub behaviour preserved when OUTCOME_GATE_PROMOTION=False
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_records_with_contract(*, goal_completed: bool, count: int = 1):
    records = []
    for _ in range(count):
        r = MagicMock()
        r.scope = "workflow_instance"
        r.metrics = {"contract_goal_completed": goal_completed}
        records.append(r)
    return records


def test_resolve_stress_test_no_contract_gate_on(monkeypatch):
    """Gate on + no contract → stress_test_passed=False."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    passed, reason = resolve_stress_test(
        template_name="greenhouse_apply_v2",
        env_key="greenhouse.io",
        execution_records=[],
        has_contract=False,
    )
    assert passed is False
    assert "no_contract" in reason


def test_resolve_stress_test_contract_verified_gate_on(monkeypatch):
    """Gate on + contract + 5/5 verified → stress_test_passed=True."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    records = _make_records_with_contract(goal_completed=True, count=5)
    passed, reason = resolve_stress_test(
        template_name="greenhouse_apply",
        env_key="greenhouse.io",
        execution_records=records,
        has_contract=True,
    )
    assert passed is True
    assert "ratio=1.00" in reason


def test_resolve_stress_test_gate_off_is_always_true(monkeypatch):
    """Gate off → stress_test_passed=True (stub) regardless of contract state."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", False)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    passed, reason = resolve_stress_test(
        template_name="any_template",
        env_key="any_env",
        execution_records=[],
        has_contract=False,
    )
    assert passed is True
    assert "STUBBED" in reason


def test_resolve_stress_test_threshold_boundary(monkeypatch):
    """Exactly 0.80 verified ratio passes; below fails."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    # 4 out of 5 = 0.80 — exactly at threshold → passes
    records = (
        _make_records_with_contract(goal_completed=True, count=4)
        + _make_records_with_contract(goal_completed=False, count=1)
    )
    passed, _ = resolve_stress_test("t", "e", records, has_contract=True)
    assert passed is True

    # 3 out of 5 = 0.60 — below threshold → fails
    records_low = (
        _make_records_with_contract(goal_completed=True, count=3)
        + _make_records_with_contract(goal_completed=False, count=2)
    )
    passed_low, _ = resolve_stress_test("t", "e", records_low, has_contract=True)
    assert passed_low is False
