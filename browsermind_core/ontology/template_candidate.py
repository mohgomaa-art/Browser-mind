"""TemplateCandidate — Self-Learning v1 human-approval surface.

A TemplateCandidate captures a proposed mutation to a WorkflowTemplate that
must be approved by a human before being applied. The compiler emits one
candidate per compilation when lesson evidence suggests tier downgrades.
Approval, rejection and rollback are surfaced through `bm workflow candidate`.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


class TemplateCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    parent_id: UUID
    parent_version: str = "compiled"
    mutations: List[Dict[str, Any]]
    lesson_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected", "committed", "rolled_back"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    committed_at: Optional[datetime] = None
    previous_state: Optional[Dict[str, Any]] = None


class CandidateRegistry:
    NS = "template_candidate"
    IDX = "_template_candidate_index.json"

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self.provider = LocalJSONPersistenceProvider(store_dir)

    # -- index helpers -------------------------------------------------------

    def _idx_path(self) -> str:
        return os.path.join(self.store_dir, self.IDX)

    def _load_idx(self) -> Dict[str, Dict[str, Any]]:
        import json
        path = self._idx_path()
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_idx(self, idx: Dict[str, Dict[str, Any]]) -> None:
        import json
        with open(self._idx_path(), "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2)

    def _index_entry(self, c: TemplateCandidate) -> Dict[str, Any]:
        return {
            "id": str(c.id),
            "parent_id": str(c.parent_id),
            "status": c.status,
            "created_at": c.created_at.isoformat(),
            "observations": sum(int(ev.get("observations", 0)) for ev in c.lesson_evidence),
        }

    # -- CRUD ---------------------------------------------------------------

    def save(self, candidate: TemplateCandidate) -> None:
        self.provider.save(self.NS, str(candidate.id), candidate.model_dump(mode="json"))
        idx = self._load_idx()
        idx[str(candidate.id)] = self._index_entry(candidate)
        self._save_idx(idx)

    def get(self, candidate_id: UUID) -> Optional[TemplateCandidate]:
        data = self.provider.load(self.NS, str(candidate_id))
        if not data:
            return None
        return TemplateCandidate.model_validate(data)

    def list(self, status: Optional[str] = None) -> List[TemplateCandidate]:
        out: List[TemplateCandidate] = []
        for key in self.provider.list_keys(self.NS):
            data = self.provider.load(self.NS, key)
            if not data:
                continue
            c = TemplateCandidate.model_validate(data)
            if status is None or c.status == status:
                out.append(c)
        out.sort(key=lambda c: c.created_at)
        return out

    def update_status(
        self,
        candidate_id: UUID,
        status: str,
        *,
        committed_at: Optional[datetime] = None,
    ) -> TemplateCandidate:
        c = self.get(candidate_id)
        if c is None:
            raise KeyError(f"No candidate {candidate_id}")
        c.status = status  # type: ignore[assignment]
        if committed_at is not None:
            c.committed_at = committed_at
        self.provider.save(self.NS, str(c.id), c.model_dump(mode="json"))
        idx = self._load_idx()
        idx[str(c.id)] = self._index_entry(c)
        self._save_idx(idx)
        return c
