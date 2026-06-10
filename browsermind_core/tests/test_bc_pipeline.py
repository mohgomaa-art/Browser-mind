"""Phase 3/4/5: end-to-end test of the BC-readiness pipeline.

Drives the helper directly:
  ReplayEngine._record_step_outcomes
    → KernelSession.outcome_ledger (persisted via OutcomeRepository)
    → outcome_ledger_adapter.build_from_store    (Phase 3)
    → lesson_aggregator.build_from_store         (Phase 4)
    → training_readiness_report.build_from_store (Phase 5)

Asserts the contract every downstream piece relies on, including the dataset
manifest schema and the readiness verdict thresholds.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ontology.p1_schemas import (
    FailureAttribution,
    ReplayReport,
    WorkflowInstance,
    WorkflowTemplate,
)
from browsermind_core.runtime.replay_engine import ReplayEngine

from training import outcome_ledger_adapter
from training import lesson_aggregator
from training import training_readiness_report


def _seed_step_records(store_dir: str, *, success_count: int, failure_count: int):
    ks = KernelSession(store_dir=store_dir)
    persona_id = uuid4()
    template = WorkflowTemplate(
        name="t",
        description="seed",
        family_key="testfam",
        steps=[{"action": "click"} for _ in range(success_count + failure_count)],
        metadata={"compiled_from": "demo"},
    )
    instance = WorkflowInstance(
        persona_id=persona_id,
        template_id=template.id,
        bound_resources={},
        bound_identities={},
    )

    attrs = []
    for i in range(success_count):
        attrs.append(FailureAttribution(
            step_seq=i + 1,
            action_type="click",
            role="button",
            name="Submit",
            predicted_tier="HIGH",
            predicted_score=0.9,
            actual_outcome="SUCCESS",
            resolved_by="primary_semantic",
            resolution_success=True,
            execution_success=True,
            effect_verified=True,
            effect_type="URL_CHANGED",
        ))
    for i in range(failure_count):
        attrs.append(FailureAttribution(
            step_seq=success_count + i + 1,
            action_type="click",
            role="button",
            name="Submit",
            predicted_tier="HIGH",
            predicted_score=0.9,
            actual_outcome="FAILED",
            failure_reason="TargetNotFound: role='button', name='Submit'",
            resolution_success=False,
            execution_success=False,
            effect_verified=None,
            failure_layer="resolution",
        ))

    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS" if failure_count == 0 else "FAILED",
        total_steps=len(attrs),
        resolved_steps=success_count,
        failed_steps=failure_count,
        ambiguous_steps=0,
        resolution_rate=success_count / max(1, len(attrs)),
        ambiguity_rate=0.0,
        recovery_rate=100.0,
        duration_seconds=1.0,
        failure_attribution=attrs,
    )

    engine = ReplayEngine(
        MagicMock(),
        outcome_ledger=ks.outcome_ledger,
        persona_id=persona_id,
        environment_family="testfam",
        environment_instance="saucedemo",
    )
    engine._record_replay_outcome(report, template, instance)
    engine._record_step_outcomes(report, template, instance, "saucedemo")


# --- Phase 3 -----------------------------------------------------------------


def test_adapter_emits_dataset_and_manifest_with_schema_v1():
    with tempfile.TemporaryDirectory() as store:
        _seed_step_records(store, success_count=3, failure_count=2)
        with tempfile.TemporaryDirectory() as out:
            result = outcome_ledger_adapter.build_from_store(store, out)
            assert result["rows_written"] == 5

            manifest = json.loads(Path(out, "dataset_manifest.json").read_text(encoding="utf-8"))
            assert manifest["schema_version"] == "browsermind.bc_dataset.v1"
            assert manifest["sample_count"] == 5
            assert manifest["success_count"] == 3
            assert manifest["failure_count"] == 2
            assert manifest["label_distribution"] == {"SUCCESS": 3, "FAILED": 2}

            rows = [json.loads(l) for l in Path(out, "dataset.jsonl").read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 5
            keys = {"row_id", "step_id", "workflow_id", "persona_id", "action",
                    "success", "label", "failure_class", "root_cause",
                    "effect_verified", "weight"}
            assert keys.issubset(rows[0].keys())
            failures = [r for r in rows if not r["success"]]
            assert all(r["failure_class"] == "TARGET_CHANGED" for r in failures)
            assert all(r["weight"] == 0.1 for r in failures)
            successes = [r for r in rows if r["success"]]
            assert all(r["weight"] == 1.0 for r in successes)


def test_adapter_handles_empty_ledger():
    with tempfile.TemporaryDirectory() as store:
        KernelSession(store_dir=store)
        with tempfile.TemporaryDirectory() as out:
            result = outcome_ledger_adapter.build_from_store(store, out)
            assert result["rows_written"] == 0
            assert json.loads(Path(out, "dataset_manifest.json").read_text(encoding="utf-8"))["sample_count"] == 0


# --- Phase 4 -----------------------------------------------------------------


def test_lesson_aggregator_extracts_pattern_buckets():
    with tempfile.TemporaryDirectory() as store:
        _seed_step_records(store, success_count=3, failure_count=2)
        with tempfile.TemporaryDirectory() as out:
            result = lesson_aggregator.build_from_store(store, out)
            assert result["lessons_written"] >= 1

            lessons = [json.loads(l) for l in Path(out, "lessons.jsonl").read_text(encoding="utf-8").splitlines()]
            kinds = {l["kind"] for l in lessons}
            assert "failure_class" in kinds
            assert "resolution_strategy" in kinds
            assert "predicted_vs_actual" in kinds

            failure_lesson = next(l for l in lessons if l["kind"] == "failure_class")
            assert failure_lesson["key"] == {"failure_class": "TARGET_CHANGED"}
            assert failure_lesson["observations"] == 2
            assert failure_lesson["outcomes"] == {"success": 0, "failure": 2}

            manifest = json.loads(Path(out, "lesson_manifest.json").read_text(encoding="utf-8"))
            assert manifest["schema_version"] == "browsermind.lesson.v1"
            assert manifest["lesson_count"] == len(lessons)


def test_lesson_aggregator_no_steps_yields_empty_manifest():
    with tempfile.TemporaryDirectory() as store:
        KernelSession(store_dir=store)
        with tempfile.TemporaryDirectory() as out:
            result = lesson_aggregator.build_from_store(store, out)
            assert result["lessons_written"] == 0


# --- Phase 5 -----------------------------------------------------------------


def test_readiness_report_verdict_not_ready_on_thin_data():
    with tempfile.TemporaryDirectory() as store:
        _seed_step_records(store, success_count=3, failure_count=2)
        with tempfile.TemporaryDirectory() as out:
            outcome_ledger_adapter.build_from_store(store, str(Path(out, "ds")))
            lesson_aggregator.build_from_store(store, str(Path(out, "ls")))
            result = training_readiness_report.build_from_store(
                store,
                dataset_dir=str(Path(out, "ds")),
                lessons_dir=str(Path(out, "ls")),
                ground_truth_dir="ground_truth",
                output_path=str(Path(out, "report.json")),
            )

            report = result["report"]
            assert report["schema_version"] == "browsermind.training_readiness.v1"
            assert report["counts"]["step_records"] == 5
            assert report["metrics"]["dataset_yield"] == 1.0
            assert report["metrics"]["failure_coverage"] == 1.0
            # 5 step records is below the LIMITED_LEARNING threshold of 50.
            assert report["verdict"]["verdict"] == "NOT_READY"


def test_readiness_report_promotes_to_limited_learning_at_scale():
    with tempfile.TemporaryDirectory() as store:
        _seed_step_records(store, success_count=40, failure_count=15)
        with tempfile.TemporaryDirectory() as out:
            outcome_ledger_adapter.build_from_store(store, str(Path(out, "ds")))
            lesson_aggregator.build_from_store(store, str(Path(out, "ls")))
            result = training_readiness_report.build_from_store(
                store,
                dataset_dir=str(Path(out, "ds")),
                lessons_dir=str(Path(out, "ls")),
                ground_truth_dir="ground_truth",
                output_path=str(Path(out, "report.json")),
            )
            v = result["report"]["verdict"]["verdict"]
            assert v in ("READY_FOR_LIMITED_LEARNING", "READY_FOR_BC")


def test_readiness_report_persists_to_disk():
    with tempfile.TemporaryDirectory() as store:
        _seed_step_records(store, success_count=1, failure_count=0)
        with tempfile.TemporaryDirectory() as out:
            out_path = Path(out, "training_readiness_report.json")
            training_readiness_report.build_from_store(
                store,
                dataset_dir=str(Path(out, "ds")),
                lessons_dir=str(Path(out, "ls")),
                ground_truth_dir="ground_truth",
                output_path=str(out_path),
            )
            # Adapter and lesson dirs were not created — yields fall back to None.
            assert out_path.exists()
            data = json.loads(out_path.read_text(encoding="utf-8"))
            assert data["counts"]["step_records"] == 1
