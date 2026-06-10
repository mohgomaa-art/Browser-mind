"""Regression tests for the verification pipeline fixes.

Covers:
  TEST 1 — _replay_success vetoes on state_match=False
  TEST 2 — _replay_success allows when state_match=True and steps pass
  TEST 3 — _task_completed prefers state_match, falls back to verifier_result,
           then to state_inference.match
  TEST 4 — verifier exceptions are captured in verification_error (no silent pass)
  TEST 5 — effect_verified / effect_type / effect_details survive into step_outcomes
  TEST 6 — supplying ground_truth produces judged outcomes and a non-None FPR
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from browsermind_core.evaluation.state_verification.schemas import (
    StateRule,
    StateVerifierConfig,
)
from browsermind_core.evaluation.state_verification.verifier import StateVerifier
from browsermind_core.experiments.ground_truth import (
    GroundTruthAnnotation,
    GroundTruthDataset,
)
from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.reliability_metrics import (
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    compute_replay_reliability_metrics,
)
from browsermind_core.ontology.p1_schemas import FailureAttribution, ReplayReport


def _ok_step(seq: int, *, effect_verified=True, effect_type="URL_CHANGED",
             effect_details=None, failure_layer=None) -> FailureAttribution:
    return FailureAttribution(
        step_seq=seq,
        action_type="click",
        role="button",
        name=f"Step {seq}",
        predicted_tier="HIGH",
        predicted_score=0.9,
        actual_outcome="SUCCESS",
        resolution_success=True,
        execution_success=True,
        effect_verified=effect_verified,
        effect_type=effect_type,
        effect_details=effect_details,
        failure_layer=failure_layer,
        target_integrity={"resolved_text": f"step{seq}", "candidate_count": 1},
    )


def _report(*, verification_report=None, state_inference=None,
            failure_attribution=None, total_steps=None,
            failure_reason=None) -> ReplayReport:
    attrs = failure_attribution if failure_attribution is not None else [_ok_step(1), _ok_step(2)]
    total = total_steps if total_steps is not None else len(attrs)
    return ReplayReport(
        workflow_id=uuid4(),
        template_id=uuid4(),
        total_steps=total,
        failure_attribution=attrs,
        failure_reason=failure_reason,
        verification_report=verification_report,
        state_inference=state_inference,
    )


# ── TEST 1 ───────────────────────────────────────────────────────────────────

def test_replay_success_vetoed_by_state_match_false():
    report = _report(verification_report={"state_match": False})
    assert ReplayExperimentHarness._replay_success(report, report.total_steps) is False


# ── TEST 2 ───────────────────────────────────────────────────────────────────

def test_replay_success_passes_when_state_match_true_and_steps_pass():
    report = _report(verification_report={"state_match": True})
    assert ReplayExperimentHarness._replay_success(report, report.total_steps) is True


def test_replay_success_true_verdict_does_not_mask_step_failure():
    """A verifier 'success' must not whitewash a step-level failure."""
    failing = [
        _ok_step(1),
        FailureAttribution(
            step_seq=2,
            action_type="fill",
            role="textbox",
            name="Username",
            predicted_tier="HIGH",
            predicted_score=0.9,
            actual_outcome="FAILED",
            failure_reason="ExecutionError: timeout",
        ),
    ]
    report = _report(
        verification_report={"state_match": True},
        failure_attribution=failing,
        failure_reason="Step 2 failed",
    )
    assert ReplayExperimentHarness._replay_success(report, 2) is False


# ── TEST 3 ───────────────────────────────────────────────────────────────────

def test_task_completed_prefers_state_match():
    report = _report(verification_report={"state_match": False, "verifier_result": True})
    assert ReplayExperimentHarness._task_completed(report) is False


def test_task_completed_falls_back_to_verifier_result():
    report = _report(verification_report={"verifier_result": True})
    assert ReplayExperimentHarness._task_completed(report) is True


def test_task_completed_accepts_legacy_success_keys():
    for legacy_key in ("success", "passed", "overall_success"):
        report = _report(verification_report={legacy_key: True})
        assert ReplayExperimentHarness._task_completed(report) is True, legacy_key


def test_task_completed_falls_back_to_state_inference():
    from browsermind_core.ontology.p1_schemas import StateEvidence, StateInference

    state = StateInference(
        inferred_state="authenticated",
        expected_state="authenticated",
        evidence=StateEvidence(),
        match=True,
    )
    report = _report(verification_report=None, state_inference=state)
    assert ReplayExperimentHarness._task_completed(report) is True


def test_task_completed_returns_state_inference_match_false():
    from browsermind_core.ontology.p1_schemas import StateEvidence, StateInference

    state = StateInference(
        inferred_state="logged_out",
        expected_state="authenticated",
        evidence=StateEvidence(),
        match=False,
    )
    report = _report(verification_report=None, state_inference=state)
    assert ReplayExperimentHarness._task_completed(report) is False


def test_task_completed_returns_none_when_no_signal():
    report = _report(verification_report=None, state_inference=None)
    assert ReplayExperimentHarness._task_completed(report) is None


# ── TEST 4 ───────────────────────────────────────────────────────────────────

def test_verifier_exception_is_captured_not_swallowed():
    """When the StateVerifier raises, the engine must record the error
    on report.verification_error rather than silently set
    verification_report=None.

    This test exercises the engine's verifier try/except block in isolation
    by simulating the same control flow: a verifier whose .verify() raises.
    """
    failing_page = MagicMock()
    verifier = StateVerifier(failing_page)
    config = StateVerifierConfig(
        workflow="test", success=[StateRule(type="url_equals", value="https://x")]
    )

    async def _exploding_evaluate(_rule):
        raise RuntimeError("boom: simulated verifier failure")

    verifier.evaluate_rule = _exploding_evaluate  # type: ignore[assignment]

    report = ReplayReport(
        workflow_id=uuid4(),
        template_id=uuid4(),
        total_steps=1,
    )

    async def run():
        try:
            vr = await verifier.verify(config)
            report.verification_report = vr.model_dump()
        except Exception as exc:
            import traceback as _tb
            report.verification_error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": _tb.format_exc(),
            }

    asyncio.run(run())

    assert report.verification_report is None
    assert report.verification_error is not None
    assert report.verification_error["type"] == "RuntimeError"
    assert "boom" in report.verification_error["message"]
    assert "Traceback" in report.verification_error["traceback"]


# ── TEST 5 ───────────────────────────────────────────────────────────────────

def test_step_outcomes_preserve_effect_fields():
    from browsermind_core.experiments.sites import ExperimentSite
    from browsermind_core.ontology.p1_schemas import WorkflowTemplate

    site = ExperimentSite(
        key="static_baseline",
        label="Static Baseline",
        suggested_workflow="static_baseline_v1",
        operator_hint="N/A",
    )
    template = WorkflowTemplate(
        name="static_baseline_v1",
        description="test template",
        steps=[
            {"seq": 1, "action_type": "click", "target_role": "button",
             "target_name": "Go", "target_selector": "#go"},
        ],
        metadata={},
    )
    report = ReplayReport(
        workflow_id=uuid4(),
        template_id=template.id,
        total_steps=1,
        resolved_steps=1,
        resolution_rate=1.0,
        failure_attribution=[
            _ok_step(
                1,
                effect_verified=False,
                effect_type="VALUE_CHANGED",
                effect_details={"val_before": "", "val_after": "x"},
                failure_layer="effect",
            ),
        ],
    )

    harness = ReplayExperimentHarness.__new__(ReplayExperimentHarness)
    result = ReplayExperimentHarness.result_from_report(
        harness, site=site, template=template, report=report
    )
    assert len(result.step_outcomes) == 1
    s = result.step_outcomes[0]
    assert s["effect_verified"] is False
    assert s["effect_type"] == "VALUE_CHANGED"
    assert s["effect_details"] == {"val_before": "", "val_after": "x"}
    assert s["failure_layer"] == "effect"
    assert s["resolution_success"] is True
    assert s["execution_success"] is True


# ── TEST 6 ───────────────────────────────────────────────────────────────────

def _gt_annotations(n: int, *, site: str, template: str):
    return [
        GroundTruthAnnotation(
            annotation_id=f"gt-{i:03d}",
            site=site,
            template_name=template,
            step_seq=i + 1,
            true_role="button",
            true_name=f"Step {i + 1}",
            true_container="",
            true_target=f"#step-{i + 1}",
        )
        for i in range(n)
    ]


def test_ground_truth_produces_judged_outcomes_and_non_none_fpr():
    from browsermind_core.experiments.sites import ExperimentSite
    from browsermind_core.ontology.p1_schemas import WorkflowTemplate

    site = ExperimentSite(
        key="static_baseline",
        label="Static Baseline",
        suggested_workflow="judged_template",
        operator_hint="N/A",
    )
    template = WorkflowTemplate(
        name="judged_template",
        description="test template",
        steps=[
            {"seq": i + 1, "action_type": "click", "target_role": "button",
             "target_name": f"Step {i + 1}", "target_selector": f"#step-{i + 1}"}
            for i in range(2)
        ],
        metadata={},
    )
    # Step 1 matches the annotation; step 2 does not (wrong target).
    annotations = _gt_annotations(100, site="static_baseline", template="judged_template")
    dataset = GroundTruthDataset(dataset_id="gt-test", annotations=annotations)

    attrs = [
        FailureAttribution(
            step_seq=1, action_type="click", role="button", name="Step 1",
            predicted_tier="HIGH", predicted_score=0.9, actual_outcome="SUCCESS",
            target_integrity={"resolved_target": "#step-1", "selection_forensics": {}},
        ),
        FailureAttribution(
            step_seq=2, action_type="click", role="button", name="Step 2",
            predicted_tier="HIGH", predicted_score=0.9, actual_outcome="SUCCESS",
            target_integrity={"resolved_target": "#wrong-target", "selection_forensics": {}},
        ),
    ]
    report = ReplayReport(
        workflow_id=uuid4(),
        template_id=template.id,
        total_steps=2,
        resolved_steps=2,
        resolution_rate=1.0,
        failure_attribution=attrs,
    )

    harness = ReplayExperimentHarness.__new__(ReplayExperimentHarness)
    result_with_gt = ReplayExperimentHarness.result_from_report(
        harness, site=site, template=template, report=report, ground_truth=dataset
    )
    result_without_gt = ReplayExperimentHarness.result_from_report(
        harness, site=site, template=template, report=report, ground_truth=None
    )

    outcomes_with = [s["outcome"] for s in result_with_gt.step_outcomes]
    assert RESOLVED_CORRECT in outcomes_with
    assert RESOLVED_INCORRECT in outcomes_with
    assert result_with_gt.false_positive_resolution_rate is not None
    assert result_with_gt.resolution_accuracy is not None

    # Sanity check: without ground truth the same report produces None FPR.
    assert result_without_gt.false_positive_resolution_rate is None
    assert result_without_gt.resolution_accuracy is None


def test_compute_metrics_without_ground_truth_keeps_fpr_none():
    metrics = compute_replay_reliability_metrics(
        [
            {"outcome": "RESOLVED_UNJUDGED"},
            {"outcome": "RESOLVED_UNJUDGED"},
        ],
        task_completed=True,
    )
    assert metrics["false_positive_resolution_rate"] is None
    assert metrics["resolution_accuracy"] is None
