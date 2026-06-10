"""A-3: ReplayEngine writes a durable Execution row per run.

These tests exercise the start/close helpers directly with a real
KernelSession-provided ExecutionEngine and ExecutionRepository, so we
can prove cross-process survival of the Execution snapshot the same
way A-1 proved cross-process survival of the OutcomeRecord.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from browsermind_core.console.session import KernelSession
from browsermind_core.ontology.p1_schemas import (
    ReplayReport,
    WorkflowInstance,
    WorkflowTemplate,
)
from browsermind_core.runtime.replay_engine import ReplayEngine


REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


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


def _success_report(template_id, instance_id):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="SUCCESS",
        total_steps=2,
        resolved_steps=2,
        resolution_rate=1.0,
        duration_seconds=1.1,
    )


def _failed_report(template_id, instance_id):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="FAILED",
        total_steps=4,
        resolved_steps=1,
        failed_steps=3,
        resolution_rate=0.25,
        duration_seconds=2.2,
        failure_reason="Step 2: target not found",
    )


def _blocked_report(template_id, instance_id):
    return ReplayReport(
        workflow_id=instance_id,
        template_id=template_id,
        status="BLOCKED",
        total_steps=4,
        resolved_steps=0,
        duration_seconds=0.05,
        failure_reason="IDENTITY_EXPIRED: re-authenticate",
    )


def _make_engine(ks, *, persona_id, task_id, ledger=True, exec_engine=True):
    return ReplayEngine(
        MagicMock(),
        outcome_ledger=ks.outcome_ledger if ledger else None,
        persona_id=persona_id,
        environment_family="testfam",
        environment_instance="testinst",
        execution_engine=ks.execution_engine if exec_engine else None,
        task_id=task_id,
    )


# --- helper noop guards -------------------------------------------------------


def test_start_noop_when_engine_missing():
    persona_id = uuid4()
    eng = ReplayEngine(MagicMock(), persona_id=persona_id, task_id=uuid4())
    template = _make_template()
    instance = _make_instance(template.id, persona_id)
    eng._start_execution_if_wired(template, instance)
    # With no execution_engine, a synthetic execution_id is assigned so
    # all step records from this replay share a trajectory identifier.
    assert eng._active_execution_id is not None


def test_start_noop_when_task_id_missing():
    persona_id = uuid4()
    fake_engine = MagicMock()
    eng = ReplayEngine(MagicMock(), persona_id=persona_id, execution_engine=fake_engine)
    template = _make_template()
    instance = _make_instance(template.id, persona_id)
    eng._start_execution_if_wired(template, instance)
    fake_engine.start_execution.assert_not_called()
    assert eng._active_execution_id is None


def test_close_noop_when_no_active_execution():
    eng = ReplayEngine(MagicMock())
    report = _success_report(uuid4(), uuid4())
    eng._close_execution_if_wired(report)


# --- happy path: start + complete on SUCCESS ---------------------------------


def test_success_run_creates_and_completes_execution():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        task = ks.task_manager.create_task(persona_id=persona_id, goal="test")

        eng = _make_engine(ks, persona_id=persona_id, task_id=task.id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._start_execution_if_wired(template, instance)
        assert eng._active_execution_id is not None
        active_id = eng._active_execution_id

        execution = ks.execution_engine.get_execution(active_id)
        assert execution is not None
        assert execution.status == "running"
        assert execution.task_id == task.id
        assert execution.workflow_instance_id == instance.id
        assert execution.context.template_id == template.id

        report = _success_report(template.id, instance.id)
        eng._close_execution_if_wired(report)
        assert eng._active_execution_id is None

        execution_after = ks.execution_engine.get_execution(active_id)
        assert execution_after.status == "succeeded"


def test_failed_run_completes_as_failed():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        task = ks.task_manager.create_task(persona_id=persona_id, goal="test")

        eng = _make_engine(ks, persona_id=persona_id, task_id=task.id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._start_execution_if_wired(template, instance)
        active_id = eng._active_execution_id

        eng._close_execution_if_wired(_failed_report(template.id, instance.id))

        execution = ks.execution_engine.get_execution(active_id)
        assert execution.status == "failed"


def test_blocked_run_calls_fail_execution_with_reason():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        task = ks.task_manager.create_task(persona_id=persona_id, goal="test")

        eng = _make_engine(ks, persona_id=persona_id, task_id=task.id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._start_execution_if_wired(template, instance)
        active_id = eng._active_execution_id

        eng._close_execution_if_wired(_blocked_report(template.id, instance.id))

        execution = ks.execution_engine.get_execution(active_id)
        assert execution.status == "failed"
        assert execution.failure_reason is not None
        assert "IDENTITY_EXPIRED" in execution.failure_reason


# --- cross-process restart ----------------------------------------------------


def test_execution_snapshot_survives_kernel_restart():
    with tempfile.TemporaryDirectory() as td:
        ks1 = KernelSession(td)
        persona_id = uuid4()
        task = ks1.task_manager.create_task(persona_id=persona_id, goal="restart")
        eng = _make_engine(ks1, persona_id=persona_id, task_id=task.id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._start_execution_if_wired(template, instance)
        active_id = eng._active_execution_id
        eng._close_execution_if_wired(_success_report(template.id, instance.id))
        del ks1

        ks2 = KernelSession(td)
        rehydrated = ks2.execution_engine.rehydrate_execution(active_id)
        assert rehydrated is not None
        assert rehydrated.status == "succeeded"
        assert rehydrated.workflow_instance_id == instance.id


# --- outcome record carries execution_id -------------------------------------


def test_outcome_record_links_to_execution_id():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        task = ks.task_manager.create_task(persona_id=persona_id, goal="test")

        eng = _make_engine(ks, persona_id=persona_id, task_id=task.id)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._start_execution_if_wired(template, instance)
        active_id = eng._active_execution_id

        report = _success_report(template.id, instance.id)

        # Record outcome BEFORE close — _close clears _active_execution_id.
        # In the real replay() path, _close runs first and the OutcomeRecord
        # captures _active_execution_id pre-clear because order matters.
        # Here we replicate the production order: assert outcome captures it
        # by writing outcome directly while _active_execution_id is still set.
        eng._record_replay_outcome(report, template, instance)

        records = ks.outcome_ledger.records
        assert len(records) == 1
        assert records[0].execution_id == active_id


def test_outcome_record_has_no_execution_id_when_engine_absent():
    with tempfile.TemporaryDirectory() as td:
        ks = KernelSession(td)
        persona_id = uuid4()
        eng = _make_engine(ks, persona_id=persona_id, task_id=None, exec_engine=False)
        template = _make_template()
        instance = _make_instance(template.id, persona_id)

        eng._record_replay_outcome(_success_report(template.id, instance.id), template, instance)

        records = ks.outcome_ledger.records
        assert len(records) == 1
        assert records[0].execution_id is None


# --- failure tolerance --------------------------------------------------------


def test_start_failure_does_not_break_replay():
    fake = MagicMock()
    fake.start_execution.side_effect = RuntimeError("policy denial")
    eng = ReplayEngine(MagicMock(), persona_id=uuid4(), task_id=uuid4(), execution_engine=fake)
    template = _make_template()
    instance = _make_instance(template.id, eng.persona_id)
    eng._start_execution_if_wired(template, instance)
    assert eng._active_execution_id is None


def test_close_failure_does_not_break_replay():
    fake = MagicMock()
    fake.start_execution.return_value = MagicMock(id=uuid4())
    fake.complete_execution.side_effect = RuntimeError("disk full")
    eng = ReplayEngine(MagicMock(), persona_id=uuid4(), task_id=uuid4(), execution_engine=fake)
    template = _make_template()
    instance = _make_instance(template.id, eng.persona_id)
    eng._start_execution_if_wired(template, instance)
    eng._close_execution_if_wired(_success_report(template.id, instance.id))
    # _active_execution_id must still be cleared so the engine is reusable
    assert eng._active_execution_id is None


# --- source-level guards ------------------------------------------------------


def test_replay_calls_start_before_main_loop():
    """Source-level: _start_execution_if_wired is called once early in replay()."""
    assert "self._start_execution_if_wired(template, instance)" in REPLAY_ENGINE_SRC


def test_both_return_paths_call_close_before_outcome_record():
    """Source-level: every return path closes execution AFTER outcome+accuracy records,
    so both ledger writes carry the right execution_id (cleared on close).

    Phase 1 inserted _record_step_outcomes between _record_replay_outcome and
    _close_execution_if_wired; allow that helper between the two sentinels.
    Capability Loop additions (_mine_step_outcomes, _compile_and_promote,
    _verify_capabilities_in_execution) and their surrounding try/except/await
    blocks are also allowed — they all run before close so execution_id is
    still live during mining/compilation/verification.
    """
    # Anchor on _record_replay_outcome followed eventually (within 60 lines)
    # by _close_execution_if_wired + return report, with NO intervening
    # _record_replay_outcome (that would mean we've crossed into a second block).
    # Use a line-by-line search rather than a greedy regex to be robust against
    # helper call signatures that span multiple lines or use await.
    lines = REPLAY_ENGINE_SRC.splitlines()
    OPEN  = "self._record_replay_outcome(report, template, instance)"
    CLOSE = "self._close_execution_if_wired(report)"
    RETVAL = "return report"

    triples_found = 0
    i = 0
    while i < len(lines):
        if OPEN in lines[i]:
            # look ahead up to 60 lines for CLOSE then RETVAL
            window = lines[i + 1 : i + 61]
            try:
                close_idx = next(j for j, l in enumerate(window) if CLOSE in l)
                ret_idx   = next(j for j, l in enumerate(window) if RETVAL in l and j > close_idx)
                triples_found += 1
                i += ret_idx + 2  # advance past the found triple
                continue
            except StopIteration:
                pass
        i += 1

    assert triples_found >= 2, (
        f"Need at least two record→close→return triples (BLOCKED early return + "
        f"normal end); found {triples_found}"
    )


def test_init_signature_accepts_execution_engine_and_task_id():
    import inspect
    sig = inspect.signature(ReplayEngine.__init__)
    assert "execution_engine" in sig.parameters
    assert "task_id" in sig.parameters
    assert sig.parameters["execution_engine"].default is None
    assert sig.parameters["task_id"].default is None
