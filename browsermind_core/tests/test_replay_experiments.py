"""Unit tests for replay validation experiment harness."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from browsermind_core.experiments.failure_taxonomy import classify_failure
from browsermind_core.experiments.replay_result import FailureCategory, ReplayResult
from browsermind_core.experiments.report_generator import (
    evaluate_decision_thresholds,
    generate_summary_report,
)
from browsermind_core.ontology.p1_schemas import FailureAttribution, ReplayReport


def _result(**kwargs) -> ReplayResult:
    defaults = dict(
        workflow_id=uuid4(),
        total_steps=10,
        resolved_steps=10,
        failed_steps=0,
        resolution_rate=1.0,
        workflow_failed=False,
        replay_success=True,
        timestamp=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return ReplayResult(**defaults)


def test_classify_empty_semantics():
    step = {
        "target_role": "img",
        "target_name": "",
        "replayability": {"reasons": ["generic_role_with_no_name"]},
    }
    category, reason = classify_failure(
        failure_reason="Step 3: click - role='img', name='' -> TargetNotFound",
        failed_step=step,
    )
    assert category == FailureCategory.NO_VISIBLE_SIGNAL
    assert reason == "img + empty name"


def test_classify_ambiguous_target():
    step = {
        "target_role": "button",
        "target_name": "Submit",
        "replayability": {"reasons": ["multiple_candidates"]},
    }
    category, reason = classify_failure(
        failure_reason="multiple matching elements for role='button'",
        failed_step=step,
    )
    assert category == FailureCategory.AMBIGUOUS_TARGET


def test_classify_target_changed():
    step = {
        "target_role": "button",
        "target_name": "Login",
        "replayability": {"tier": "HIGH", "reasons": []},
    }
    category, _ = classify_failure(
        failure_reason="Step 2: click - role='button', name='Login' -> TargetNotFound",
        failed_step=step,
    )
    assert category == FailureCategory.TARGET_CHANGED


def test_classify_environment_failure():
    category, _ = classify_failure(
        failure_reason="ExecutionError: Failed to execute 'click': Timeout 10000ms exceeded.",
        failed_step={"target_role": "button", "target_name": "Go"},
    )
    assert category == FailureCategory.ENVIRONMENT_FAILURE


def test_replay_result_schema_roundtrip():
    result = ReplayResult(
        workflow_id=uuid4(),
        site="saucedemo",
        total_steps=11,
        resolved_steps=1,
        failed_steps=1,
        resolution_rate=0.09,
        workflow_failed=True,
        replay_success=False,
        failure_reason="img + empty name",
        failure_category=FailureCategory.NO_VISIBLE_SIGNAL,
        failed_step=3,
        timestamp=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )
    payload = result.model_dump(mode="json")
    restored = ReplayResult.model_validate(payload)
    assert restored.site == "saucedemo"
    assert restored.failure_category == FailureCategory.NO_VISIBLE_SIGNAL
    assert restored.workflow_failed is True


def test_resolution_and_workflow_failure_are_independent():
    result = _result(
        site="demoqa",
        total_steps=10,
        resolved_steps=9,
        failed_steps=0,
        resolution_rate=0.9,
        workflow_failed=True,
        replay_success=False,
        failure_category=FailureCategory.ENVIRONMENT_FAILURE,
        failure_reason="timeout on submit",
        failed_step=10,
    )
    assert result.resolution_rate == 0.9
    assert result.workflow_failed is True


def test_summary_report_leads_with_resolution():
    results = [
        _result(site="saucedemo"),
        _result(
            site="github",
            total_steps=8,
            resolved_steps=2,
            failed_steps=1,
            resolution_rate=0.25,
            workflow_failed=True,
            replay_success=False,
            failure_reason="img + empty name",
            failure_category=FailureCategory.NO_VISIBLE_SIGNAL,
            failed_step=2,
        ),
    ]
    summary = generate_summary_report(results)
    assert "primary_kpi" in summary
    assert summary["primary_kpi"]["avg_resolution_rate"] == 0.625
    assert summary["secondary_kpi"]["workflow_failures"] == 1
    assert "saucedemo" in summary["by_site"]
    assert summary["by_site"]["saucedemo"]["avg_resolution_rate"] == 1.0


def test_decision_thresholds_stop_on_low_saucedemo():
    results = [_result(site="static_baseline", resolution_rate=0.95), _result(site="saucedemo", resolution_rate=0.5)]
    thresholds = evaluate_decision_thresholds(results)
    assert thresholds["stop_recommended"] is True
    assert "saucedemo" in thresholds["stop_reason"]


def test_decision_thresholds_engine_valid():
    results = [
        _result(site="static_baseline", resolution_rate=0.95),
        _result(site="saucedemo", resolution_rate=0.95),
        _result(site="demoqa", resolution_rate=0.85),
    ]
    thresholds = evaluate_decision_thresholds(results)
    rules = {d["rule"]: d for d in thresholds["decisions"]}
    assert rules["replay_engine_likely_valid"]["passed"] is True


def test_decision_thresholds_semantic_survivability():
    results = [
        _result(site="saucedemo", resolution_rate=0.97),
        _result(site="github", resolution_rate=0.20),
    ]
    thresholds = evaluate_decision_thresholds(results)
    rules = {d["rule"]: d for d in thresholds["decisions"]}
    assert rules["semantic_survivability_bottleneck"]["passed"] is True


def test_harness_replay_success_from_report():
    from browsermind_core.experiments.harness import ReplayExperimentHarness

    report = ReplayReport(
        workflow_id=uuid4(),
        template_id=uuid4(),
        total_steps=2,
        failure_attribution=[
            FailureAttribution(
                step_seq=1,
                action_type="click",
                role="button",
                name="Login",
                predicted_tier="HIGH",
                predicted_score=0.9,
                actual_outcome="SUCCESS",
            ),
            FailureAttribution(
                step_seq=2,
                action_type="fill",
                role="textbox",
                name="Username",
                predicted_tier="HIGH",
                predicted_score=0.9,
                actual_outcome="SUCCESS",
            ),
        ],
    )
    assert ReplayExperimentHarness._replay_success(report, 2) is True

    failed = ReplayReport(
        workflow_id=uuid4(),
        template_id=uuid4(),
        total_steps=2,
        failure_reason="Step 2: fill failed",
        failure_attribution=[
            FailureAttribution(
                step_seq=1,
                action_type="click",
                role="button",
                name="Login",
                predicted_tier="HIGH",
                predicted_score=0.9,
                actual_outcome="SUCCESS",
            ),
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
        ],
    )
    assert ReplayExperimentHarness._replay_success(failed, 2) is False
