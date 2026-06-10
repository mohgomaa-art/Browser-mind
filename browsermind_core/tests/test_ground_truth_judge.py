"""P4: Ground Truth + Resolution Accuracy.

Tests the bridge between FailureAttribution rows and the existing
reliability_metrics function, plus the second OutcomeRecord that
ReplayEngine writes per run when a ground_truth_dataset is supplied.
"""
from __future__ import annotations

import tempfile
from unittest.mock import MagicMock
from uuid import uuid4

from browsermind_core.console.session import KernelSession
from browsermind_core.experiments.ground_truth import (
    GroundTruthAnnotation,
    GroundTruthDataset,
)
from browsermind_core.experiments.ground_truth_judge import (
    annotation_summary,
    judge_step_outcomes,
)
from browsermind_core.experiments.reliability_metrics import (
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    RESOLVED_UNJUDGED,
    SKIPPED,
    UNKNOWN,
    compute_replay_reliability_metrics,
)
from browsermind_core.ontology.p1_schemas import (
    FailureAttribution,
    ReplayReport,
    WorkflowInstance,
    WorkflowTemplate,
)
from browsermind_core.runtime.replay_engine import ReplayEngine


def _make_template():
    return WorkflowTemplate(
        name="login",
        description="audit fixture",
        family_key="testfam",
        steps=[],
        metadata={"compiled_from": "demo-1"},
    )


def _make_instance(template_id, persona_id):
    return WorkflowInstance(
        persona_id=persona_id,
        template_id=template_id,
        bound_resources={},
        bound_identities={},
    )


def _make_attribution(seq, role, name, *, actual="SUCCESS", target_selector=None,
                      container_label=None, failure_reason=None):
    target_integrity = {}
    if target_selector is not None:
        target_integrity["target_selector"] = target_selector
    if container_label is not None:
        target_integrity["container_label"] = container_label
    return FailureAttribution(
        step_seq=seq,
        action_type="click",
        role=role,
        name=name,
        predicted_tier="HIGH",
        predicted_score=0.9,
        actual_outcome=actual,
        failure_reason=failure_reason,
        target_integrity=target_integrity or None,
    )


def _make_dataset(annotations, required_size=None):
    if required_size is None:
        required_size = len(annotations)
    return GroundTruthDataset(
        dataset_id="t-1",
        required_size=required_size,
        annotations=annotations,
    )


# --- judge_step_outcomes -----------------------------------------------------


def test_judge_correct_when_annotation_matches():
    ann = GroundTruthAnnotation(
        annotation_id="a1",
        site="saucedemo",
        step_seq=1,
        true_role="button",
        true_name="Login",
        true_target="#login-button",
    )
    dataset = _make_dataset([ann])
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=1,
        resolved_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", target_selector="#login-button"),
        ],
    )
    rows = judge_step_outcomes(report, dataset, site="saucedemo")
    assert len(rows) == 1
    assert rows[0]["outcome"] == RESOLVED_CORRECT
    assert rows[0]["annotation_id"] == "a1"


def test_judge_incorrect_when_annotation_mismatches():
    ann = GroundTruthAnnotation(
        annotation_id="a1",
        site="saucedemo",
        step_seq=1,
        true_role="button",
        true_name="Login",
        true_target="#login-button",
    )
    dataset = _make_dataset([ann])
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=1,
        resolved_steps=1,
        failure_attribution=[
            # Wrong target_selector: resolver picked the wrong element
            _make_attribution(1, "button", "Login", target_selector="#cancel-button"),
        ],
    )
    rows = judge_step_outcomes(report, dataset, site="saucedemo")
    assert rows[0]["outcome"] == RESOLVED_INCORRECT


def test_judge_unjudged_when_no_annotation_for_step():
    ann = GroundTruthAnnotation(
        annotation_id="a1",
        site="saucedemo",
        step_seq=999,
        true_role="button",
        true_name="Other",
        true_target="#other",
    )
    dataset = _make_dataset([ann])
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=1,
        resolved_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", target_selector="#login-button"),
        ],
    )
    rows = judge_step_outcomes(report, dataset, site="saucedemo")
    assert rows[0]["outcome"] == RESOLVED_UNJUDGED


def test_judge_legacy_resolved_when_no_dataset_supplied():
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=1,
        resolved_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", target_selector="#login-button"),
        ],
    )
    rows = judge_step_outcomes(report, None, site="saucedemo")
    assert rows[0]["outcome"] == "RESOLVED"


def test_judge_failed_step_passes_through_failure_reason():
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="FAILED",
        total_steps=1,
        failed_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", actual="FAILED",
                              failure_reason="TARGET_NOT_FOUND"),
        ],
    )
    rows = judge_step_outcomes(report, None, site="saucedemo")
    assert rows[0]["outcome"] == "TARGET_NOT_FOUND"


def test_judge_failed_step_without_reason_is_unknown():
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="FAILED",
        total_steps=1,
        failed_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", actual="FAILED"),
        ],
    )
    rows = judge_step_outcomes(report, None, site="saucedemo")
    assert rows[0]["outcome"] == UNKNOWN


def test_judge_ambiguous_step_marked_skipped():
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="FAILED",
        total_steps=1,
        failed_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Submit", actual="AMBIGUOUS_IDENTITY"),
        ],
    )
    rows = judge_step_outcomes(report, None, site="saucedemo")
    assert rows[0]["outcome"] == SKIPPED


# --- end-to-end metrics -------------------------------------------------------


def test_metrics_match_expected_fpr_and_accuracy():
    annotations = [
        GroundTruthAnnotation(annotation_id=f"a{i}", site="saucedemo", step_seq=i,
                              true_role="button", true_name=f"B{i}", true_target=f"#b{i}")
        for i in range(1, 5)
    ]
    dataset = _make_dataset(annotations)
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=4,
        resolved_steps=4,
        failure_attribution=[
            _make_attribution(1, "button", "B1", target_selector="#b1"),  # correct
            _make_attribution(2, "button", "B2", target_selector="#b2"),  # correct
            _make_attribution(3, "button", "B3", target_selector="#wrong"),  # incorrect
            _make_attribution(4, "button", "B4", target_selector="#b4"),  # correct
        ],
    )
    rows = judge_step_outcomes(report, dataset, site="saucedemo")
    metrics = compute_replay_reliability_metrics(rows)
    counts = annotation_summary(rows)

    assert counts[RESOLVED_CORRECT] == 3
    assert counts[RESOLVED_INCORRECT] == 1
    assert metrics["resolution_accuracy"] == 0.75
    assert metrics["false_positive_resolution_rate"] == 0.25
    assert metrics["resolution_rate"] == 1.0
    assert metrics["gate_ready"] is True


# --- ReplayEngine integration -------------------------------------------------


def test_engine_writes_accuracy_record_when_dataset_supplied():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        ann = GroundTruthAnnotation(
            annotation_id="a1",
            site="testinst",
            step_seq=1,
            true_role="button",
            true_name="Login",
            true_target="#login-button",
        )
        dataset = _make_dataset([ann])

        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="testinst",
            ground_truth_dataset=dataset,
        )
        report = ReplayReport(
            workflow_id=instance.id,
            template_id=template.id,
            status="SUCCESS",
            total_steps=1,
            resolved_steps=1,
            resolution_rate=1.0,
            duration_seconds=0.5,
            failure_attribution=[
                _make_attribution(1, "button", "Login", target_selector="#login-button"),
            ],
        )

        engine._record_replay_accuracy(report, template, instance, env_key="testinst")
        engine._record_replay_outcome(report, template, instance)

        records = ks.outcome_ledger.records
        assert len(records) == 2
        outcome_types = sorted(r.outcome_type for r in records)
        assert outcome_types == ["replay_accuracy", "replay_run"]

        accuracy_rec = next(r for r in records if r.outcome_type == "replay_accuracy")
        assert accuracy_rec.success is True
        assert accuracy_rec.metrics["resolution_accuracy"] == 1.0
        assert accuracy_rec.metrics["false_positive_resolution_rate"] == 0.0
        assert accuracy_rec.metrics["ground_truth_counts"][RESOLVED_CORRECT] == 1


def test_engine_no_op_when_no_dataset():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="testinst",
            ground_truth_dataset=None,
        )
        report = ReplayReport(
            workflow_id=instance.id,
            template_id=template.id,
            status="SUCCESS",
            total_steps=1,
            resolved_steps=1,
            resolution_rate=1.0,
            duration_seconds=0.5,
        )
        engine._record_replay_accuracy(report, template, instance, env_key="testinst")
        # Without a dataset, no accuracy record is written
        accuracy_records = [r for r in ks.outcome_ledger.records if r.outcome_type == "replay_accuracy"]
        assert accuracy_records == []


def test_engine_accuracy_failure_is_swallowed():
    bad_ledger = MagicMock()
    bad_ledger.record.side_effect = RuntimeError("disk full")
    persona_id = uuid4()

    ann = GroundTruthAnnotation(
        annotation_id="a1",
        site="testinst",
        step_seq=1,
        true_role="button",
        true_name="Login",
        true_target="#login-button",
    )
    dataset = _make_dataset([ann])

    engine = ReplayEngine(
        MagicMock(),
        outcome_ledger=bad_ledger,
        persona_id=persona_id,
        environment_family="testfam",
        environment_instance="testinst",
        ground_truth_dataset=dataset,
    )
    template = _make_template()
    instance = _make_instance(template.id, persona_id)
    report = ReplayReport(
        workflow_id=instance.id,
        template_id=template.id,
        status="SUCCESS",
        total_steps=1,
        resolved_steps=1,
        failure_attribution=[
            _make_attribution(1, "button", "Login", target_selector="#login-button"),
        ],
    )
    # Must not propagate
    engine._record_replay_accuracy(report, template, instance, env_key="testinst")


def test_engine_init_accepts_ground_truth_dataset():
    import inspect
    sig = inspect.signature(ReplayEngine.__init__)
    assert "ground_truth_dataset" in sig.parameters
    assert sig.parameters["ground_truth_dataset"].default is None


def test_accuracy_record_links_to_execution_id():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        task = ks.task_manager.create_task(persona_id=persona_id, goal="t")
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        ann = GroundTruthAnnotation(
            annotation_id="a1",
            site="testinst",
            step_seq=1,
            true_role="button",
            true_name="Login",
            true_target="#login-button",
        )
        dataset = _make_dataset([ann])

        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="testinst",
            execution_engine=ks.execution_engine,
            task_id=task.id,
            ground_truth_dataset=dataset,
        )
        engine._start_execution_if_wired(template, instance)
        active_id = engine._active_execution_id
        report = ReplayReport(
            workflow_id=instance.id,
            template_id=template.id,
            status="SUCCESS",
            total_steps=1,
            resolved_steps=1,
            failure_attribution=[
                _make_attribution(1, "button", "Login", target_selector="#login-button"),
            ],
        )
        engine._record_replay_accuracy(report, template, instance, env_key="testinst")
        engine._record_replay_outcome(report, template, instance)
        engine._close_execution_if_wired(report)

        accuracy_rec = next(r for r in ks.outcome_ledger.records if r.outcome_type == "replay_accuracy")
        assert accuracy_rec.execution_id == active_id
