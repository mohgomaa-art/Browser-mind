"""
ExecutionRepository
Sits between ExecutionEngine and PersistenceProvider.
Owns the Snapshot sequence, checkpoint management, and corruption recovery.
"""
from typing import Optional, List
from uuid import UUID
from browsermind_core.ontology.p1_schemas import Execution, SnapshotRecord
from browsermind_core.runtime.persistence import PersistenceProvider


class ExecutionRepository:
    EXEC_NS = "executions"
    SNAP_NS = "snapshots"

    def __init__(self, provider: PersistenceProvider):
        self.provider = provider

    # -------------------------------------------------------------------------
    # Execution persistence
    # -------------------------------------------------------------------------

    def save_execution(self, execution: Execution):
        self.provider.save(self.EXEC_NS, str(execution.id), execution.model_dump(mode="json"))

    def load_execution(self, execution_id: UUID) -> Optional[Execution]:
        data = self.provider.load(self.EXEC_NS, str(execution_id))
        if data is None:
            return None
        return Execution.model_validate(data)

    # -------------------------------------------------------------------------
    # Snapshot (checkpoint) management
    # -------------------------------------------------------------------------

    def save_snapshot(self, execution: Execution) -> SnapshotRecord:
        """Create a new sequenced SnapshotRecord for this Execution state."""
        existing = self.load_all_snapshots(execution.id)
        next_seq = len(existing)

        snapshot = SnapshotRecord(
            execution_id=execution.id,
            sequence=next_seq,
            execution_state=execution.model_dump(mode="json"),
            is_valid=True,
        )
        key = f"{execution.id}_seq{next_seq}"
        self.provider.save(self.SNAP_NS, key, snapshot.model_dump(mode="json"))
        return snapshot

    def load_all_snapshots(self, execution_id: UUID) -> List[SnapshotRecord]:
        """Load all valid snapshots for an execution, ordered by sequence."""
        all_keys = self.provider.list_keys(self.SNAP_NS)
        prefix = str(execution_id)
        snapshots: List[SnapshotRecord] = []

        for key in all_keys:
            if not key.startswith(prefix):
                continue
            data = self.provider.load(self.SNAP_NS, key)
            if data is None:
                continue  # Corrupted — skip silently
            snap = SnapshotRecord.model_validate(data)
            if snap.is_valid:
                snapshots.append(snap)

        snapshots.sort(key=lambda s: s.sequence)
        return snapshots

    def load_latest_valid_snapshot(self, execution_id: UUID) -> Optional[SnapshotRecord]:
        """
        Returns the latest valid snapshot.
        If the latest is corrupted, falls back to the previous valid one.
        """
        snapshots = self.load_all_snapshots(execution_id)
        if not snapshots:
            return None
        return snapshots[-1]  # already filtered to valid-only in load_all_snapshots

    def invalidate_snapshot(self, execution_id: UUID, sequence: int):
        """Mark a snapshot as invalid (e.g. after detecting corruption)."""
        key = f"{execution_id}_seq{sequence}"
        data = self.provider.load(self.SNAP_NS, key)
        if data:
            data["is_valid"] = False
            self.provider.save(self.SNAP_NS, key, data)
