"""A-1: ReplayEngine writes OutcomeRecord to OutcomeLedger per run.

These tests exercise the helper directly with stubbed inputs (no Playwright,
no AuthSession). The full replay() loop drives the helper at two return
points: the BLOCKED early return at identity precheck and the normal end-of-run
return. Both call _record_replay_outcome with the same arguments, so a unit
test of the helper plus a smoke test that both return paths invoke it gives
us full coverage without a real browser.

Cross-process survival is verified by writing through one OutcomeLedger,
discarding it, and rehydrating a fresh one against the same store dir.
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
    ReplayReport,
    WorkflowInstance,
    WorkflowTemplate,
)
from browsermind_core.runtime.replay_engine import ReplayEngine


REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


def _make_engine(outcome_ledger=None, persona_id=None):
    """Build a ReplayEngine with a fully stubbed AuthSession."""
    auth_session = MagicMock()
    return ReplayEngine(
        auth_session,
        outcome_ledger=outcome_ledger,
        persona_id=persona_id,
        environment_family="testfam",
        environment_instance="testinst",
    )


def _make_template():
    return WorkflowTemplate(
        name="t1",
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


def _make_success_report(template_id, instance_id):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="SUCCESS",
        total_steps=3,
        resolved_steps=3,
        failed_steps=0,
        ambiguous_steps=0,
        resolution_rate=1.0,
        ambiguity_rate=0.0,
        recovery_rate=100.0,
        duration_seconds=2.5,
    )


def _make_failure_report(template_id, instance_id):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="FAILED",
        total_steps=5,
        resolved_steps=2,
        failed_steps=3,
        ambiguous_steps=1,
        resolution_rate=0.4,
        ambiguity_rate=0.2,
        recovery_rate=50.0,
        duration_seconds=4.1,
        failure_reason="Step 3: target not found",
    )


# --- Helper unit tests --------------------------------------------------------


def test_helper_no_op_when_no_ledger():
    engine = _make_engine(outcome_ledger=None, persona_id=uuid4())
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = _make_success_report(template.id, instance.id)
    # Must not raise even with ledger=None
    engine._record_replay_outcome(report, template, instance)


def test_helper_no_op_when_no_persona_id():
    ledger = MagicMock()
    engine = _make_engine(outcome_ledger=ledger, persona_id=None)
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = _make_success_report(template.id, instance.id)
    engine._record_replay_outcome(report, template, instance)
    ledger.record.assert_not_called()


def test_helper_writes_success_record():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        engine = _make_engine(outcome_ledger=ks.outcome_ledger, persona_id=persona_id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)
        report = _make_success_report(template.id, instance.id)

        engine._record_replay_outcome(report, template, instance)

        assert len(ks.outcome_ledger.records) == 1
        rec = ks.outcome_ledger.records[0]
        assert rec.scope == "workflow_instance"
        assert rec.scope_id == instance.id
        assert rec.persona_id == persona_id
        assert rec.environment_family == "testfam"
        assert rec.environment_instance == "testinst"
        assert rec.outcome_type == "replay_run"
        assert rec.success is True
        assert rec.metrics["status"] == "SUCCESS"
        assert rec.metrics["resolved_steps"] == 3
        assert rec.metrics["resolution_rate"] == 1.0
        assert rec.metrics["template_id"] == str(template.id)


def test_helper_writes_failure_record_with_failure_reason_in_evidence():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        engine = _make_engine(outcome_ledger=ks.outcome_ledger, persona_id=persona_id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)
        report = _make_failure_report(template.id, instance.id)

        engine._record_replay_outcome(report, template, instance)

        rec = ks.outcome_ledger.records[0]
        assert rec.success is False
        assert "target not found" in rec.evidence
        assert rec.metrics["failed_steps"] == 3
        assert rec.metrics["ambiguous_steps"] == 1


def test_helper_swallow_recorded_exception_does_not_break_caller():
    """A ledger write failure must never break the replay return path."""
    bad_ledger = MagicMock()
    bad_ledger.record.side_effect = RuntimeError("disk full")
    engine = _make_engine(outcome_ledger=bad_ledger, persona_id=uuid4())
    template = _make_template()
    instance = _make_instance(template.id, uuid4())
    report = _make_success_report(template.id, instance.id)

    # Must not propagate
    engine._record_replay_outcome(report, template, instance)


# --- Cross-process restart ----------------------------------------------------


def test_outcome_record_survives_kernel_session_restart():
    """Write through one KernelSession, drop it, open a fresh one, find the record."""
    with tempfile.TemporaryDirectory() as td:
        # First session: write
        ks1 = KernelSession(td)
        persona_id = uuid4()
        template = _make_template()
        instance_id = uuid4()
        engine = ReplayEngine(
            MagicMock(),
            outcome_ledger=ks1.outcome_ledger,
            persona_id=persona_id,
            environment_family="testfam",
            environment_instance="saucedemo",
        )
        instance = WorkflowInstance(
            id=instance_id,
            persona_id=persona_id,
            template_id=template.id,
            bound_resources={},
            bound_identities={},
        )
        report = _make_success_report(template.id, instance.id)
        engine._record_replay_outcome(report, template, instance)
        assert len(ks1.outcome_ledger.records) == 1
        del ks1

        # Second session: same store, fresh instance, record must rehydrate
        ks2 = KernelSession(td)
        records = ks2.outcome_ledger.records
        assert len(records) == 1
        rec = records[0]
        assert rec.scope == "workflow_instance"
        assert rec.scope_id == instance_id
        assert rec.persona_id == persona_id
        assert rec.environment_instance == "saucedemo"
        assert rec.metrics["resolved_steps"] == 3
        assert rec.metrics["template_name"] == "t1"


def test_two_runs_produce_two_records():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        template = _make_template()

        for status_label, report_factory in [("SUCCESS", _make_success_report), ("FAILED", _make_failure_report)]:
            instance = _make_instance(template.id, persona_id)
            engine = ReplayEngine(
                MagicMock(),
                outcome_ledger=ks.outcome_ledger,
                persona_id=persona_id,
                environment_family="testfam",
                environment_instance="testinst",
            )
            report = report_factory(template.id, instance.id)
            engine._record_replay_outcome(report, template, instance)

        assert len(ks.outcome_ledger.records) == 2
        statuses = sorted(r.metrics["status"] for r in ks.outcome_ledger.records)
        assert statuses == ["FAILED", "SUCCESS"]


# --- Source-level coverage of both replay() return paths ----------------------


def test_normal_return_path_calls_record_replay_outcome():
    """Source-level: the final `return report` is preceded by _record_replay_outcome.

    Allows optional _close_execution_if_wired after (A-3), optional
    _record_replay_accuracy before (P4), and optional _record_step_outcomes
    after (Phase 1 step-scope writer) — all companions of the outcome write.
    """
    final = re.search(
        r"self\._record_replay_outcome\(report, template, instance\)\s*\n"
        r"(?:\s*self\._record_step_outcomes\([^)]*\)\s*\n)?"
        r"(?:\s*self\._close_execution_if_wired\(report\)\s*\n)?"
        r"\s*return report\s*$",
        REPLAY_ENGINE_SRC,
        re.MULTILINE,
    )
    assert final is not None, "Final return path does not call _record_replay_outcome"


def test_blocked_return_path_calls_record_replay_outcome():
    """Source-level: the BLOCKED early return is preceded by _record_replay_outcome.

    Allows optional _record_replay_accuracy (P4) before,
    _record_step_outcomes (Phase 1) after, and
    _close_execution_if_wired (A-3) after.
    """
    blocked = re.search(
        r'status="BLOCKED",\s*\n\s*\)\s*\n'
        r'(?:[^\n]*\n)*?'
        r'\s*self\._record_replay_outcome\(report, template, instance\)\s*\n'
        r'(?:\s*self\._record_step_outcomes\([^)]*\)\s*\n)?'
        r'(?:\s*self\._close_execution_if_wired\(report\)\s*\n)?'
        r'\s*return report',
        REPLAY_ENGINE_SRC,
    )
    assert blocked is not None, "BLOCKED return path does not call _record_replay_outcome"


def test_init_signature_accepts_outcome_ledger_and_persona_id():
    """The new keyword args must be present in __init__."""
    import inspect
    sig = inspect.signature(ReplayEngine.__init__)
    assert "outcome_ledger" in sig.parameters
    assert "persona_id" in sig.parameters
    assert "environment_family" in sig.parameters
    assert "environment_instance" in sig.parameters
    # All must default to a falsy value so existing call sites stay valid
    assert sig.parameters["outcome_ledger"].default is None
    assert sig.parameters["persona_id"].default is None
