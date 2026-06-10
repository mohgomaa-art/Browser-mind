"""
tests/test_failure_recovery.py
Superseded by test_execution_recovery.py::test_D_failure_and_retry.
This file is kept to maintain the explicit, standalone failure arc test.
"""
import pytest
import os
import shutil
from uuid import uuid4

from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.ledger.mutation_ledger import MutationLedger
from browsermind_core.managers.policy.policy_engine import PolicyEngine
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.runtime.execution_repository import ExecutionRepository
from browsermind_core.runtime.execution_engine import ExecutionEngine

STORAGE_DIR = ".test_failure_store"


@pytest.fixture(autouse=True)
def clean_storage():
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    yield
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)


def _make_engine(max_retries: int = 3) -> ExecutionEngine:
    event_bus = EventBus()
    MutationLedger(event_bus)
    policy_engine = PolicyEngine()
    provider = LocalJSONPersistenceProvider(STORAGE_DIR)
    repo = ExecutionRepository(provider)
    return ExecutionEngine(event_bus, policy_engine, repo, max_retries=max_retries)


def test_failure_and_retry():
    """Running → Failed → Retry → Running → Success"""
    engine = _make_engine()
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine.start_execution(task_id, wf_id, tmpl_id, persona_id)
    assert execution.status == "running"

    engine.fail_execution(execution.id, reason="Anti-bot blocked the page")
    assert engine.get_execution(execution.id).status == "failed"
    assert engine.get_execution(execution.id).failure_reason == "Anti-bot blocked the page"

    engine.retry_execution(execution.id)
    assert engine.get_execution(execution.id).status == "running"
    assert engine.get_execution(execution.id).retry_count == 1

    engine.complete_execution(execution.id, outcome="success")
    assert engine.get_execution(execution.id).status == "succeeded"


def test_max_retry_exhaustion():
    """Proves the engine enforces a max_retries ceiling."""
    engine = _make_engine(max_retries=2)
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine.start_execution(task_id, wf_id, tmpl_id, persona_id)

    engine.fail_execution(execution.id, reason="Timeout")
    engine.retry_execution(execution.id)
    assert engine.get_execution(execution.id).retry_count == 1

    engine.fail_execution(execution.id, reason="Timeout again")
    engine.retry_execution(execution.id)
    assert engine.get_execution(execution.id).retry_count == 2

    engine.fail_execution(execution.id, reason="Final failure")
    with pytest.raises(RuntimeError, match="Max retries exhausted"):
        engine.retry_execution(execution.id)

    assert engine.get_execution(execution.id).status == "failed"
