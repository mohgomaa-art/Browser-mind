from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from browsermind_core.experiments.baseline_lock import lock_phase1_baseline
from browsermind_core.experiments.descriptor_entropy import descriptor_entropy
from browsermind_core.experiments.ground_truth import GroundTruthAnnotation, GroundTruthDataset
from browsermind_core.experiments.reliability_metrics import (
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    RESOLVED_UNJUDGED,
    evaluate_bc_gate,
    compute_replay_reliability_metrics,
)
from browsermind_core.experiments.reliability_telemetry import telemetry_event


def _annotations(n: int = 100):
    return [
        GroundTruthAnnotation(
            annotation_id=f"gt-{i:03d}",
            site="demoqa",
            template_name="form",
            step_seq=i + 1,
            true_role="textbox",
            true_name=f"Field {i}",
            true_container="Main form",
            true_target=f"#field-{i}",
        )
        for i in range(n)
    ]


def test_ground_truth_dataset_requires_exactly_100_annotations():
    dataset = GroundTruthDataset(dataset_id="gt-v1", annotations=_annotations())
    assert len(dataset.annotations) == 100
    assert dataset.find(site="demoqa", template_name="form", step_seq=7).true_target == "#field-6"

    with pytest.raises(ValueError, match="exactly 100"):
        GroundTruthDataset(dataset_id="too-small", annotations=_annotations(99))


def test_ground_truth_annotation_judges_correct_target():
    ann = _annotations(1)[0]
    assert ann.matches_resolution(
        {
            "role": "textbox",
            "name": "Field 0",
            "container": "Main form",
            "target": "#field-0",
        }
    )
    assert not ann.matches_resolution(
        {
            "role": "textbox",
            "name": "Field 0",
            "container": "Main form",
            "target": "#other-field",
        }
    )


def test_reliability_metrics_include_fpr_and_accuracy():
    metrics = compute_replay_reliability_metrics(
        [
            {"outcome": RESOLVED_CORRECT},
            {"outcome": RESOLVED_CORRECT},
            {"outcome": RESOLVED_INCORRECT},
            {"outcome": RESOLVED_UNJUDGED},
            {"outcome": "TARGET_CHANGED"},
            {"outcome": "SKIPPED"},
        ],
        task_completed=True,
    )
    assert metrics["attempted_steps"] == 5
    assert metrics["resolution_rate"] == 0.8
    assert metrics["false_positive_resolution_rate"] == 0.3333
    assert metrics["resolution_accuracy"] == 0.6667
    assert metrics["task_completion_rate"] == 1.0


def test_corrected_bc_gate_requires_all_three_metrics():
    passing = {
        "resolution_rate": 0.81,
        "false_positive_resolution_rate": 0.049,
        "task_completion_rate": 0.70,
    }
    assert evaluate_bc_gate(passing)["passed"] is True

    failing = dict(passing, false_positive_resolution_rate=0.05)
    gate = evaluate_bc_gate(failing)
    assert gate["passed"] is False
    assert gate["checks"]["false_positive_resolution_rate"] is False


def test_descriptor_entropy_scores_descriptor():
    scored = descriptor_entropy(
        {
            "role": "textbox",
            "name": "Location (City)",
            "container_label": "Apply for this job",
            "true_target": "#candidate-location",
        }
    )
    assert scored["length"] > 0
    assert scored["entropy_bits_per_char"] > 0
    assert scored["schema"] == "browsermind.descriptor_entropy.v1"


def test_reliability_telemetry_is_mutation_ledger_compatible():
    entity_id = uuid4()
    payload = telemetry_event(
        component="metrics",
        event_type="computed",
        phase="phase1_measurement",
        entity_id=entity_id,
        data={"resolution_rate": 0.8},
    ).to_mutation_payload()
    assert payload["entity_type"] == "ReplayReliabilityTelemetry"
    assert payload["entity_id"] == entity_id
    assert payload["new_value"]["schema"] == "browsermind.replay_reliability.telemetry.v1"
    assert payload["actor"] == "metrics"


def test_baseline_lock_preserves_existing_numbers(tmp_path: Path):
    identity = tmp_path / "sprint_results.json"
    identity.write_text(
        json.dumps(
            {
                "Baseline": {
                    "total_steps": 49,
                    "resolved_steps": 10,
                    "resolution_rate": 10 / 49,
                    "critical_path_success": False,
                    "task_success_probability": 0.0,
                }
            }
        ),
        encoding="utf-8",
    )
    dossier = tmp_path / "target_changed.json"
    dossier.write_text(
        json.dumps(
            {
                "total_cases": 10,
                "root_cause_distribution": {
                    "RECORDER_MISMATCH": 3,
                    "ROLE_DRIFT": 3,
                    "NAVIGATION_STATE_CHANGE": 4,
                },
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "phase1_baseline_locked.json"
    locked = lock_phase1_baseline(
        identity_sprint_path=identity,
        target_changed_dossier_path=dossier,
        output_path=out,
    )
    assert out.exists()
    assert locked["measurement_before_fixes"] is True
    assert locked["asm_greenhouse_baseline"]["resolution_rate"] == 10 / 49
    assert locked["phase_order"] == ["P8A", "P8B", "P8D", "P8E", "P8C"]
