"""Bridge: ReplayReport.failure_attribution → ground-truth-judged step_outcomes
   → reliability metrics with FPR + accuracy.

The ReplayEngine already produces FailureAttribution rows (one per step). The
existing reliability_metrics module already consumes step_outcomes labeled
RESOLVED_CORRECT / RESOLVED_INCORRECT / RESOLVED_UNJUDGED. The gap was a function
that reads the engine's output and the human ground-truth dataset, judges each
resolved step, and emits the labeled rows.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from browsermind_core.experiments.ground_truth import (
    GroundTruthAnnotation,
    GroundTruthDataset,
)
from browsermind_core.experiments.reliability_metrics import (
    LEGACY_RESOLVED,
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    RESOLVED_UNJUDGED,
    SKIPPED,
    TRANSITION_SUCCESS,
    UNKNOWN,
)
from browsermind_core.ontology.p1_schemas import FailureAttribution, ReplayReport


def _attribution_to_resolution_dict(attr: FailureAttribution) -> Dict[str, Any]:
    """Shape a FailureAttribution row into the dict GroundTruthAnnotation.matches_resolution understands."""
    target_integrity = attr.target_integrity or {}
    return {
        "role": attr.role,
        "name": attr.name,
        "container": target_integrity.get("container_label") or target_integrity.get("nearest_container_label"),
        "target": target_integrity.get("resolved_target") or target_integrity.get("target_selector"),
    }


def judge_step_outcomes(
    report: ReplayReport,
    dataset: Optional[GroundTruthDataset],
    *,
    site: str,
    template_name: Optional[str] = None,
    workflow_id: Optional[UUID] = None,
) -> List[Dict[str, Any]]:
    """Project FailureAttribution rows into step_outcomes consumable by compute_replay_reliability_metrics.

    Each row is one of:
      - SKIPPED       — execution never attempted (e.g. predecessor failure)
      - RESOLVED_CORRECT  — the resolver chose the human-labeled target
      - RESOLVED_INCORRECT — the resolver chose a different target than labeled
      - RESOLVED_UNJUDGED — resolved but no annotation exists for this step
      - UNKNOWN       — failed but no failure_reason captured (legacy)
      - the original failure_reason category (string-passed-through) for failed steps
    """
    rows: List[Dict[str, Any]] = []
    for attr in report.failure_attribution:
        actual = attr.actual_outcome
        if actual == "SUCCESS" or actual == "TRANSITION_SUCCESS":
            outcome = LEGACY_RESOLVED if actual == "SUCCESS" else TRANSITION_SUCCESS
            annotation = None
            if dataset is not None:
                annotation = dataset.find(
                    site=site,
                    step_seq=attr.step_seq,
                    workflow_id=workflow_id,
                    template_name=template_name,
                )
            if annotation is not None:
                outcome = (
                    RESOLVED_CORRECT
                    if annotation.matches_resolution(_attribution_to_resolution_dict(attr))
                    else RESOLVED_INCORRECT
                )
            elif dataset is not None:
                # Dataset present but no annotation for this step → unjudged
                outcome = RESOLVED_UNJUDGED
            rows.append({
                "step_seq": attr.step_seq,
                "outcome": outcome,
                "role": attr.role,
                "name": attr.name,
                "annotation_id": annotation.annotation_id if annotation is not None else None,
            })
        elif actual == "FAILED":
            rows.append({
                "step_seq": attr.step_seq,
                "outcome": UNKNOWN if not attr.failure_reason else attr.failure_reason,
                "role": attr.role,
                "name": attr.name,
            })
        else:  # AMBIGUOUS_IDENTITY, ASK — neither resolved nor cleanly failed; do not credit as resolved
            rows.append({
                "step_seq": attr.step_seq,
                "outcome": SKIPPED,
                "role": attr.role,
                "name": attr.name,
                "actual_outcome": actual,
            })
    return rows


def annotation_summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Quick counts for diagnostic logging."""
    counter = {
        RESOLVED_CORRECT: 0,
        RESOLVED_INCORRECT: 0,
        RESOLVED_UNJUDGED: 0,
        LEGACY_RESOLVED: 0,
        TRANSITION_SUCCESS: 0,
        SKIPPED: 0,
        UNKNOWN: 0,
        "OTHER_FAILURE": 0,
    }
    for row in rows:
        outcome = row.get("outcome", "")
        if outcome in counter:
            counter[outcome] += 1
        else:
            counter["OTHER_FAILURE"] += 1
    return counter
