"""RecoveryPromotionGate — Phase 6 of R6 v1.

Reuses training.effectiveness_tracker.validate_for_promotion to gate
RecoveryCandidates between status="shadow" and status="ready".

A candidate may move pending → shadow on first shadow trial (handled by the
ReplayEngine hook). The gate decides shadow → ready strictly on shadow
evidence: aggregate would_resolve_rate from shadow_results.jsonl must beat
the live-resolver baseline by MIN_LIFT, with at least SHADOW_MIN_SAMPLES
trials.

Exposes:
    promote_candidate(candidate, validator) -> (allow: bool, reason: str)
    refresh_all(registry, validator)        -> list[(candidate, allow, reason)]

NEVER auto-commits. Only flips status to "ready" so the operator can run
`bm recovery candidate approve <id>`.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from browsermind_core.ontology.recovery_candidate import (
    RecoveryCandidate, RecoveryCandidateRegistry,
)
from browsermind_core.runtime.shadow_validator import ShadowValidator


SHADOW_MIN_SAMPLES = 30
MIN_LIFT = 0.10            # candidate must beat baseline by 10 percentage points
TRANSIENT_STATES = ("pending", "shadow")


def _aggregate_with_baseline(
    validator: ShadowValidator,
    candidate_id: str,
) -> Dict[str, Any]:
    """Read shadow_results.jsonl rows for one candidate.

    Compute:
      n_trials                — total rows for this candidate
      would_resolve_rate      — share of rows with would_resolve=True
      live_baseline_rate      — share of rows where live_resolver_succeeded=True
      lift                    — would_resolve_rate - live_baseline_rate
    """
    if not validator.path.exists():
        return {"n_trials": 0, "would_resolve_rate": 0.0,
                "live_baseline_rate": 0.0, "lift": 0.0}
    n = 0
    n_resolve = 0
    n_live_ok = 0
    try:
        import json
        with validator.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("candidate_id") != candidate_id:
                    continue
                n += 1
                if row.get("would_resolve") is True:
                    n_resolve += 1
                if row.get("live_resolver_succeeded") is True:
                    n_live_ok += 1
    except Exception:
        return {"n_trials": 0, "would_resolve_rate": 0.0,
                "live_baseline_rate": 0.0, "lift": 0.0}
    if n == 0:
        return {"n_trials": 0, "would_resolve_rate": 0.0,
                "live_baseline_rate": 0.0, "lift": 0.0}
    wr = n_resolve / n
    bl = n_live_ok / n
    return {
        "n_trials": n,
        "would_resolve_rate": round(wr, 4),
        "live_baseline_rate": round(bl, 4),
        "lift": round(wr - bl, 4),
    }


def evaluate_candidate(
    candidate: RecoveryCandidate,
    *,
    validator: ShadowValidator,
    shadow_min_samples: int = SHADOW_MIN_SAMPLES,
    min_lift: float = MIN_LIFT,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Decide whether a candidate should flip to status='ready'.

    Returns (allow, reason, metrics).
    Only operates on candidates currently in pending|shadow.
    """
    if candidate.status not in TRANSIENT_STATES:
        return False, f"status_not_eligible:{candidate.status}", {}

    metrics = _aggregate_with_baseline(validator, str(candidate.id))
    if metrics["n_trials"] < shadow_min_samples:
        return False, f"below_shadow_min_samples:{metrics['n_trials']}/{shadow_min_samples}", metrics

    if metrics["would_resolve_rate"] <= 0.0:
        return False, "no_resolutions_in_shadow", metrics

    if metrics["lift"] < min_lift:
        return False, f"lift_below_threshold:{metrics['lift']}", metrics

    return True, f"lift_ok:{metrics['lift']}", metrics


def refresh_registry(
    registry: RecoveryCandidateRegistry,
    *,
    validator: Optional[ShadowValidator] = None,
    shadow_min_samples: int = SHADOW_MIN_SAMPLES,
    min_lift: float = MIN_LIFT,
) -> List[Tuple[RecoveryCandidate, bool, str]]:
    """Walk the candidate registry and promote any pending|shadow rows that
    pass evaluate_candidate(). Side-effects:
      - flips status to "shadow" once n_trials >= 1 (entered observation)
      - flips status to "ready" when the lift gate passes
    Always stores the latest metrics on candidate.shadow_metrics.

    Returns the (candidate, allow, reason) tuples for caller logging."""
    v = validator or ShadowValidator()
    out: List[Tuple[RecoveryCandidate, bool, str]] = []
    for c in registry.list():
        if c.status not in TRANSIENT_STATES:
            continue
        allow, reason, metrics = evaluate_candidate(
            c, validator=v,
            shadow_min_samples=shadow_min_samples,
            min_lift=min_lift,
        )
        new_status = c.status
        if allow:
            new_status = "ready"
        elif c.status == "pending" and metrics.get("n_trials", 0) >= 1:
            new_status = "shadow"
        if new_status != c.status or metrics:
            try:
                registry.update_status(
                    c.id, new_status,
                    shadow_metrics=metrics,
                )
            except KeyError:
                pass
        out.append((c, allow, reason))
    return out
