"""RecoveryPostCommitMonitor — Phase 9 of R6 v1.

Once a mined RecoveryCandidate is committed, it appears in the live ladder
as a row tagged `recovered_by="mined:<candidate_id>"` on FailureAttribution
rows it resolves. This module aggregates those tags from the OutcomeLedger
to detect post-commit regressions.

Decision rule:
    - If n_after_commit < POSTCOMMIT_MIN_SAMPLES → do nothing yet.
    - If real-traffic success_rate < live_baseline - QUARANTINE_NEG_LIFT
      → quarantine the strategy in the RecoveryRegistry AND flip the
        candidate's status to "quarantined".

This closes the loop:
    mined strategy → live use → outcome rows → effectiveness audit →
    quarantine when harmful.

Pure functions over OutcomeLedger records. Does not mutate the page,
the resolver, or the candidate's previous_state (which remains
available for `bm recovery candidate rollback`).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from browsermind_core.ontology.recovery_candidate import (
    RecoveryCandidate, RecoveryCandidateRegistry,
)
from browsermind_core.runtime.recovery_registry import RecoveryRegistry


POSTCOMMIT_MIN_SAMPLES = 20
QUARANTINE_NEG_LIFT = 0.10   # candidate worse than baseline by 10pp triggers quarantine
MINED_RECOVERED_BY_PREFIX = "mined:"


def _committed_at(c: RecoveryCandidate):
    return c.committed_at


def _is_step_attempt(rec) -> bool:
    return rec.scope == "step" and rec.outcome_type == "step_attempt"


def measure_candidate(
    records: Iterable[Any],
    candidate: RecoveryCandidate,
) -> Dict[str, Any]:
    """Compute post-commit success metrics for one committed candidate.

    Splits records into:
      - mined cohort: rows whose metrics.recovered_by == 'mined:<candidate.id>'
      - baseline cohort: rows post-dating commit whose recovered_by is non-empty
        and NOT prefixed 'mined:' (i.e. the legacy R1-R5 ladder)
    """
    cid = str(candidate.id)
    needle = f"{MINED_RECOVERED_BY_PREFIX}{cid}"
    committed_at = candidate.committed_at
    mined_n = 0
    mined_ok = 0
    baseline_n = 0
    baseline_ok = 0
    for rec in records:
        if not _is_step_attempt(rec):
            continue
        if committed_at is not None and rec.timestamp < committed_at:
            continue
        m = rec.metrics or {}
        recovered_by = m.get("recovered_by") or ""
        if recovered_by == needle:
            mined_n += 1
            if rec.success:
                mined_ok += 1
        elif recovered_by and not recovered_by.startswith(MINED_RECOVERED_BY_PREFIX):
            baseline_n += 1
            if rec.success:
                baseline_ok += 1
    mined_rate = (mined_ok / mined_n) if mined_n else None
    baseline_rate = (baseline_ok / baseline_n) if baseline_n else None
    lift = (
        round(mined_rate - baseline_rate, 4)
        if mined_rate is not None and baseline_rate is not None
        else None
    )
    return {
        "n_after_commit": mined_n,
        "mined_success_rate": round(mined_rate, 4) if mined_rate is not None else None,
        "baseline_success_rate": round(baseline_rate, 4) if baseline_rate is not None else None,
        "lift": lift,
    }


def should_quarantine(
    metrics: Dict[str, Any],
    *,
    min_samples: int = POSTCOMMIT_MIN_SAMPLES,
    neg_lift_threshold: float = QUARANTINE_NEG_LIFT,
) -> bool:
    n = int(metrics.get("n_after_commit") or 0)
    lift = metrics.get("lift")
    if n < min_samples:
        return False
    if lift is None:
        return False
    return lift <= -abs(neg_lift_threshold)


def sweep(
    records: Iterable[Any],
    candidate_registry: RecoveryCandidateRegistry,
    recovery_registry: RecoveryRegistry,
    *,
    min_samples: int = POSTCOMMIT_MIN_SAMPLES,
    neg_lift_threshold: float = QUARANTINE_NEG_LIFT,
) -> List[Tuple[RecoveryCandidate, Dict[str, Any], bool]]:
    """Walk every committed candidate; compute post-commit metrics; quarantine
    in both the candidate registry and the recovery_ladder.json when the
    real-traffic lift dips below threshold.

    Returns the (candidate, metrics, quarantined_now) tuples for caller
    logging. Best-effort: KeyError on stale candidate id is swallowed.
    """
    out: List[Tuple[RecoveryCandidate, Dict[str, Any], bool]] = []
    records_list = list(records)
    for c in candidate_registry.list(status="committed"):
        metrics = measure_candidate(records_list, c)
        flagged = should_quarantine(
            metrics,
            min_samples=min_samples,
            neg_lift_threshold=neg_lift_threshold,
        )
        if flagged:
            try:
                recovery_registry.quarantine(str(c.id))
            except Exception:
                pass
            try:
                candidate_registry.update_status(
                    c.id, "quarantined",
                    shadow_metrics={**(c.shadow_metrics or {}),
                                    "post_commit": metrics},
                )
            except KeyError:
                pass
        out.append((c, metrics, flagged))
    return out
