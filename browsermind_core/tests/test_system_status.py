"""bm system status — honesty surface tests.

Three behaviors:
  1. Empty store reports PLUMBED BUT DRY with all zeros.
  2. After synthetic real-traffic + auto-commit, reports LEARNING ACTUALIZED.
  3. CLI verb works in both formatted and JSON modes.
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
from browsermind_core.runtime.auto_commit_gate import commit_eligible_candidates
from browsermind_core.runtime.behavior_audit import BehaviorAuditLog
from browsermind_core.runtime.shadow_validator import ShadowValidator
from browsermind_core.training.system_status import (
    compute_status,
    render_status_lines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_shadow(path: Path, candidate_id: str, *,
                 n_resolve: int, n_total: int, baseline_n: int = 0):
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


def _step_record(success, ts):
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="testfam",
        environment_instance="saucedemo",
        outcome_type="step_attempt",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={"action": "click", "role": "button", "name": "Submit",
                 "actual_outcome": "SUCCESS" if success else "FAILED"},
    )


def _run_record(success, ts):
    return OutcomeRecord(
        scope="workflow_instance",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="testfam",
        environment_instance="saucedemo",
        outcome_type="replay_run",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={"status": "SUCCESS" if success else "FAILED"},
    )


# ---------------------------------------------------------------------------
# Empty-store baseline (the case BrowserMind is in today)
# ---------------------------------------------------------------------------


def test_empty_store_reports_plumbed_but_dry(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    status = compute_status(ks)

    assert status["actualization"]["is_learning_actualized"] is False
    assert status["actualization"]["auto_committed_observed"] == 0
    assert status["actualization"]["human_committed_mined_observed"] == 0
    assert status["evidence"]["step_records"] == 0
    assert status["evidence"]["run_records"] == 0
    assert status["evidence"]["last_real_replay_at"] is None
    assert status["evidence"]["shadow_trials"] == 0
    assert status["evidence"]["audit_auto_commits"] == 0
    # The seeded ladder still has R1-R5b builtins on a fresh store.
    assert status["ladder"]["builtin_strategies"] >= 6
    assert status["ladder"]["mined_strategies_active"] == 0


def test_empty_store_render_starts_with_plumbed_but_dry(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    lines = render_status_lines(compute_status(ks))
    assert "PLUMBED BUT DRY" in lines[0]


# ---------------------------------------------------------------------------
# Step records alone do not flip actualization
# ---------------------------------------------------------------------------


def test_step_records_without_commits_still_dry(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    base = datetime(2026, 6, 7, tzinfo=timezone.utc)
    for i in range(5):
        ks.outcome_ledger.record(_step_record(False, base + timedelta(seconds=i)))
        ks.outcome_ledger.record(_run_record(False, base + timedelta(seconds=i)))
    status = compute_status(ks)
    assert status["evidence"]["step_records"] == 5
    assert status["evidence"]["run_records"] == 5
    assert status["evidence"]["last_real_replay_at"] is not None
    # No commits → still dry.
    assert status["actualization"]["is_learning_actualized"] is False


# ---------------------------------------------------------------------------
# Auto-commit on top of step records flips actualization
# ---------------------------------------------------------------------------


def test_auto_commit_flips_to_learning_actualized(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    base = datetime(2026, 6, 7, tzinfo=timezone.utc)
    # Seed a real replay history.
    ks.outcome_ledger.record(_step_record(True, base))
    ks.outcome_ledger.record(_run_record(True, base))

    # Seed a strong-evidence candidate.
    cand = RecoveryCandidate(
        name="mined:strong",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="ready",
    )
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    audit = BehaviorAuditLog(path=Path(str(tmp_path)) / "audit" / "behavior_audit.jsonl")
    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
        behavior_audit=audit,
    )
    assert all(ok for _, ok, _ in results)

    status = compute_status(ks)
    assert status["actualization"]["is_learning_actualized"] is True
    assert status["actualization"]["auto_committed_observed"] == 1
    assert status["evidence"]["audit_auto_commits"] == 1
    assert status["candidates"]["committed_mined_strategies"] == ["mined:strong"]
    assert status["ladder"]["mined_strategies_active"] == 1


# ---------------------------------------------------------------------------
# Quarantines surface
# ---------------------------------------------------------------------------


def test_quarantined_candidate_visible_in_status(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:bad",
        predicate={},
        primitive="by_text",
        status="quarantined",
    )
    ks.recovery_candidate_registry.save(cand)
    status = compute_status(ks)
    assert status["actualization"]["quarantines_observed"] == 1
    assert status["candidates"]["quarantined_mined_strategies"] == ["mined:bad"]


# ---------------------------------------------------------------------------
# CLI verb
# ---------------------------------------------------------------------------


def test_cli_system_status_text_mode(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "system", "status"],
    )
    assert result.exit_code == 0, result.output
    assert "Bottom line:" in result.output
    assert "EVIDENCE" in result.output
    assert "ACTUALIZATION" in result.output
    assert "PLUMBED BUT DRY" in result.output


def test_cli_system_status_json_mode(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "system", "status", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "browsermind.system_status.v1"
    assert payload["actualization"]["is_learning_actualized"] is False


def test_cli_system_status_after_auto_commit_reports_actualized(tmp_path):
    """End-to-end: seed evidence + auto-commit, then call the CLI verb."""
    ks = KernelSession(store_dir=str(tmp_path))
    base = datetime(2026, 6, 7, tzinfo=timezone.utc)
    ks.outcome_ledger.record(_step_record(True, base))
    ks.outcome_ledger.record(_run_record(True, base))

    cand = RecoveryCandidate(
        name="mined:cli_test",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="ready",
    )
    ks.recovery_candidate_registry.save(cand)
    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)
    audit = BehaviorAuditLog(path=Path(str(tmp_path)) / "audit" / "behavior_audit.jsonl")
    commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
        behavior_audit=audit,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "system", "status"],
    )
    assert result.exit_code == 0, result.output
    assert "LEARNING ACTUALIZED" in result.output
    assert "auto_committed observed:   1" in result.output
