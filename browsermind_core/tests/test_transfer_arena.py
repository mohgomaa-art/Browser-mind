"""Tests for TransferArena cross-site transfer benchmark.

Verifies:
  - TransferScore rate computation
  - is_transferring threshold
  - evaluate() correctly splits records by env group
  - evaluate() filters by outcome_type
  - evaluate() filters by template_prefix
  - evaluate_all() returns all configured families
  - report() includes all families
  - Unknown family raises ValueError
  - Empty ledger returns zero-count score
"""
from __future__ import annotations

from unittest.mock import MagicMock


def _make_ledger(*env_success_pairs, outcome_type="replay_run", template_name=""):
    """Build a mock ledger with records for given (env_key, success) pairs."""
    ledger = MagicMock()
    records = []
    for env, success in env_success_pairs:
        r = MagicMock()
        r.scope = "workflow_instance"
        r.outcome_type = outcome_type
        r.environment_instance = env
        r.success = success
        r.metrics = {"template_name": template_name}
        records.append(r)
    ledger.records = records
    return ledger


# ── TransferScore ─────────────────────────────────────────────────────────────

def test_transfer_score_rates():
    from browsermind_core.evaluation.transfer_arena import TransferScore
    s = TransferScore(
        family="auth",
        training_envs=["github"],
        test_envs=["gitlab"],
        training_total=10, training_success=8,
        test_total=5, test_success=4,
    )
    assert s.training_rate == 0.8
    assert s.test_rate == 0.8
    assert s.transfer_delta == 0.0
    assert s.is_transferring is True


def test_transfer_score_below_tolerance_not_transferring():
    from browsermind_core.evaluation.transfer_arena import TransferScore
    s = TransferScore(
        family="auth",
        training_envs=["github"],
        test_envs=["gitlab"],
        training_total=10, training_success=10,
        test_total=10, test_success=5,
    )
    # delta = 0.5 - 1.0 = -0.5 < -0.10
    assert s.is_transferring is False


def test_transfer_score_within_tolerance_transferring():
    from browsermind_core.evaluation.transfer_arena import TransferScore
    s = TransferScore(
        family="auth",
        training_envs=["github"],
        test_envs=["gitlab"],
        training_total=10, training_success=10,
        test_total=10, test_success=9,
    )
    # delta = 0.9 - 1.0 = -0.10 (exactly at boundary)
    assert s.is_transferring is True


def test_transfer_score_none_when_no_test_data():
    from browsermind_core.evaluation.transfer_arena import TransferScore
    s = TransferScore(
        family="auth",
        training_envs=["github"],
        test_envs=[],
        training_total=5, training_success=5,
        test_total=0, test_success=0,
    )
    assert s.test_rate is None
    assert s.is_transferring is None


def test_transfer_score_summary_contains_verdict():
    from browsermind_core.evaluation.transfer_arena import TransferScore
    s = TransferScore(
        family="auth",
        training_envs=["github"],
        test_envs=["gitlab"],
        training_total=10, training_success=8,
        test_total=5, test_success=1,
    )
    summary = s.summary()
    assert "MEMORISED" in summary
    assert "auth" in summary


# ── TransferArena.evaluate() ──────────────────────────────────────────────────

def test_evaluate_splits_by_env():
    from browsermind_core.evaluation.transfer_arena import TransferArena, TransferArenaConfig
    config = {
        "auth": TransferArenaConfig(
            family="auth",
            training_envs=["github"],
            test_envs=["gitlab"],
        )
    }
    ledger = _make_ledger(
        ("github", True), ("github", True), ("github", False),
        ("gitlab", True), ("gitlab", False),
    )
    score = TransferArena(config).evaluate("auth", ledger)
    assert score.training_total == 3
    assert score.training_success == 2
    assert score.test_total == 2
    assert score.test_success == 1


def test_evaluate_ignores_step_scope():
    from browsermind_core.evaluation.transfer_arena import TransferArena, TransferArenaConfig
    config = {
        "auth": TransferArenaConfig(family="auth", training_envs=["github"], test_envs=[])
    }
    ledger = MagicMock()
    r_step = MagicMock()
    r_step.scope = "step"
    r_step.outcome_type = "replay_run"
    r_step.environment_instance = "github"
    r_step.success = True
    r_step.metrics = {"template_name": ""}
    ledger.records = [r_step]
    score = TransferArena(config).evaluate("auth", ledger)
    assert score.training_total == 0


def test_evaluate_filters_by_outcome_type():
    from browsermind_core.evaluation.transfer_arena import TransferArena, TransferArenaConfig
    config = {
        "auth": TransferArenaConfig(
            family="auth",
            training_envs=["github"],
            test_envs=[],
            outcome_types=["replay_run"],
        )
    }
    ledger = _make_ledger(
        ("github", True),
        outcome_type="contract_verification",  # should be excluded
    )
    score = TransferArena(config).evaluate("auth", ledger)
    assert score.training_total == 0


def test_evaluate_filters_by_template_prefix():
    from browsermind_core.evaluation.transfer_arena import TransferArena, TransferArenaConfig
    config = {
        "auth": TransferArenaConfig(
            family="auth",
            training_envs=["github"],
            test_envs=[],
            template_prefixes=["login"],
        )
    }
    ledger = _make_ledger(
        ("github", True),
        template_name="login_github",
    )
    ledger2 = _make_ledger(
        ("github", True),
        template_name="search_github",
    )
    score_match = TransferArena(config).evaluate("auth", ledger)
    score_miss = TransferArena(config).evaluate("auth", ledger2)
    assert score_match.training_total == 1
    assert score_miss.training_total == 0


def test_evaluate_unknown_family_raises():
    from browsermind_core.evaluation.transfer_arena import TransferArena
    import pytest
    arena = TransferArena()
    ledger = MagicMock()
    ledger.records = []
    with pytest.raises(ValueError, match="No TransferArenaConfig"):
        arena.evaluate("nonexistent_family", ledger)


def test_evaluate_all_returns_all_families():
    from browsermind_core.evaluation.transfer_arena import TransferArena, ARENA_CONFIGS
    ledger = MagicMock()
    ledger.records = []
    scores = TransferArena().evaluate_all(ledger)
    assert set(scores.keys()) == set(ARENA_CONFIGS.keys())


def test_report_contains_all_families():
    from browsermind_core.evaluation.transfer_arena import TransferArena, ARENA_CONFIGS
    ledger = MagicMock()
    ledger.records = []
    report = TransferArena().report(ledger)
    for family in ARENA_CONFIGS:
        assert family in report
