"""Phase B2 — auto-commit gate tests.

Six categories of coverage:

  1. Threshold gating: marginal candidates (just-ready) are NOT auto-committed.
  2. Strong candidates ARE auto-committed when whitelisted.
  3. Whitelist enforcement: non-whitelisted primitives stay at 'ready'.
  4. Status precondition: only 'ready' candidates are eligible.
  5. Audit trail: every auto-commit writes a behavior_audit row.
  6. Safety net: post-commit monitor still quarantines bad auto-committed
     strategies — auto-commit does not bypass the quarantine path.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.ontology.recovery_candidate import RecoveryCandidate
from browsermind_core.runtime.auto_commit_gate import (
    AUTO_COMMIT_MIN_LIFT,
    AUTO_COMMIT_MIN_SHADOW_SAMPLES,
    AUTO_COMMIT_PRIMITIVE_WHITELIST,
    auto_commit_candidate,
    commit_eligible_candidates,
    evaluate_auto_commit,
)
from browsermind_core.runtime.auto_pilot import AutoPilot
from browsermind_core.runtime.behavior_audit import BehaviorAuditLog
from browsermind_core.runtime.recovery_post_commit_monitor import sweep as monitor_sweep
from browsermind_core.runtime.recovery_registry import RecoveryStrategy
from browsermind_core.runtime.shadow_validator import ShadowValidator


# ---------------------------------------------------------------------------
# Helpers — synthetic shadow + outcome rows
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


def _ready_candidate(*, name="mined:strong", primitive="by_text",
                     predicate=None) -> RecoveryCandidate:
    return RecoveryCandidate(
        name=name,
        predicate=predicate or {"has_accessible_name": True},
        primitive=primitive,
        status="ready",
    )


# ---------------------------------------------------------------------------
# 1. Threshold gating
# ---------------------------------------------------------------------------


def test_marginal_ready_candidate_not_auto_committed(tmp_path):
    """A candidate that just barely cleared the human-ready gate (n=30, lift=0.10)
    must NOT be auto-committed. Auto-commit demands 3x more evidence."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate()
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    # Just past the human-ready threshold: 22/30 = 73%, baseline 18/30 = 60% → lift 0.13.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=22, n_total=30, baseline_n=18)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    assert len(results) == 1
    _, committed, reason = results[0]
    assert committed is False
    assert "below_min_shadow_samples" in reason or "lift_below_threshold" in reason

    after = ks.recovery_candidate_registry.get(cand.id)
    assert after.status == "ready"
    assert cand.name not in [s.name for s in ks.recovery_registry.ladder()]


def test_strong_candidate_is_auto_committed(tmp_path):
    """Triple-threshold candidate MUST auto-commit."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate()
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    # n=120 ≥ 100, would_resolve=110/120=0.917, baseline=12/120=0.10, lift=0.817.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    assert len(results) == 1
    _, committed, reason = results[0]
    assert committed is True, f"expected auto-commit, got reason: {reason}"
    assert "eligible" in reason

    after = ks.recovery_candidate_registry.get(cand.id)
    assert after.status == "committed"
    assert after.committed_at is not None
    assert cand.name in [s.name for s in ks.recovery_registry.ladder()]


def test_baseline_too_thin_blocks_commit(tmp_path):
    """Candidate must accumulate enough trials. n=80 < min_shadow_samples=100."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate()
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    # Strong lift but only 80 trials.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=72, n_total=80, baseline_n=8)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    _, committed, reason = results[0]
    assert committed is False
    assert "below_min_shadow_samples" in reason


def test_resolve_rate_too_low_blocks_commit(tmp_path):
    """Even with strong lift, resolve_rate < 0.80 blocks. Catches the case
    where mined strategy beats baseline only because baseline is terrible."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate()
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    # 60/120 = 50% resolve rate, baseline 0/120 = 0% → lift 0.50 (clears lift)
    # but resolve_rate 0.50 < 0.80 (blocks).
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=60, n_total=120, baseline_n=0)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    _, committed, reason = results[0]
    assert committed is False
    assert "resolve_rate_too_low" in reason


# ---------------------------------------------------------------------------
# 2. Whitelist enforcement
# ---------------------------------------------------------------------------


def test_non_whitelisted_primitive_blocks_commit(tmp_path):
    """A candidate with `by_capability` primitive must not auto-commit even
    when shadow evidence is overwhelming. by_capability is intentionally
    excluded from the whitelist (carries page-state context)."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate(primitive="by_capability")
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    _, committed, reason = results[0]
    assert committed is False
    assert "primitive_not_whitelisted" in reason
    assert "by_capability" in reason

    after = ks.recovery_candidate_registry.get(cand.id)
    assert after.status == "ready"


def test_whitelist_contains_only_routine_primitives():
    """Sanity check on the whitelist contents — drift catcher."""
    assert "by_role" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "by_text" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "by_placeholder" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "by_label" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "by_test_id" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "structural" in AUTO_COMMIT_PRIMITIVE_WHITELIST
    # Critical exclusions:
    assert "by_capability" not in AUTO_COMMIT_PRIMITIVE_WHITELIST
    assert "container_proximity" not in AUTO_COMMIT_PRIMITIVE_WHITELIST


# ---------------------------------------------------------------------------
# 3. Status precondition
# ---------------------------------------------------------------------------


def test_pending_candidate_is_not_auto_committable(tmp_path):
    """Candidates must pass the human-ready gate first. Pending is not eligible."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:pending",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="pending",
    )
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    # Direct evaluator call — should refuse on status.
    allow, reason, _ = evaluate_auto_commit(cand, validator=validator)
    assert allow is False
    assert "status_not_ready" in reason


def test_commit_eligible_only_inspects_ready_candidates(tmp_path):
    """Bulk sweep must skip pending/shadow/quarantined/etc."""
    ks = KernelSession(store_dir=str(tmp_path))
    for status in ("pending", "shadow", "quarantined", "rejected", "committed"):
        c = RecoveryCandidate(
            name=f"mined:{status}",
            predicate={"has_accessible_name": True},
            primitive="by_text",
            status=status,
        )
        ks.recovery_candidate_registry.save(c)

    validator = ShadowValidator(str(tmp_path))
    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    # No 'ready' candidates exist → sweep returns empty.
    assert results == []


# ---------------------------------------------------------------------------
# 4. Audit trail
# ---------------------------------------------------------------------------


def test_auto_commit_writes_audit_row(tmp_path):
    """Every auto-commit must leave a behavior_audit.jsonl row tagged
    prior_source='auto_commit'."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate()
    ks.recovery_candidate_registry.save(cand)

    audit_path = tmp_path / "audit.jsonl"
    audit = BehaviorAuditLog(path=audit_path)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    results = commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
        behavior_audit=audit,
    )
    assert all(ok for _, ok, _ in results)

    rows = audit.tail()
    assert len(rows) == 1
    row = rows[0]
    assert row["decision_point"] == "auto_commit_gate.recovery"
    assert row["prior_source"] == "auto_commit"
    assert row["picked"] == cand.name
    assert row["extra"]["candidate_id"] == str(cand.id)
    assert row["extra"]["primitive"] == "by_text"
    assert "metrics" in row["extra"]


# ---------------------------------------------------------------------------
# 5. Post-commit monitor still works on auto-committed candidates
# ---------------------------------------------------------------------------


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


def test_post_commit_monitor_quarantines_bad_auto_committed_strategy(tmp_path):
    """The safety invariant: an auto-committed strategy whose real-traffic
    lift goes negative is still quarantined by the post-commit monitor.
    Auto-commit is NOT a 'trusted' bypass."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate(name="mined:auto_then_bad")
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    # Step 1: auto-commit.
    commit_eligible_candidates(
        ks.recovery_candidate_registry,
        ks.recovery_registry,
        validator=validator,
    )
    after_commit = ks.recovery_candidate_registry.get(cand.id)
    assert after_commit.status == "committed"
    assert cand.name in [s.name for s in ks.recovery_registry.ladder()]

    # Step 2: real-traffic data shows the strategy is harmful.
    base = datetime.now(timezone.utc) + timedelta(seconds=1)
    needle = f"mined:{cand.id}"
    records = []
    for i in range(25):
        records.append(_post_commit_step(
            i < 2, base + timedelta(minutes=i), recovered_by=needle))
    for i in range(25):
        records.append(_post_commit_step(
            i < 22, base + timedelta(minutes=30 + i),
            recovered_by="container_proximity"))

    # Step 3: monitor sweep must quarantine.
    results = monitor_sweep(
        records, ks.recovery_candidate_registry, ks.recovery_registry,
        min_samples=10, neg_lift_threshold=0.1,
    )
    assert any(flagged for _, _, flagged in results)
    after_quar = ks.recovery_candidate_registry.get(cand.id)
    assert after_quar.status == "quarantined"
    assert cand.name not in [s.name for s in ks.recovery_registry.ladder()]


# ---------------------------------------------------------------------------
# 6. AutoPilot integration — auto_committed surfaces in last_results
# ---------------------------------------------------------------------------


def test_autopilot_sweep_reports_auto_committed_count(tmp_path):
    """AutoPilot._safe_sweep must report the auto_committed count alongside
    promoted_to_ready, so operators can see how many human gates were
    bypassed by the statistical gate per cycle."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate(name="mined:autopilot")
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=110, n_total=120, baseline_n=12)

    pilot = AutoPilot(ks, interval=10)
    pilot.notify_steps_recorded(10)
    sweep_result = pilot.last_results.get("sweep") or {}
    assert "auto_committed" in sweep_result
    assert sweep_result["auto_committed"] >= 1

    after = ks.recovery_candidate_registry.get(cand.id)
    assert after.status == "committed"


def test_autopilot_sweep_does_not_auto_commit_marginal(tmp_path):
    """Through the full AutoPilot path, marginal candidates stay at 'ready'."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = _ready_candidate(name="mined:marginal")
    ks.recovery_candidate_registry.save(cand)

    validator = ShadowValidator(str(tmp_path))
    # Just over human-ready, well below auto-commit.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=22, n_total=30, baseline_n=18)

    pilot = AutoPilot(ks, interval=10)
    pilot.notify_steps_recorded(10)
    sweep_result = pilot.last_results.get("sweep") or {}
    assert sweep_result.get("auto_committed", 0) == 0

    after = ks.recovery_candidate_registry.get(cand.id)
    assert after.status == "ready"


# ---------------------------------------------------------------------------
# 7. Source-level guardrail: no autonomous commit path outside the gate
# ---------------------------------------------------------------------------


def test_auto_commit_path_only_lives_in_auto_commit_gate():
    """The phrase `update_status(... "committed" ...)` should only appear in:
      - browsermind_core/runtime/auto_commit_gate.py (auto path)
      - browsermind_core/console/cli.py (human path)
    Any other appearance in production code is a missing safety check.
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r'update_status\([^)]*"committed"', re.DOTALL)
    offenders = []
    for py in root.glob("**/*.py"):
        if "tests" in py.parts:
            continue
        if py.name in ("auto_commit_gate.py",):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        if pattern.search(text):
            offenders.append(str(py.relative_to(root)))
    # cli.py contains the human-approval committed transition.
    allowed = {"console\\cli.py", "console/cli.py"}
    real_offenders = [o for o in offenders if o not in allowed]
    assert real_offenders == [], (
        f"Found new committed-transition site outside auto_commit_gate: "
        f"{real_offenders}"
    )
