"""Persist DemonstrationSession under ~/.browsermind/demonstrations/."""
from __future__ import annotations

import json
import os
from typing import List, Optional
from uuid import UUID

from browsermind_core.recorder.demonstration_session import DemonstrationSession
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


class DemonstrationRepository:
    NS = "demonstration"
    INDEX_KEY = "_demonstration_index"
    ACTIVE_KEY = "_active_session"

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        self.demonstrations_dir = os.path.join(store_dir, "demonstrations")
        os.makedirs(self.demonstrations_dir, exist_ok=True)
        self.provider = LocalJSONPersistenceProvider(store_dir)

    def save(self, session: DemonstrationSession):
        self.provider.save(self.NS, str(session.id), session.model_dump(mode="json"))
        idx = self._load_index()
        idx[str(session.id)] = {
            "id": str(session.id),
            "family": session.environment_family,
            "instance": session.environment_instance[:80],
            "persona": session.persona_name,
            "status": session.status,
            "actions": len(session.actions),
            "started_at": session.started_at.isoformat(),
        }
        self._save_index(idx)

    def load(self, session_id: UUID) -> Optional[DemonstrationSession]:
        data = self.provider.load(self.NS, str(session_id))
        if not data:
            return None
        return DemonstrationSession.model_validate(data)

    def list_sessions(self, n: int = 50) -> List[dict]:
        idx = self._load_index()
        rows = list(idx.values())
        rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return rows[:n]

    def set_active(self, session_id: UUID):
        self.provider.save(
            self.NS,
            self.ACTIVE_KEY,
            {"session_id": str(session_id)},
        )

    def get_active(self) -> Optional[UUID]:
        data = self.provider.load(self.NS, self.ACTIVE_KEY)
        if not data:
            return None
        return UUID(data["session_id"])

    def clear_active(self):
        self.provider.save(self.NS, self.ACTIVE_KEY, {})

    def _load_index(self) -> dict:
        data = self.provider.load(self.NS, self.INDEX_KEY)
        return data.get("sessions", {}) if data else {}

    def _save_index(self, sessions: dict):
        self.provider.save(self.NS, self.INDEX_KEY, {"sessions": sessions})
