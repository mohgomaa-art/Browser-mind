"""Replay reliability metrics for measurement-before-fix experiments."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, Optional

from browsermind_core.experiments.reliability_telemetry import telemetry_event


RESOLVED_CORRECT = "RESOLVED_CORRECT"
RESOLVED_INCORRECT = "RESOLVED_INCORRECT"
RESOLVED_UNJUDGED = "RESOLVED_UNJUDGED"
LEGACY_RESOLVED = "RESOLVED"
TRANSITION_SUCCESS = "TRANSITION_SUCCESS"
SKIPPED = "SKIPPED"
UNKNOWN = "UNKNOWN"

RESOLVED_OUTCOMES = {
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    RESOLVED_UNJUDGED,
    LEGACY_RESOLVED,
    TRANSITION_SUCCESS,
}

JUDGED_RESOLVED_OUTCOMES = {RESOLVED_CORRECT, RESOLVED_INCORRECT}


def compute_replay_reliability_metrics(
    step_outcomes: Iterable[Dict[str, Any]],
    *,
    task_completed: Optional[bool] = None,
) -> Dict[str, Any]:
    rows = list(step_outcomes)
    attempted = [row for row in rows if row.get("outcome") != SKIPPED]
    counts = Counter(str(row.get("outcome") or "") for row in rows)

    resolved_total = sum(counts[name] for name in RESOLVED_OUTCOMES)
    judged_total = sum(counts[name] for name in JUDGED_RESOLVED_OUTCOMES)
    correct = counts[RESOLVED_CORRECT]
    incorrect = counts[RESOLVED_INCORRECT]
    unjudged = counts[RESOLVED_UNJUDGED] + counts[LEGACY_RESOLVED] + counts[TRANSITION_SUCCESS]

    failed = len(attempted) - resolved_total
    unknown_failures = sum(1 for row in attempted if row.get("outcome") == UNKNOWN)

    fpr = None if judged_total == 0 else round(incorrect / judged_total, 4)
    accuracy = None if judged_total == 0 else round(correct / judged_total, 4)
    resolution_rate = 0.0 if not attempted else round(resolved_total / len(attempted), 4)

    return {
        "schema": "browsermind.replay_reliability.metrics.v1",
        "attempted_steps": len(attempted),
        "skipped_steps": counts[SKIPPED],
        "resolved_steps": resolved_total,
        "resolved_correct_steps": correct,
        "resolved_incorrect_steps": incorrect,
        "resolved_unjudged_steps": unjudged,
        "failed_steps": failed,
        "resolution_rate": resolution_rate,
        "false_positive_resolution_rate": fpr,
        "resolution_accuracy": accuracy,
        "attribution_completeness": None if failed == 0 else round(1 - (unknown_failures / failed), 4),
        "unknown_failure_steps": unknown_failures,
        "task_completed": task_completed,
        "task_completion_rate": None if task_completed is None else (1.0 if task_completed else 0.0),
        "outcome_counts": dict(counts),
        "gate_ready": judged_total == resolved_total and unknown_failures == 0,
    }


def evaluate_bc_gate(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Corrected BC gate: RR>=80%, FPR<5%, task completion>=70%."""
    rr = metrics.get("resolution_rate")
    fpr = metrics.get("false_positive_resolution_rate")
    task = metrics.get("task_completion_rate")

    checks = {
        "resolution_rate": rr is not None and rr >= 0.80,
        "false_positive_resolution_rate": fpr is not None and fpr < 0.05,
        "task_completion_rate": task is not None and task >= 0.70,
    }
    return {
        "schema": "browsermind.bc_gate.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": {
            "resolution_rate_min": 0.80,
            "false_positive_resolution_rate_max_exclusive": 0.05,
            "task_completion_rate_min": 0.70,
        },
    }


def metrics_telemetry(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return telemetry_event(
        component="reliability_metrics",
        event_type="metrics_computed",
        phase="phase1_measurement",
        data=metrics,
    ).to_mutation_payload()
