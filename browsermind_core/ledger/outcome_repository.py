"""Persistent store for OutcomeRecord (append-only)."""
from typing import List
from uuid import UUID

from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.runtime.persistence import PersistenceProvider


class OutcomeRepository:
    NS = "outcome_ledger"
    INDEX_KEY = "_outcome_index"

    def __init__(self, provider: PersistenceProvider):
        self.provider = provider

    def _load_index(self) -> List[str]:
        data = self.provider.load(self.NS, self.INDEX_KEY)
        return data.get("keys", []) if data else []

    def _save_index(self, keys: List[str]):
        self.provider.save(self.NS, self.INDEX_KEY, {"keys": keys})

    def append(self, entry: OutcomeRecord):
        key = str(entry.id)
        self.provider.save(self.NS, key, entry.model_dump(mode="json"))
        keys = self._load_index()
        keys.append(key)
        self._save_index(keys)

    def tail(self, n: int = 20) -> List[OutcomeRecord]:
        keys = self._load_index()
        records = []
        for k in keys[-n:]:
            data = self.provider.load(self.NS, k)
            if data:
                records.append(OutcomeRecord.model_validate(data))
        return records

    def count(self) -> int:
        return len(self._load_index())

    def load_all(self) -> List[OutcomeRecord]:
        n = self.count()
        return self.tail(n) if n else []

    def get_by_execution(self, execution_id: UUID) -> List[OutcomeRecord]:
        return [r for r in self.load_all() if r.execution_id == execution_id]
