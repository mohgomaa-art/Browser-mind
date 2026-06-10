"""Outcome Ledger — answers 'Did it work?' (see DOCS/OUTCOME_LEDGER_CONTRACT.md)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OutcomeRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scope: Literal["step", "execution", "task", "workflow_instance"]
    scope_id: UUID
    persona_id: UUID
    environment_family: str = ""
    environment_instance: str = ""

    outcome_type: str
    success: bool
    evidence: str
    evidence_uris: List[str] = Field(default_factory=list)

    execution_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    resource_ids: List[UUID] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class OutcomeLedger:
    """Append-only outcome log; optional repository for cross-session persistence."""

    def __init__(self, repository=None):
        self.repository = repository
        self.records: List[OutcomeRecord] = []
        if self.repository:
            self.records = self.repository.load_all()

    def record(self, entry: OutcomeRecord) -> OutcomeRecord:
        self.records.append(entry)
        if self.repository:
            self.repository.append(entry)
        return entry

    def list_for_execution(self, execution_id: UUID) -> List[OutcomeRecord]:
        return [r for r in self.records if r.execution_id == execution_id]

    def list_for_scope(self, scope_id: UUID) -> List[OutcomeRecord]:
        return [r for r in self.records if r.scope_id == scope_id]
