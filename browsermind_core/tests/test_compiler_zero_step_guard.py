"""B-4: guard against emitting 0-step compiled WorkflowTemplate."""
from __future__ import annotations

import tempfile

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ontology.p1_schemas import WorkflowTemplate
from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
from browsermind_core.recorder.demonstration_session import (
    DemonstrationSession,
    DemonstrationStep,
)


def _all_filtered_session() -> DemonstrationSession:
    session = DemonstrationSession(
        persona_name="pilot",
        environment_family="empty_fam",
        environment_instance="https://example.test/",
    )
    session.append(DemonstrationStep(seq=0, action_type="session"))
    session.append(
        DemonstrationStep(
            seq=0,
            action_type="click",
            target_role="canvas",
            target_name="anywhere",
        )
    )
    session.append(
        DemonstrationStep(
            seq=0,
            action_type="click",
            target_role="button",
            target_name="begin",
        )
    )
    return session


def test_compile_raises_when_all_actions_filtered():
    with tempfile.TemporaryDirectory() as store_dir:
        ks = KernelSession(store_dir=store_dir)
        session = _all_filtered_session()

        emitted = []
        ks.event_bus.subscribe("EntityMutated", lambda e: emitted.append(e))

        compiler = DemonstrationCompiler(ks)
        with pytest.raises(ValueError) as exc:
            compiler.compile(session, "empty_test")

        msg = str(exc.value)
        assert str(session.id) in msg
        assert "0 steps" in msg

        assert ks.workflow_store.list_templates() == []
        assert emitted == []


def test_compile_happy_path_one_real_action():
    with tempfile.TemporaryDirectory() as store_dir:
        ks = KernelSession(store_dir=store_dir)
        session = DemonstrationSession(
            persona_name="pilot",
            environment_family="happy_fam",
            environment_instance="https://example.test/",
        )
        session.append(
            DemonstrationStep(
                seq=0,
                action_type="click",
                target_role="button",
                target_name="Submit order",
                target_selector="button#order",
            )
        )

        compiler = DemonstrationCompiler(ks)
        tpl = compiler.compile(session, "happy_test")

        assert isinstance(tpl, WorkflowTemplate)
        assert len(tpl.steps) == 1
        assert tpl.steps[0]["action_type"] == "click"
        assert ks.workflow_store.list_templates()[0]["name"] == "happy_test"
