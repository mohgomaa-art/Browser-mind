"""R6 v1 — full evidence-pipeline tests.

Covers the 8 requirements in the R6 contract:
  1. R1-R5 behavior unchanged (data-driven ladder produces identical labels).
  2. RecoveryCandidate creation works.
  3. Shadow validation produces evidence (read-only, never clicks).
  4. Promotion gate blocks weak candidates.
  5. Approval required before commit (no auto-commit anywhere).
  6. Rollback restores previous ladder.
  7. RecoveryRegistry loads correctly (seed + reload + persistence).
  8. Quarantined candidates never execute.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from click.testing import CliRunner

from browsermind_core.console import cli as cli_module
from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.ontology.recovery_candidate import (
    RecoveryCandidate, RecoveryCandidateRegistry,
)
from browsermind_core.runtime.primitive_library import (
    PRIMITIVE_LIBRARY, get_primitive, known_primitives,
)
from browsermind_core.runtime.recovery_post_commit_monitor import (
    measure_candidate, should_quarantine, sweep,
)
from browsermind_core.runtime.recovery_promotion_gate import (
    evaluate_candidate, refresh_registry,
)
from browsermind_core.runtime.recovery_registry import (
    RecoveryRegistry, RecoveryStrategy, predicate_matches,
)
from browsermind_core.runtime.shadow_validator import ShadowValidator
from browsermind_core.runtime.target_resolver import TargetResolver
from browsermind_core.training.descriptor_features import (
    BOOLEAN_FEATURE_KEYS, features, features_from_metrics,
)
from browsermind_core.training.failure_pattern_miner import (
    PatternCandidate, mine_patterns, split_cohorts, to_recovery_candidate,
)


# =============================================================================
# Phase 1 — DescriptorFeatureExtractor
# =============================================================================


def test_features_returns_stable_keys():
    out = features({}, {})
    for k in BOOLEAN_FEATURE_KEYS:
        assert k in out


def test_features_presence_flags_match_descriptor_fields():
    out = features(
        {"accessible_name": "Submit", "placeholder": "", "dom_path": "div > button"},
        {"candidate_count": 1, "resolved_text": "Submit"},
    )
    assert out["has_accessible_name"] is True
    assert out["has_placeholder"] is False
    assert out["has_dom_path"] is True
    assert out["candidate_count_eq_1"] is True
    assert out["name_text_similarity_gte_0_8"] is True


# =============================================================================
# Phase 7 — RecoveryRegistry seed + reload (Requirement 7)
# =============================================================================


def test_registry_seeds_with_R1_R5_on_first_load(tmp_path):
    reg = RecoveryRegistry(str(tmp_path))
    rows = reg.ladder()
    names = [r.name for r in rows]
    # Order matters — must match the historical R1-R5b sequence.
    assert names == [
        "container_proximity",
        "placeholder",
        "accessible_name",
        "nearby_text",
        "structural_path",
        "affordance_intent",
        "capability_intent",
    ]
    assert all(r.source == "builtin" for r in rows)


def test_registry_persists_across_instances(tmp_path):
    r1 = RecoveryRegistry(str(tmp_path))
    r1.append(RecoveryStrategy(
        name="mined:test",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        depth=5,
        source="mined",
        candidate_id="abc",
    ))
    r2 = RecoveryRegistry(str(tmp_path))
    names = [r.name for r in r2.ladder()]
    assert "mined:test" in names


# =============================================================================
# Phase 1 — Predicate matcher
# =============================================================================


def test_predicate_matches_empty_predicate_matches_anything():
    assert predicate_matches({}, {"has_x": False}) is True


def test_predicate_matches_boolean_strict():
    assert predicate_matches(
        {"has_accessible_name": True}, {"has_accessible_name": True}
    ) is True
    assert predicate_matches(
        {"has_accessible_name": True}, {"has_accessible_name": False}
    ) is False


# =============================================================================
# Phase 4 — RecoveryCandidate creation works (Requirement 2)
# =============================================================================


def test_recovery_candidate_save_get_list(tmp_path):
    reg = RecoveryCandidateRegistry(str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:by_text",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        support=63,
        lift=5.25,
        mined_from=["a", "b"],
    )
    reg.save(cand)
    fetched = reg.get(cand.id)
    assert fetched is not None
    assert fetched.primitive == "by_text"
    assert fetched.status == "pending"
    listed = reg.list(status="pending")
    assert any(c.id == cand.id for c in listed)


# =============================================================================
# Phase 2 — Pattern miner (Requirement 2: candidate emission from evidence)
# =============================================================================


def _seed_step(success, ts, *, recovered_by="", failure_class="TARGET_CHANGED",
               action="click", role="button", name="Submit",
               env="saucedemo"):
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
            "action": action, "role": role, "name": name,
            "recovered_by": recovered_by,
            "failure_class": failure_class,
            "actual_outcome": "SUCCESS" if success else "FAILED",
        },
    )


def test_split_cohorts_filters_by_recovery():
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    records = [
        _seed_step(True, base, recovered_by="container_proximity"),    # recovered
        _seed_step(False, base, recovered_by=""),                       # unrecovered
        _seed_step(False, base, recovered_by="something"),              # NOT unrecovered (had recovery)
    ]
    unrec, rec = split_cohorts(records)
    assert len(unrec) == 1
    assert len(rec) == 1


def test_mine_patterns_emits_pattern_candidate_with_lift():
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # 25 unrecovered failures with name="Submit" (has_accessible_name=True)
    # 5 recovered with same descriptor — 5x lift
    records = []
    for i in range(25):
        records.append(_seed_step(False, base, recovered_by="", name="Submit"))
    for i in range(5):
        records.append(_seed_step(True, base, recovered_by="container_proximity",
                                   name="Submit"))
    patterns = mine_patterns(records, min_support=10, min_lift=2.0)
    assert len(patterns) >= 1
    p = patterns[0]
    assert p.support >= 10
    assert p.lift >= 2.0
    assert p.suggested_primitive in known_primitives()


# =============================================================================
# Phase 5 — Shadow validation (Requirement 3: read-only evidence)
# =============================================================================


@pytest.mark.asyncio
async def test_shadow_trial_records_would_resolve_without_clicking(tmp_path):
    """Verify the shadow trial calls .count() but never .click()/.fill()."""
    validator = ShadowValidator(str(tmp_path))

    # Fake locator that records every method call.
    calls = []
    fake_loc = MagicMock()

    async def _count():
        calls.append("count")
        return 1
    fake_loc.count = _count
    # If anything tries to mutate, we want to know.
    fake_loc.click = AsyncMock(side_effect=AssertionError("click() must not be called"))
    fake_loc.fill = AsyncMock(side_effect=AssertionError("fill() must not be called"))

    # Patch the primitive library so it returns our fake locator.
    cand = RecoveryCandidate(
        name="mined:by_text",
        predicate={"has_accessible_name": True},
        primitive="by_text",
    )

    # Inject a tiny fake primitive lookup by monkey-patching via the module.
    import browsermind_core.runtime.primitive_library as pl_mod

    async def fake_primitive(page, descriptor, *, resolver=None, read_only=False):
        return fake_loc
    original = pl_mod.PRIMITIVE_LIBRARY.get("by_text")
    pl_mod.PRIMITIVE_LIBRARY["by_text"] = fake_primitive
    try:
        page = MagicMock()
        result = await validator.shadow_trial(
            candidate=cand, page=page,
            descriptor={"accessible_name": "Submit"},
            feature_vector={"has_accessible_name": True},
            step_id="1", persona="alpha", env="saucedemo",
            live_resolver_succeeded=False,
        )
    finally:
        if original is not None:
            pl_mod.PRIMITIVE_LIBRARY["by_text"] = original

    assert result["would_resolve"] is True
    assert "count" in calls
    fake_loc.click.assert_not_awaited()
    fake_loc.fill.assert_not_awaited()
    rows = validator.tail()
    assert len(rows) == 1


def test_shadow_aggregate_returns_rate(tmp_path):
    validator = ShadowValidator(str(tmp_path))
    cid = "abc-123"
    # Hand-roll three shadow rows.
    validator.path.parent.mkdir(parents=True, exist_ok=True)
    with validator.path.open("a", encoding="utf-8") as f:
        for would in (True, True, False):
            f.write(json.dumps({
                "ts": "2026-06-07T00:00:00+00:00",
                "candidate_id": cid,
                "primitive": "by_text",
                "would_resolve": would,
                "candidate_count": 1 if would else 0,
                "live_resolver_succeeded": False,
            }) + "\n")
    agg = validator.aggregate(cid)
    assert agg["n_trials"] == 3
    assert agg["n_would_resolve"] == 2
    assert agg["would_resolve_rate"] == pytest.approx(2 / 3, rel=1e-3)


# =============================================================================
# Phase 6 — Promotion gate (Requirement 4: weak candidates blocked)
# =============================================================================


def _seed_shadow(path: Path, candidate_id: str, *, n_resolve: int, n_total: int,
                 baseline_n: int = 0):
    """Write n_total rows for candidate_id; n_resolve of them with would_resolve=True.
    Some `baseline_n` rows have live_resolver_succeeded=True."""
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


def test_promotion_gate_rejects_thin_sample(tmp_path):
    cand = RecoveryCandidate(name="x", predicate={}, primitive="by_text")
    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id), n_resolve=10, n_total=10)
    allow, reason, metrics = evaluate_candidate(
        cand, validator=validator, shadow_min_samples=30,
    )
    assert allow is False
    assert "below_shadow_min_samples" in reason


def test_promotion_gate_rejects_negative_lift(tmp_path):
    cand = RecoveryCandidate(name="x", predicate={}, primitive="by_text")
    validator = ShadowValidator(str(tmp_path))
    # 5 / 30 = 0.167 vs baseline 25 / 30 = 0.833 — strongly negative lift.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=5, n_total=30, baseline_n=25)
    allow, reason, _ = evaluate_candidate(
        cand, validator=validator, shadow_min_samples=30, min_lift=0.1,
    )
    assert allow is False


def test_promotion_gate_accepts_strong_candidate(tmp_path):
    cand = RecoveryCandidate(name="x", predicate={}, primitive="by_text")
    validator = ShadowValidator(str(tmp_path))
    # 28 / 30 = 0.933 vs baseline 0 / 30 = 0.0 — large positive lift.
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=28, n_total=30, baseline_n=0)
    allow, reason, metrics = evaluate_candidate(
        cand, validator=validator, shadow_min_samples=30, min_lift=0.1,
    )
    assert allow is True
    assert metrics["lift"] > 0.5


def test_refresh_registry_flips_status_to_ready(tmp_path):
    reg = RecoveryCandidateRegistry(str(tmp_path))
    cand = RecoveryCandidate(name="strong", predicate={}, primitive="by_text")
    reg.save(cand)
    validator = ShadowValidator(str(tmp_path))
    _seed_shadow(validator.path, str(cand.id),
                 n_resolve=28, n_total=30, baseline_n=0)
    refresh_registry(reg, validator=validator,
                     shadow_min_samples=30, min_lift=0.1)
    after = reg.get(cand.id)
    assert after.status == "ready"


# =============================================================================
# Phase 7 — Approval CLI (Requirement 5: approval required before commit)
# =============================================================================


def test_cli_recovery_candidate_approve_appends_to_ladder(tmp_path):
    runner = CliRunner()
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:by_text+name",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="ready",
    )
    ks.recovery_candidate_registry.save(cand)

    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "candidate", "approve", str(cand.id)],
    )
    assert result.exit_code == 0, result.output

    ks2 = KernelSession(store_dir=str(tmp_path))
    names = [s.name for s in ks2.recovery_registry.ladder()]
    assert "mined:by_text+name" in names
    assert ks2.recovery_candidate_registry.get(cand.id).status == "committed"


def test_cli_recovery_candidate_no_auto_commit_on_pending(tmp_path):
    """Pending → committed only via explicit `approve`; no implicit promotion."""
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:test",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="pending",
    )
    ks.recovery_candidate_registry.save(cand)
    # Re-open without invoking any CLI verb.
    ks2 = KernelSession(store_dir=str(tmp_path))
    after = ks2.recovery_candidate_registry.get(cand.id)
    assert after.status == "pending"
    assert "mined:test" not in [s.name for s in ks2.recovery_registry.ladder()]


def test_cli_recovery_candidate_reject(tmp_path):
    runner = CliRunner()
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(name="x", predicate={}, primitive="by_text",
                             status="pending")
    ks.recovery_candidate_registry.save(cand)
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "candidate", "reject", str(cand.id)],
    )
    assert result.exit_code == 0, result.output
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.get(cand.id).status == "rejected"


# =============================================================================
# Phase 7 — Rollback (Requirement 6)
# =============================================================================


def test_cli_recovery_candidate_rollback_restores_ladder(tmp_path):
    runner = CliRunner()
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(
        name="mined:rollback_test",
        predicate={"has_accessible_name": True},
        primitive="by_text",
        status="ready",
    )
    ks.recovery_candidate_registry.save(cand)

    # Approve.
    runner.invoke(cli_module.cli,
                  ["--store", str(tmp_path), "recovery", "candidate",
                   "approve", str(cand.id)])
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert "mined:rollback_test" in [s.name for s in ks2.recovery_registry.ladder()]

    # Rollback.
    result = runner.invoke(cli_module.cli,
                           ["--store", str(tmp_path), "recovery", "candidate",
                            "rollback", str(cand.id)])
    assert result.exit_code == 0, result.output

    ks3 = KernelSession(store_dir=str(tmp_path))
    names = [s.name for s in ks3.recovery_registry.ladder()]
    assert "mined:rollback_test" not in names
    assert ks3.recovery_candidate_registry.get(cand.id).status == "rolled_back"


def test_cli_recovery_candidate_rollback_refuses_non_committed(tmp_path):
    runner = CliRunner()
    ks = KernelSession(store_dir=str(tmp_path))
    cand = RecoveryCandidate(name="x", predicate={}, primitive="by_text",
                             status="pending")
    ks.recovery_candidate_registry.save(cand)
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "recovery", "candidate", "rollback", str(cand.id)],
    )
    # Rollback on pending must NOT alter the candidate.
    assert "must" in result.output.lower() or "committed" in result.output.lower()
    ks2 = KernelSession(store_dir=str(tmp_path))
    assert ks2.recovery_candidate_registry.get(cand.id).status == "pending"


# =============================================================================
# Phase 9 — Quarantined candidates never execute (Requirement 8)
# =============================================================================


def test_registry_hides_quarantined_strategies(tmp_path):
    reg = RecoveryRegistry(str(tmp_path))
    reg.append(RecoveryStrategy(
        name="mined:harmful", predicate={}, primitive="by_text",
        depth=5, source="mined", candidate_id="bad-id",
    ))
    assert "mined:harmful" in [s.name for s in reg.ladder()]
    reg.quarantine("bad-id")
    assert "mined:harmful" not in [s.name for s in reg.ladder()]
    # But the quarantined row is still present when explicitly requested
    # (so the audit trail / rollback path can find it).
    full = reg.ladder(include_quarantined=True)
    assert "mined:harmful" in [s.name for s in full]


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


def test_post_commit_sweep_quarantines_negative_lift(tmp_path):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cand = RecoveryCandidate(
        name="mined:weak", predicate={}, primitive="by_text",
        status="committed",
    )
    cand.committed_at = base - timedelta(hours=1)
    cand_reg = RecoveryCandidateRegistry(str(tmp_path))
    cand_reg.save(cand)
    rec_reg = RecoveryRegistry(str(tmp_path))
    rec_reg.append(RecoveryStrategy(
        name="mined:weak", predicate={}, primitive="by_text",
        depth=5, source="mined", candidate_id=str(cand.id),
    ))

    needle = f"mined:{cand.id}"
    records = []
    # 25 mined trials, 2 successes — 8% success rate.
    for i in range(25):
        records.append(_post_commit_step(i < 2, base + timedelta(minutes=i),
                                         recovered_by=needle))
    # 25 builtin trials, 22 successes — 88% baseline.
    for i in range(25):
        records.append(_post_commit_step(i < 22, base + timedelta(minutes=30 + i),
                                         recovered_by="container_proximity"))

    results = sweep(records, cand_reg, rec_reg,
                    min_samples=10, neg_lift_threshold=0.1)
    assert len(results) == 1
    _, metrics, flagged = results[0]
    assert flagged is True
    assert metrics["lift"] is not None and metrics["lift"] < 0
    assert cand_reg.get(cand.id).status == "quarantined"
    assert "mined:weak" not in [s.name for s in rec_reg.ladder()]


# =============================================================================
# Requirement 1 — R1-R5 behavior unchanged via data-driven ladder
# =============================================================================


def test_seeded_ladder_reproduces_R1_R5_strategy_set(tmp_path):
    """The seeded ladder names + depths reproduce the historical R1-R5b."""
    reg = RecoveryRegistry(str(tmp_path))
    rows = reg.ladder()
    expected = {
        "container_proximity": 1,
        "placeholder": 1,
        "accessible_name": 2,
        "nearby_text": 2,
        "structural_path": 3,
        "affordance_intent": 4,
        "capability_intent": 4,
    }
    seen = {r.name: r.depth for r in rows}
    assert seen == expected


def test_resolver_accepts_recovery_registry_kwarg():
    import inspect
    sig = inspect.signature(TargetResolver.__init__)
    assert "recovery_registry" in sig.parameters
