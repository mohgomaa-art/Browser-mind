"""
ledger/ledger_repository.py
Persistent, append-only log of all Mutation events.
Simple interface: append / tail / get_by_entity
"""
import json
import os
from typing import List, Optional
from uuid import UUID

from browsermind_core.ledger.mutation_ledger import LedgerEntry
from browsermind_core.runtime.persistence import PersistenceProvider


class LedgerRepository:
    NS = "ledger"
    INDEX_KEY = "_ledger_index"

    def __init__(self, provider: PersistenceProvider):
        self.provider = provider

    # -------------------------------------------------------------------------
    # Internal: monotonic index
    # -------------------------------------------------------------------------

    def _load_index(self) -> List[str]:
        data = self.provider.load(self.NS, self.INDEX_KEY)
        return data.get("keys", []) if data else []

    def _save_index(self, keys: List[str]):
        self.provider.save(self.NS, self.INDEX_KEY, {"keys": keys})

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def append(self, entry: LedgerEntry):
        key = str(entry.id)
        self.provider.save(self.NS, key, entry.model_dump(mode="json"))
        keys = self._load_index()
        keys.append(key)
        self._save_index(keys)

    def tail(self, n: int = 20) -> List[LedgerEntry]:
        keys = self._load_index()
        recent_keys = keys[-n:]
        entries = []
        for k in recent_keys:
            data = self.provider.load(self.NS, k)
            if data:
                entries.append(LedgerEntry.model_validate(data))
        return entries

    def get_by_entity(self, entity_id: UUID) -> List[LedgerEntry]:
        keys = self._load_index()
        entries = []
        for k in keys:
            data = self.provider.load(self.NS, k)
            if data and data.get("entity_id") == str(entity_id):
                entries.append(LedgerEntry.model_validate(data))
        return entries

    def count(self) -> int:
        return len(self._load_index())

    def load_all(self) -> List[LedgerEntry]:
        """All entries in append order (for session hydration)."""
        n = self.count()
        return self.tail(n) if n else []
