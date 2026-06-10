"""
tests/test_execution_recovery.py

Full P0.5-P0.7 Recovery Test Suite.
Tests A, B, C — each proves a harder invariant than the previous.
"""
import pytest
import os
import shutil
import json
from uuid import uuid4

from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.ledger.mutation_ledger import MutationLedger
from browsermind_core.managers.policy.policy_engine import PolicyEngine
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.runtime.execution_repository import ExecutionRepository
from browsermind_core.runtime.execution_engine import ExecutionEngine

STORAGE_DIR = ".test_recovery_store"


@pytest.fixture(autouse=True)
def clean_storage():
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    yield
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)


def _make_engine(max_retries=3) -> tuple[ExecutionEngine, ExecutionRepository]:
    event_bus = EventBus()
    MutationLedger(event_bus)
    policy_engine = PolicyEngine()
    provider = LocalJSONPersistenceProvider(STORAGE_DIR)
    repo = ExecutionRepository(provider)
    engine = ExecutionEngine(event_bus, policy_engine, repo, max_retries=max_retries)
    return engine, repo


# =============================================================================
# Test A — Survival: Running → Pause → Crash → Restart → Resume → Success
# =============================================================================

def test_A_survival_across_crash():
    engine_v1, repo = _make_engine()
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine_v1.start_execution(task_id, wf_id, tmpl_id, persona_id)
    engine_v1.pause_execution(execution.id)
    assert engine_v1.get_execution(execution.id).status == "paused"

    # CRASH — destroy the engine entirely
    del engine_v1

    # RESTART — brand new engine, same repo
    event_bus2 = EventBus()
    engine_v2 = ExecutionEngine(event_bus2, PolicyEngine(), repo)

    rehydrated = engine_v2.rehydrate_execution(execution.id)
    assert rehydrated is not None
    assert rehydrated.id == execution.id
    assert rehydrated.status == "paused"

    # Verify deterministic rehydration invariant: IDs and context must match exactly
    assert rehydrated.context.task_id == task_id
    assert rehydrated.context.persona_id == persona_id

    engine_v2.resume_execution(rehydrated.id)
    engine_v2.complete_execution(rehydrated.id, outcome="success")
    assert engine_v2.get_execution(rehydrated.id).status == "succeeded"


# =============================================================================
# Test B — Latest Checkpoint Wins: Must not restore stale state
# =============================================================================

def test_B_latest_checkpoint_wins():
    engine, repo = _make_engine()
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine.start_execution(task_id, wf_id, tmpl_id, persona_id)
    # Checkpoint #0 = running

    engine.pause_execution(execution.id)
    # Checkpoint #1 = paused

    # Verify 2 snapshots exist
    snaps = repo.load_all_snapshots(execution.id)
    assert len(snaps) == 2
    assert snaps[0].execution_state["status"] == "running"   # seq 0
    assert snaps[1].execution_state["status"] == "paused"    # seq 1

    # CRASH
    del engine

    # RESTART
    engine2 = ExecutionEngine(EventBus(), PolicyEngine(), repo)
    rehydrated = engine2.rehydrate_execution(execution.id)

    # Must rehydrate from seq #1 (paused), NOT seq #0 (running)
    assert rehydrated.status == "paused"

    latest_snap = repo.load_latest_valid_snapshot(execution.id)
    assert latest_snap.sequence == 1


# =============================================================================
# Test C — Corruption Recovery: Corrupted latest → fallback to previous valid
# =============================================================================

def test_C_corrupted_snapshot_fallback():
    engine, repo = _make_engine()
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine.start_execution(task_id, wf_id, tmpl_id, persona_id)
    # Checkpoint #0 = running

    engine.pause_execution(execution.id)
    # Checkpoint #1 = paused

    snaps = repo.load_all_snapshots(execution.id)
    assert len(snaps) == 2

    # Corrupt the LATEST snapshot file by writing garbage directly to disk
    seq1_key = f"{execution.id}_seq1"
    snap_path = os.path.join(STORAGE_DIR, "snapshots", f"{seq1_key}.json")
    assert os.path.exists(snap_path)
    with open(snap_path, "w") as f:
        json.dump({"_checksum": "corrupted_garbage", "_data": {"broken": True}}, f)

    # CRASH
    del engine

    # RESTART — repository must skip the corrupted snapshot and return seq #0
    engine2 = ExecutionEngine(EventBus(), PolicyEngine(), repo)
    rehydrated = engine2.rehydrate_execution(execution.id)

    # Must fallback to seq #0 (running), not crash or return None
    assert rehydrated is not None
    assert rehydrated.status == "running"   # Fallback to last known good state


# =============================================================================
# Test D — Failure / Retry Arc
# =============================================================================

def test_D_failure_and_retry():
    engine, _ = _make_engine(max_retries=2)
    task_id, wf_id, tmpl_id, persona_id = uuid4(), uuid4(), uuid4(), uuid4()

    execution = engine.start_execution(task_id, wf_id, tmpl_id, persona_id)

    engine.fail_execution(execution.id, reason="Anti-bot blocked")
    assert engine.get_execution(execution.id).status == "failed"
    assert engine.get_execution(execution.id).failure_reason == "Anti-bot blocked"

    engine.retry_execution(execution.id)
    assert engine.get_execution(execution.id).status == "running"
    assert engine.get_execution(execution.id).retry_count == 1

    engine.fail_execution(execution.id, reason="Network timeout")
    engine.retry_execution(execution.id)
    assert engine.get_execution(execution.id).retry_count == 2

    # Max retries reached — next retry must raise
    engine.fail_execution(execution.id, reason="Final failure")
    with pytest.raises(RuntimeError, match="Max retries exhausted"):
        engine.retry_execution(execution.id)

    assert engine.get_execution(execution.id).status == "failed"
