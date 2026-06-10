"""R6 v2 — bm recovery mine / sweep / monitor CLI verb tests.

These three verbs are the operator-facing taps that connect the existing
pure functions (mine_patterns, refresh_registry, post_commit_monitor.sweep)
to a real end-to-end cycle.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from browsermind_core.console import cli as cli_module
from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.ontology.recovery_candidate import RecoveryCandidate
from browsermind_core.runtime.recovery_registry import RecoveryStrategy
from browsermind_core.runtime.shadow_validator import ShadowValidator


def _step(success, ts, *, recovered_by="", failure_class="TARGET_CHANGED",
          name="Submit", env="saucedemo", action="click"):
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="testfam",
        environment_instance=env,
        outcome_type="step_attempt",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={
            "action": action, "role": "button", "name": name,
            "recovered_by": recovered_by,
            "failure_class": failure_class,
            "actual_outcome": "SUCCESS" if success else "FAILED",
        },
    )


def _seed_unrecovered_failures(ks: KernelSession, n: int):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(n):
        ks.outcome_ledger.record(
            _step(False, base + timedelta(seconds=i), recovered_by="")
        )


def _seed_recovered(ks: KernelSession, n: int, *, recovered_by="container_proximity"):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(n):
        ks.outcome_ledger.record(
            _step(True, base + timedelta(seconds=1000 + i),
                  recovered_by=recovered_by)
        )


# =============================================================================
# bm recovery mine
# =============================================================================


def test_mine_errors_when_ledger_empty(tmp_path):
    runner = CliRunner()
    KernelSession(store_dir=str(tmp_path))   # initialize store
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "mine"],
    )
    # _err calls sys.exit(1)
    assert result.exit_code != 0
    assert "no records" in result.output.lower()


def test_mine_persists_candidates(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    _seed_unrecovered_failures(ks, 25)
    _seed_recovered(ks, 5)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "mine",
         "--min-support", "5", "--min-lift", "2.0"],
    )
    assert result.exit_code == 0, result.output

    ks2 = KernelSession(store_dir=str(tmp_path))
    rows = ks2.recovery_candidate_registry.list()
    assert len(rows) >= 1
    assert rows[0].status == "pending"
    assert rows[0].support >= 5
    assert "Saved" in result.output


def test_mine_dry_run_does_not_persist(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    _seed_unrecovered_failures(ks, 25)
    _seed_recovered(ks, 5)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "mine",
         "--min-support", "5", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower()
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.list() == []


def test_mine_dedups_existing_candidates(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    _seed_unrecovered_failures(ks, 25)
    _seed_recovered(ks, 5)
    runner = CliRunner()
    # First run.
    runner.invoke(cli_module.cli,
                  ["--store", str(tmp_path), "recovery", "mine",
                   "--min-support", "5"])
    n_after_first = len(KernelSession(store_dir=str(tmp_path))
                         .recovery_candidate_registry.list())
    # Second run with same data should add nothing.
    result = runner.invoke(cli_module.cli,
                           ["--store", str(tmp_path), "recovery", "mine",
                            "--min-support", "5"])
    assert result.exit_code == 0
    n_after_second = len(KernelSession(store_dir=str(tmp_path))
                          .recovery_candidate_registry.list())
    assert n_after_second == n_after_first
    assert "DUP" in result.output


# =============================================================================
# bm recovery sweep
# =============================================================================


def _seed_shadow(path: Path, candidate_id: str, *, n_resolve: int, n_total: int,
                 baseline_n: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for i in range(n_total):
            f.write(json.dumps({
                "ts": "2026-06-07T00:00:00+00:00",
                "candidate_id": candidate_id,
                "primitive": "by_text",
                "would_resolve": i < n_resolve,
                "candidate_count": 1 if i < n_resolve else 0,
                "live_resolver_succeeded": i < baseline_n,
            }) + "\n")


def test_sweep_promotes_strong_candidate(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:strong",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="pending",
    )
    ks.recovery_candidate_registry.save(cand)
    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=28, n_total=30, baseline_n=0)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "sweep",
         "--shadow-min-samples", "30", "--min-lift", "0.1"],
    )
    assert result.exit_code == 0, result.output
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.get(cand.id).status == "ready"
    assert "Promoted 1" in result.output


def test_sweep_does_not_promote_weak_candidate(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:weak", predicate={}, primitive="by_text", status="pending",
    )
    ks.recovery_candidate_registry.save(cand)
    validator = ShadowValidator(str(tmp_path))
    # Negative lift: 5/30 mined vs 25/30 baseline.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=5, n_total=30, baseline_n=25)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "sweep",
         "--shadow-min-samples", "30", "--min-lift", "0.1"],
    )
    assert result.exit_code == 0, result.output
    ks2 = KernelSession(store_dir=str(tmp_path))
    after = ks2.recovery_candidate_registry.get(cand.id)
    assert after.status != "ready"
    assert "Promoted 0" in result.output


def test_sweep_handles_empty_registry(tmp_path):
    KernelSession(store_dir=str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "sweep"],
    )
    assert result.exit_code == 0, result.output
    assert "(no pending/shadow candidates)" in result.output


# =============================================================================
# bm recovery monitor
# =============================================================================


def _post_commit_step(success, ts, *, recovered_by, env="saucedemo"):
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="testfam",
        environment_instance=env,
        outcome_type="step_attempt",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={
            "recovered_by": recovered_by,
            "actual_outcome": "SUCCESS" if success else "FAILED",
        },
    )


def test_monitor_quarantines_negative_lift_strategy(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)

    cand = RecoveryCandidate(
        name="mined:badrec", predicate={}, primitive="by_text",
        status="committed",
    )
    cand.committed_at = base - timedelta(hours=1)
    ks.recovery_candidate_registry.save(cand)
    ks.recovery_registry.append(RecoveryStrategy(
        name="mined:badrec", predicate={}, primitive="by_text",
        depth=5, source="mined", candidate_id=str(cand.id),
    ))

    needle = f"mined:{cand.id}"
    # Mined strategy resolves only 2/25 = 8%.
    for i in range(25):
        ks.outcome_ledger.record(
            _post_commit_step(i < 2, base + timedelta(minutes=i),
                              recovered_by=needle)
        )
    # Builtin baseline: 22/25 = 88%.
    for i in range(25):
        ks.outcome_ledger.record(
            _post_commit_step(i < 22, base + timedelta(minutes=30 + i),
                              recovered_by="container_proximity")
        )

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "monitor",
         "--min-samples", "10", "--neg-lift", "0.1"],
    )
    assert result.exit_code == 0, result.output
    assert "Quarantined 1" in result.output
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.get(cand.id).status == "quarantined"
    # Ladder hides the harmful row.
    names = [s.name for s in ks2.recovery_registry.ladder()]
    assert "mined:badrec" not in names


def test_monitor_keeps_healthy_strategy(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cand = RecoveryCandidate(
        name="mined:goodrec", predicate={}, primitive="by_text",
        status="committed",
    )
    cand.committed_at = base - timedelta(hours=1)
    ks.recovery_candidate_registry.save(cand)
    ks.recovery_registry.append(RecoveryStrategy(
        name="mined:goodrec", predicate={}, primitive="by_text",
        depth=5, source="mined", candidate_id=str(cand.id),
    ))

    needle = f"mined:{cand.id}"
    # Mined strategy: 23/25 = 92%, baseline 23/25 = 92% — neutral.
    for i in range(25):
        ks.outcome_ledger.record(
            _post_commit_step(i < 23, base + timedelta(minutes=i),
                              recovered_by=needle)
        )
    for i in range(25):
        ks.outcome_ledger.record(
            _post_commit_step(i < 23, base + timedelta(minutes=30 + i),
                              recovered_by="container_proximity")
        )

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "monitor",
         "--min-samples", "10", "--neg-lift", "0.1"],
    )
    assert result.exit_code == 0, result.output
    assert "Quarantined 0" in result.output
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.get(cand.id).status == "committed"


def test_monitor_handles_no_committed_candidates(tmp_path):
    KernelSession(store_dir=str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "monitor"],
    )
    assert result.exit_code == 0, result.output
    assert "(no committed candidates" in result.output


# =============================================================================
# End-to-end: mine → sweep → approve → monitor (the full first cycle)
# =============================================================================


def test_full_first_cycle_mine_sweep_approve_monitor(tmp_path):
    """One pass through the pipeline using only CLI verbs."""
    ks = KernelSession(store_dir=str(tmp_path))
    _seed_unrecovered_failures(ks, 25)
    _seed_recovered(ks, 5)
    runner = CliRunner()

    # 1. Mine
    r1 = runner.invoke(cli_module.cli,
                       ["--store", str(tmp_path), "recovery", "mine",
                        "--min-support", "5", "--min-lift", "2.0"])
    assert r1.exit_code == 0
    cand = KernelSession(store_dir=str(tmp_path)).recovery_candidate_registry.list()[0]
    assert cand.status == "pending"

    # 2. Seed shadow evidence and sweep.
    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=28, n_total=30, baseline_n=0)
    r2 = runner.invoke(cli_module.cli,
                       ["--store", str(tmp_path), "recovery", "sweep",
                        "--shadow-min-samples", "30", "--min-lift", "0.1"])
    assert r2.exit_code == 0
    after_sweep = KernelSession(store_dir=str(tmp_path)) \
        .recovery_candidate_registry.get(cand.id)
    assert after_sweep.status == "ready"

    # 3. Approve.
    r3 = runner.invoke(cli_module.cli,
                       ["--store", str(tmp_path), "recovery", "candidate",
                        "approve", str(cand.id)])
    assert r3.exit_code == 0, r3.output
    after_commit = KernelSession(store_dir=str(tmp_path))
    assert cand.name in [s.name for s in after_commit.recovery_registry.ladder()]
    assert after_commit.recovery_candidate_registry.get(cand.id).status == "committed"

    # 4. Monitor with healthy real traffic — must NOT quarantine.
    base = datetime(2026, 6, 7, tzinfo=timezone.utc)
    needle = f"mined:{cand.id}"
    for i in range(15):
        after_commit.outcome_ledger.record(
            _post_commit_step(i < 13, base + timedelta(minutes=i),
                              recovered_by=needle)
        )
    for i in range(15):
        after_commit.outcome_ledger.record(
            _post_commit_step(i < 12, base + timedelta(minutes=30 + i),
                              recovered_by="container_proximity")
        )
    r4 = runner.invoke(cli_module.cli,
                       ["--store", str(tmp_path), "recovery", "monitor",
                        "--min-samples", "10", "--neg-lift", "0.1"])
    assert r4.exit_code == 0, r4.output
    assert "Quarantined 0" in r4.output
    final = KernelSession(store_dir=str(tmp_path))
    assert final.recovery_candidate_registry.get(cand.id).status == "committed"
    assert cand.name in [s.name for s in final.recovery_registry.ladder()]
