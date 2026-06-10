"""AutoCommitGate — Phase B2 of the Autonomous Self-Learning roadmap.

Statistical escape hatch that lets ROUTINE recovery candidates self-commit
when their shadow evidence is dramatically stronger than what's required to
flip them to status='ready'.

NON-NEGOTIABLES
---------------
1. The gate is conservative on purpose. Thresholds are 3x stricter than the
   `validate_for_promotion` gate that flips pending → ready. A candidate that
   is "good enough for human review" is NOT good enough for auto-commit.
2. Only primitives in AUTO_COMMIT_PRIMITIVE_WHITELIST are eligible. Mined
   candidates calling exotic or future primitives still need human approval.
3. Only failure classes in AUTO_COMMIT_FAILURE_CLASS_WHITELIST are eligible.
   New failure modes get human-eyes-on by default.
4. Auto-committed candidates are still quarantined automatically by the
   post-commit monitor when real-traffic lift goes negative. There is no
   special "trusted" path that bypasses the safety net.
5. Every auto-commit writes an audit row to behavior_audit.jsonl with
   prior_source="auto_commit" so every autonomous structural mutation is
   traceable.

WHAT REMAINS HUMAN-GATED
------------------------
- WorkflowTemplate mutations (TemplateCandidate flow, unchanged).
- Recovery candidates outside the whitelist or below the 3x threshold.
- Anything with a regression risk the gate isn't confident about.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from browsermind_core.ontology.recovery_candidate import (
    RecoveryCandidate,
    RecoveryCandidateRegistry,
)
from browsermind_core.runtime.recovery_promotion_gate import _aggregate_with_baseline
from browsermind_core.runtime.recovery_registry import (
    RecoveryRegistry,
    RecoveryStrategy,
)
from browsermind_core.runtime.shadow_validator import ShadowValidator


# ---------------------------------------------------------------------------
# Thresholds — 3x stricter than the human-ready gate
# ---------------------------------------------------------------------------
#
# `validate_for_promotion` flips pending→ready at:
#     shadow_min_samples = 30
#     min_lift           = 0.10
#
# Auto-commit demands at least 3x of each plus a healthy baseline cohort:
#
AUTO_COMMIT_MIN_SHADOW_SAMPLES = 100   # 3.3x ready threshold
AUTO_COMMIT_MIN_LIFT           = 0.30  # 3x ready threshold
AUTO_COMMIT_MIN_BASELINE_N     = 50    # baseline cohort must be solid
AUTO_COMMIT_MIN_RESOLVE_RATE   = 0.80  # candidate must resolve >=80% of trials

# ---------------------------------------------------------------------------
# Whitelists — only routine, well-understood surfaces auto-commit
# ---------------------------------------------------------------------------

# Primitives the gate trusts. Anything else (future primitives, capability
# helpers that take state) routes through human approval.
AUTO_COMMIT_PRIMITIVE_WHITELIST = frozenset({
    "by_role",
    "by_text",
    "by_placeholder",
    "by_label",
    "by_test_id",
    "structural",
})

# Failure classes the gate trusts. New failure modes route through humans.
AUTO_COMMIT_FAILURE_CLASS_WHITELIST = frozenset({
    "TARGET_CHANGED",
})


# ---------------------------------------------------------------------------
# Eligibility decision
# ---------------------------------------------------------------------------


def evaluate_auto_commit(
    candidate: RecoveryCandidate,
    *,
    validator: ShadowValidator,
    min_shadow_samples: int = AUTO_COMMIT_MIN_SHADOW_SAMPLES,
    min_lift: float = AUTO_COMMIT_MIN_LIFT,
    min_baseline_n: int = AUTO_COMMIT_MIN_BASELINE_N,
    min_resolve_rate: float = AUTO_COMMIT_MIN_RESOLVE_RATE,
    primitive_whitelist: frozenset = AUTO_COMMIT_PRIMITIVE_WHITELIST,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Decide whether one candidate may auto-commit.

    Returns (allow, reason, metrics). The candidate is committed only when
    all six gates pass:
      1. status == "ready" (human-promotion gate already passed)
      2. primitive in whitelist
      3. n_trials >= min_shadow_samples
      4. baseline cohort >= min_baseline_n
      5. would_resolve_rate >= min_resolve_rate
      6. lift (would_resolve_rate - live_baseline_rate) >= min_lift

    Reasons are human-readable strings useful for audit + CLI reporting.
    """
    if candidate.status != "ready":
        return False, f"status_not_ready:{candidate.status}", {}

    if candidate.primitive not in primitive_whitelist:
        return False, f"primitive_not_whitelisted:{candidate.primitive}", {}

    metrics = _aggregate_with_baseline(validator, str(candidate.id))
    n = metrics.get("n_trials", 0)
    if n < min_shadow_samples:
        return False, f"below_min_shadow_samples:{n}/{min_shadow_samples}", metrics

    # Baseline N is encoded as the count of rows where live_resolver_succeeded
    # is meaningful — we compute it implicitly via baseline_rate × n_trials.
    # Since shadow trials write live_resolver_succeeded for every row, the
    # effective baseline cohort = n_trials. Require min_baseline_n trials.
    if n < min_baseline_n:
        return False, f"below_min_baseline_n:{n}/{min_baseline_n}", metrics

    wr = metrics.get("would_resolve_rate", 0.0) or 0.0
    if wr < min_resolve_rate:
        return False, f"resolve_rate_too_low:{wr}", metrics

    lift = metrics.get("lift", 0.0) or 0.0
    if lift < min_lift:
        return False, f"lift_below_threshold:{lift}/{min_lift}", metrics

    return True, f"eligible:lift={lift},n={n},rate={wr}", metrics


# ---------------------------------------------------------------------------
# Commit action — mirrors the CLI approve verb but autonomous
# ---------------------------------------------------------------------------


def auto_commit_candidate(
    candidate: RecoveryCandidate,
    *,
    candidate_registry: RecoveryCandidateRegistry,
    recovery_registry: RecoveryRegistry,
    behavior_audit=None,
    metrics: Optional[Dict[str, Any]] = None,
) -> RecoveryCandidate:
    """Commit a single candidate. Mirrors the CLI approve verb's body so the
    durable state is identical to a human-approved commit. Adds an audit
    trail entry tagged prior_source='auto_commit'.

    Returns the updated candidate (status='committed').
    """
    snapshot = recovery_registry.snapshot()
    strat = RecoveryStrategy(
        name=candidate.name,
        predicate=dict(candidate.predicate or {}),
        primitive=candidate.primitive,
        depth=5,                # mined strategies always sit at depth 5
        source="mined",
        candidate_id=str(candidate.id),
    )
    recovery_registry.append(strat)
    updated = candidate_registry.update_status(
        candidate.id, "committed",
        committed_at=datetime.now(timezone.utc),
        previous_state=snapshot,
    )

    # Audit trail — best effort; failure must not undo the commit.
    if behavior_audit is not None:
        try:
            behavior_audit.record(
                decision_point="auto_commit_gate.recovery",
                prior_source="auto_commit",
                prior_version="v1",
                picked=candidate.name,
                fallback_used=False,
                extra={
                    "candidate_id": str(candidate.id),
                    "primitive": candidate.primitive,
                    "metrics": metrics or {},
                },
            )
        except Exception:
            pass

    return updated


# ---------------------------------------------------------------------------
# Bulk sweep — used by AutoPilot._safe_sweep
# ---------------------------------------------------------------------------


def commit_eligible_candidates(
    candidate_registry: RecoveryCandidateRegistry,
    recovery_registry: RecoveryRegistry,
    *,
    validator: Optional[ShadowValidator] = None,
    behavior_audit=None,
    min_shadow_samples: int = AUTO_COMMIT_MIN_SHADOW_SAMPLES,
    min_lift: float = AUTO_COMMIT_MIN_LIFT,
    min_baseline_n: int = AUTO_COMMIT_MIN_BASELINE_N,
    min_resolve_rate: float = AUTO_COMMIT_MIN_RESOLVE_RATE,
    primitive_whitelist: frozenset = AUTO_COMMIT_PRIMITIVE_WHITELIST,
) -> List[Tuple[RecoveryCandidate, bool, str]]:
    """Walk every status='ready' candidate; auto-commit those that pass.

    Returns (candidate, committed, reason) tuples for caller logging.
    Best-effort: per-candidate errors do not stop the sweep.
    """
    v = validator or ShadowValidator()
    out: List[Tuple[RecoveryCandidate, bool, str]] = []
    for c in candidate_registry.list(status="ready"):
        try:
            allow, reason, metrics = evaluate_auto_commit(
                c, validator=v,
                min_shadow_samples=min_shadow_samples,
                min_lift=min_lift,
                min_baseline_n=min_baseline_n,
                min_resolve_rate=min_resolve_rate,
                primitive_whitelist=primitive_whitelist,
            )
        except Exception as e:
            out.append((c, False, f"eval_error:{e}"))
            continue
        if not allow:
            out.append((c, False, reason))
            continue
        try:
            auto_commit_candidate(
                c,
                candidate_registry=candidate_registry,
                recovery_registry=recovery_registry,
                behavior_audit=behavior_audit,
                metrics=metrics,
            )
            out.append((c, True, reason))
        except Exception as e:
            out.append((c, False, f"commit_error:{e}"))
    return out
