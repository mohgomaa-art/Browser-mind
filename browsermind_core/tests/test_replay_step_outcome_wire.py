"""Phase 1: ReplayEngine._record_step_outcomes promotes every FailureAttribution
row to a durable OutcomeRecord(scope='step') with the BC-required fields:
  step_id, action, success, failure_class, root_cause, effect_verified.

These tests exercise the helper directly with stubbed inputs (no Playwright,
no AuthSession). Cross-process survival is exercised by writing through one
KernelSession-backed OutcomeLedger and rehydrating a fresh KernelSession.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.ontology.p1_schemas import (
    FailureAttribution,
    ReplayReport,
    WorkflowInstance,
    WorkflowTemplate,
)
from browsermind_core.runtime.replay_engine import ReplayEngine


REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


def _make_engine(outcome_ledger=None, persona_id=None):
    auth = MagicMock()
    return ReplayEngine(
        auth,
        outcome_ledger=outcome_ledger,
        persona_id=persona_id,
        environment_family="testfam",
        environment_instance="testinst",
    )


def _make_template(steps=None):
    return WorkflowTemplate(
        name="t1",
        description="phase 1 fixture",
        family_key="testfam",
        steps=steps or [],
        metadata={"compiled_from": "demo-1"},
    )


def _make_instance(template_id, persona_id):
    return WorkflowInstance(
        persona_id=persona_id,
        template_id=template_id,
        bound_resources={},
        bound_identities={},
    )


def _make_report(template_id, instance_id, attributions):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="SUCCESS" if all(a.actual_outcome == "SUCCESS" for a in attributions) else "FAILED",
        total_steps=len(attributions),
        resolved_steps=sum(1 for a in attributions if a.actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS")),
        failed_steps=sum(1 for a in attributions if a.actual_outcome == "FAILED"),
        ambiguous_steps=sum(1 for a in attributions if a.actual_outcome == "AMBIGUOUS_IDENTITY"),
        resolution_rate=1.0,
        ambiguity_rate=0.0,
        recovery_rate=100.0,
        duration_seconds=1.0,
        failure_attribution=attributions,
    )


def _attr_success(seq=1, action="click"):
    return FailureAttribution(
        step_seq=seq,
        action_type=action,
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
    )


def _attr_failed(seq=2, action="click", reason="TargetNotFound: role='button', name='Submit'"):
    return FailureAttribution(
        step_seq=seq,
        action_type=action,
        role="button",
        name="Submit",
        predicted_tier="HIGH",
        predicted_score=0.9,
        actual_outcome="FAILED",
        failure_reason=reason,
        resolution_success=False,
        execution_success=False,
        effect_verified=None,
        failure_layer="resolution",
    )


# --- Helper signature -------------------------------------------------------


def test_helper_exists_and_is_called_at_both_return_paths():
    assert "_record_step_outcomes" in REPLAY_ENGINE_SRC
    pat = re.compile(r"self\._record_step_outcomes\(report, template, instance, [^)]+\)")
    assert len(pat.findall(REPLAY_ENGINE_SRC)) >= 2, (
        "Phase 1: _record_step_outcomes must be called from both replay() return paths"
    )


# --- Behavioral: helper produces step-scope rows ----------------------------


def test_records_one_step_record_per_failure_attribution():
    with tempfile.TemporaryDirectory() as store:
        ks = KernelSession(store_dir=store)
        persona_id = uuid4()
        template = _make_template(steps=[{"action": "click"}, {"action": "click"}])
        instance = _make_instance(template.id, persona_id)
        attrs = [_attr_success(seq=1), _attr_failed(seq=2)]
        report = _make_report(template.id, instance.id, attrs)

        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="testinst",
        )
        engine._record_step_outcomes(report, template, instance, "demoqa")

        step_rows = [r for r in ks.outcome_ledger.records if r.scope == "step"]
        assert len(step_rows) == 2

        success_row = next(r for r in step_rows if r.success)
        assert success_row.outcome_type == "step_attempt"
        assert success_row.metrics["action"] == "click"
        assert success_row.metrics["failure_class"] is None
        assert success_row.metrics["root_cause"] is None
        assert success_row.metrics["effect_verified"] is True
        assert success_row.metrics["step_id"]
        assert len(success_row.metrics["step_id"]) == 32

        failed_row = next(r for r in step_rows if not r.success)
        assert failed_row.metrics["action"] == "click"
        assert failed_row.metrics["failure_class"] == "TARGET_CHANGED"
        assert "target" in (failed_row.metrics["root_cause"] or "").lower()
        assert failed_row.metrics["effect_verified"] is None


def test_step_id_is_deterministic_per_workflow_seq_action():
    """Same (instance, seq, action) → same step_id; differs on any axis."""
    with tempfile.TemporaryDirectory() as store:
        ks = KernelSession(store_dir=store)
        persona_id = uuid4()
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        attrs = [_attr_success(seq=1, action="click")]
        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="f",
            environment_instance="i",
        )
        engine._record_step_outcomes(_make_report(template.id, instance.id, attrs), template, instance, "k")
        engine._record_step_outcomes(_make_report(template.id, instance.id, attrs), template, instance, "k")

        rows = [r for r in ks.outcome_ledger.records if r.scope == "step"]
        assert len(rows) == 2
        assert rows[0].metrics["step_id"] == rows[1].metrics["step_id"]

        # Different action on same seq must change step_id.
        attrs2 = [_attr_success(seq=1, action="fill")]
        engine._record_step_outcomes(_make_report(template.id, instance.id, attrs2), template, instance, "k")
        rows2 = [r for r in ks.outcome_ledger.records if r.scope == "step"]
        ids = {r.metrics["step_id"] for r in rows2 if r.metrics["action"] == "click"}
        ids2 = {r.metrics["step_id"] for r in rows2 if r.metrics["action"] == "fill"}
        assert ids and ids2 and ids.isdisjoint(ids2)


def test_step_records_survive_kernel_session_restart():
    with tempfile.TemporaryDirectory() as store:
        persona_id = uuid4()
        template = _make_template(steps=[{"action": "click"}])
        instance = _make_instance(template.id, persona_id)

        ks1 = KernelSession(store_dir=store)
        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks1.outcome_ledger,
            persona_id=persona_id,
            environment_family="f",
            environment_instance="i",
        )
        engine._record_step_outcomes(
            _make_report(template.id, instance.id, [_attr_failed(seq=1)]),
            template, instance, "demoqa",
        )

        ks2 = KernelSession(store_dir=store)
        rows = [r for r in ks2.outcome_ledger.records if r.scope == "step"]
        assert len(rows) == 1
        assert rows[0].metrics["failure_class"] == "TARGET_CHANGED"


def test_no_ledger_means_helper_is_a_no_op():
    engine = _make_engine(outcome_ledger=None, persona_id=None)
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = _make_report(template.id, instance.id, [_attr_success()])
    # Should not raise.
    engine._record_step_outcomes(report, template, instance, "k")


def test_empty_failure_attribution_writes_nothing():
    with tempfile.TemporaryDirectory() as store:
        ks = KernelSession(store_dir=store)
        persona_id = uuid4()
        template = _make_template()
        instance = _make_instance(template.id, persona_id)
        report = _make_report(template.id, instance.id, [])

        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks.outcome_ledger,
            persona_id=persona_id,
            environment_family="f",
            environment_instance="i",
        )
        engine._record_step_outcomes(report, template, instance, "k")
        assert [r for r in ks.outcome_ledger.records if r.scope == "step"] == []
