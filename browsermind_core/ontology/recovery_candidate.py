"""RecoveryCandidate — Phase 4 of R6 v1.

A RecoveryCandidate is a (predicate, primitive) pair the system has mined
from recurring failure patterns. It walks the strict approval lifecycle:

    pending      — emitted by the miner; awaiting first shadow trials
    shadow       — accumulating shadow_results; not yet ready to promote
    ready        — promotion gate passed; operator may approve
    approved     — operator approved but commit not yet executed (transient)
    committed    — written to recovery_ladder.json; live in runtime
    rejected     — operator rejected; will not be reconsidered
    quarantined  — committed but real-traffic lift went negative; skipped
    rolled_back  — operator restored ladder to previous_state

The schema mirrors TemplateCandidate so we can reuse the persistence
pattern. shadow_metrics and previous_state are populated on demand by
the shadow validator (Phase 5) and the approval CLI (Phase 7).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


RecoveryStatus = Literal[
    "pending", "shadow", "ready", "approved",
    "committed", "rejected", "quarantined", "rolled_back",
]


class RecoveryCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str                                  # short human label, e.g. "mined:by_text+name>=0.8"
    predicate: Dict[str, Any]                  # mined conjunction: {"has_X": True, ...}
    primitive: str                             # key in PRIMITIVE_LIBRARY
    primitive_args: Dict[str, Any] = Field(default_factory=dict)
    support: int = 0                           # observations producing this pattern
    lift: float = 0.0                          # miner-reported lift
    mined_from: List[str] = Field(default_factory=list)  # OutcomeRecord ids
    shadow_metrics: Dict[str, Any] = Field(default_factory=dict)
    status: RecoveryStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    committed_at: Optional[datetime] = None
    previous_state: Optional[Dict[str, Any]] = None  # snapshot of recovery_ladder.json for rollback


class RecoveryCandidateRegistry:
    """Append-friendly persistence for RecoveryCandidates. Mirrors the
    structure of CandidateRegistry (template_candidate.py) so the CLI
    glue layer can be near-identical."""

    NS = "recovery_candidate"
    IDX = "_recovery_candidate_index.json"

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self.provider = LocalJSONPersistenceProvider(store_dir)

    # --- index helpers -----------------------------------------------------

    def _idx_path(self) -> str:
        return os.path.join(self.store_dir, self.IDX)

    def _load_idx(self) -> Dict[str, Dict[str, Any]]:
        path = self._idx_path()
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_idx(self, idx: Dict[str, Dict[str, Any]]) -> None:
        with open(self._idx_path(), "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2)

    def _index_entry(self, c: RecoveryCandidate) -> Dict[str, Any]:
        return {
            "id": str(c.id),
            "name": c.name,
            "primitive": c.primitive,
            "status": c.status,
            "support": c.support,
            "lift": round(float(c.lift or 0.0), 4),
            "created_at": c.created_at.isoformat(),
        }

    # --- CRUD --------------------------------------------------------------

    def save(self, candidate: RecoveryCandidate) -> None:
        self.provider.save(self.NS, str(candidate.id), candidate.model_dump(mode="json"))
        idx = self._load_idx()
        idx[str(candidate.id)] = self._index_entry(candidate)
        self._save_idx(idx)

    def get(self, candidate_id: UUID) -> Optional[RecoveryCandidate]:
        data = self.provider.load(self.NS, str(candidate_id))
        if not data:
            return None
        return RecoveryCandidate.model_validate(data)

    def list(self, status: Optional[str] = None) -> List[RecoveryCandidate]:
        out: List[RecoveryCandidate] = []
        for key in self.provider.list_keys(self.NS):
            data = self.provider.load(self.NS, key)
            if not data:
                continue
            c = RecoveryCandidate.model_validate(data)
            if status is None or c.status == status:
                out.append(c)
        out.sort(key=lambda c: c.created_at)
        return out

    def update_status(
        self,
        candidate_id: UUID,
        status: RecoveryStatus,
        *,
        committed_at: Optional[datetime] = None,
        shadow_metrics: Optional[Dict[str, Any]] = None,
        previous_state: Optional[Dict[str, Any]] = None,
    ) -> RecoveryCandidate:
        c = self.get(candidate_id)
        if c is None:
            raise KeyError(f"No recovery candidate {candidate_id}")
        c.status = status
        if committed_at is not None:
            c.committed_at = committed_at
        if shadow_metrics is not None:
            c.shadow_metrics = shadow_metrics
        if previous_state is not None:
            c.previous_state = previous_state
        self.provider.save(self.NS, str(c.id), c.model_dump(mode="json"))
        idx = self._load_idx()
        idx[str(c.id)] = self._index_entry(c)
        self._save_idx(idx)
        return c
