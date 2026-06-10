"""Tests: _compile_and_promote() feeds verified records to InvariantCompiler.

Verifies the filtering logic in filter_for_compilation():
  - With enough verified records (>= 2): compiles from verified pool only
  - With insufficient verified records (< 2): falls back to full pool
  - Flag off: always uses full pool
"""
from __future__ import annotations

from unittest.mock import MagicMock


def _make_step_record(*, effect_verified=None, success=True):
    r = MagicMock()
    r.scope = "step"
    r.success = success
    r.metrics = {}
    if effect_verified is not None:
        r.metrics["effect_verified"] = effect_verified
    return r


def test_compile_filter_gate_on_returns_verified_subset(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    verified = [_make_step_record(effect_verified=True) for _ in range(3)]
    unverified = [_make_step_record(effect_verified=None) for _ in range(5)]
    pool, label, from_verified = filter_for_compilation(verified + unverified)

    assert pool == verified
    assert from_verified is True
    assert "verified=3/8" in label


def test_compile_filter_gate_on_fallback_when_insufficient(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    records = [_make_step_record(effect_verified=True)] + [_make_step_record() for _ in range(4)]
    pool, label, from_verified = filter_for_compilation(records)

    assert pool is records
    assert from_verified is False
    assert "fallback" in label


def test_compile_filter_gate_off_returns_all(monkeypatch):
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", False)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    records = [_make_step_record() for _ in range(8)]
    pool, label, from_verified = filter_for_compilation(records)

    assert pool is records
    assert from_verified is False
    assert "gate_off" in label


def test_compile_filter_exact_threshold(monkeypatch):
    """Exactly 2 verified records → uses verified pool."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    verified = [_make_step_record(effect_verified=True) for _ in range(2)]
    pool, label, from_verified = filter_for_compilation(verified)

    assert pool == verified
    assert from_verified is True


def test_compile_filter_one_below_threshold(monkeypatch):
    """1 verified record (below threshold of 2) → falls back to full pool."""
    import browsermind_core.verification.outcome_gate as og
    monkeypatch.setattr(og, "OUTCOME_GATE_COMPILE_FILTER", True)
    from browsermind_core.verification.outcome_gate import filter_for_compilation

    records = [_make_step_record(effect_verified=True), _make_step_record()]
    pool, label, from_verified = filter_for_compilation(records)

    assert pool is records
    assert from_verified is False
