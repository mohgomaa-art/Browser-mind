"""Tests for OutcomeGate policy class.

Exercises: resolve_stress_test(), contract_verified_ratio(),
filter_for_mining(), filter_for_compilation().

All tests run with feature flags OFF (default) and ON via monkeypatching
so behaviour of both code paths is verified.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def _make_record(*, contract_goal_completed=None, effect_verified=None, scope="workflow_instance"):
    rec = MagicMock()
    rec.scope = scope
    rec.metrics = {}
    if contract_goal_completed is not None:
        rec.metrics["contract_goal_completed"] = contract_goal_completed
    if effect_verified is not None:
        rec.metrics["effect_verified"] = effect_verified
    return rec


# ── contract_verified_ratio ──────────────────────────────────────────────────

def test_ratio_empty_list():
    from browsermind_core.verification.outcome_gate import contract_verified_ratio
    assert contract_verified_ratio([]) == 0.0


def test_ratio_all_none_excluded_from_denominator():
    from browsermind_core.verification.outcome_gate import contract_verified_ratio
    records = [_make_record() for _ in range(5)]
    # No contract_goal_completed key set → denominator is 0 → returns 0.0
    assert contract_verified_ratio(records) == 0.0


def test_ratio_all_true():
    from browsermind_core.verification.outcome_gate import contract_verified_ratio
    records = [_make_record(contract_goal_completed=True) for _ in range(4)]
    assert contract_verified_ratio(records) == 1.0


def test_ratio_mixed():
    from browsermind_core.verification.outcome_gate import contract_verified_ratio
    records = [
        _make_record(contract_goal_completed=True),
        _make_record(contract_goal_completed=True),
        _make_record(contract_goal_completed=False),
        _make_record(contract_goal_completed=False),
    ]
    assert contract_verified_ratio(records) == 0.5


def test_ratio_none_values_excluded():
    from browsermind_core.verification.outcome_gate import contract_verified_ratio
    # Records with None are not counted in denominator; only True/False are.
    records = [
        _make_record(contract_goal_completed=True),
        _make_record(),  # no key → excluded
        _make_record(contract_goal_completed=False),
    ]
    # 1 true out of 2 with explicit result → 0.5
    assert contract_verified_ratio(records) == 0.5


# ── resolve_stress_test ──────────────────────────────────────────────────────

def test_resolve_stress_test_gate_off_always_true(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", False)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    passed, reason = resolve_stress_test(
        "some_template", "some_env", [], has_contract=False
    )
    assert passed is True
    assert "STUBBED" in reason


def test_resolve_stress_test_gate_on_no_contract_returns_false(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    passed, reason = resolve_stress_test(
        "no_contract_template", "env1", [], has_contract=False
    )
    assert passed is False
    assert "no_contract" in reason


def test_resolve_stress_test_gate_on_high_ratio_returns_true(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    records = [_make_record(contract_goal_completed=True) for _ in range(5)]
    passed, reason = resolve_stress_test(
        "verified_template", "env1", records, has_contract=True
    )
    assert passed is True
    assert "ratio" in reason


def test_resolve_stress_test_gate_on_low_ratio_returns_false(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_PROMOTION", True)
    from browsermind_core.verification.outcome_gate import resolve_stress_test

    records = [
        _make_record(contract_goal_completed=True),
        _make_record(contract_goal_completed=False),
        _make_record(contract_goal_completed=False),
        _make_record(contract_goal_completed=False),
    ]
    passed, reason = resolve_stress_test(
        "low_ratio_template", "env1", records, has_contract=True
    )
    assert passed is False
    assert "ratio" in reason


# ── filter_for_mining ────────────────────────────────────────────────────────

def _make_step_record(*, effect_verified=None):
    return _make_record(effect_verified=effect_verified, scope="step")


def test_filter_for_mining_gate_off_returns_all(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_MINE_FILTER", False)
    from browsermind_core.verification.outcome_gate import filter_for_mining

    records = [_make_step_record() for _ in range(10)]
    result, label = filter_for_mining(records)
    assert result is records
    assert "gate_off" in label


def test_filter_for_mining_gate_on_enough_verified(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_MINE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_mining

    verified = [_make_step_record(effect_verified=True) for _ in range(3)]
    unverified = [_make_step_record() for _ in range(7)]
    result, label = filter_for_mining(verified + unverified)
    assert result == verified
    assert "verified=3" in label


def test_filter_for_mining_gate_on_insufficient_verified_fallback(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_MINE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_mining

    verified = [_make_step_record(effect_verified=True)]  # only 1, below threshold of 2
    unverified = [_make_step_record() for _ in range(5)]
    all_records = verified + unverified
    result, label = filter_for_mining(all_records)
    assert result is all_records
    assert "fallback" in label


# ── filter_for_compilation ───────────────────────────────────────────────────

def test_filter_for_compilation_gate_off(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", False)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    records = [_make_step_record() for _ in range(6)]
    result, label, verified_compile = filter_for_compilation(records)
    assert result is records
    assert verified_compile is False
    assert "gate_off" in label


def test_filter_for_compilation_gate_on_enough_verified(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    verified = [_make_step_record(effect_verified=True) for _ in range(2)]
    unverified = [_make_step_record() for _ in range(4)]
    result, label, verified_compile = filter_for_compilation(verified + unverified)
    assert result == verified
    assert verified_compile is True


def test_filter_for_compilation_gate_on_insufficient_fallback(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    verified = [_make_step_record(effect_verified=True)]  # 1, below threshold of 2
    unverified = [_make_step_record() for _ in range(4)]
    all_records = verified + unverified
    result, label, verified_compile = filter_for_compilation(all_records)
    assert result is all_records
    assert verified_compile is False
    assert "fallback" in label
