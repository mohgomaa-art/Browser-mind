from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Dict, Any, List, Optional
from browsermind_core.runtime.event_bus import EventBus

class LedgerEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entity_type: str
    entity_id: UUID
    old_value: Optional[Dict[str, Any]]
    new_value: Dict[str, Any]
    actor: str = "system"
    evidence: Optional[str] = None
    policy: Optional[str] = None

class MutationLedger:
    """
    The immutable log of all state changes across the system.
    Optionally backed by a LedgerRepository for cross-session persistence.
    """
    def __init__(self, event_bus: EventBus, repository=None):
        self.event_bus = event_bus
        self.repository = repository  # Optional[LedgerRepository]
        self.history: List[LedgerEntry] = []
        if self.repository:
            self.history = self.repository.load_all()
        self.event_bus.subscribe("EntityMutated", self._on_entity_mutated)

    def _on_entity_mutated(self, payload: Dict[str, Any]):
        entry = LedgerEntry(
            entity_type=payload["entity_type"],
            entity_id=payload["entity_id"],
            old_value=payload.get("old_value"),
            new_value=payload["new_value"],
            actor=payload.get("actor", "system"),
            evidence=payload.get("evidence"),
            policy=payload.get("policy")
        )
        self.history.append(entry)
        if self.repository:
            self.repository.append(entry)

    def get_history(self) -> List[LedgerEntry]:
        """In-session history; hydrated from repository on startup when persisted."""
        return list(self.history)
