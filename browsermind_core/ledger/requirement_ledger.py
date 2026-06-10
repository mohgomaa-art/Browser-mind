# browsermind_core/ledger/requirement_ledger.py
"""Requirement Ledger — records confirmed or refuted requirement dependencies during execution."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class RequirementRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    goal: str
    requirement: str
    confirmed: bool
    evidence: str = ""
    environment: str = ""


class RequirementLedger:
    """Requirement Ledger tracks candidate requirements, compiling empirical evidence to confirm or refute them."""

    def __init__(self):
        self.records: list[RequirementRecord] = []

    def record(self, record: RequirementRecord) -> RequirementRecord:
        self.records.append(record)
        return record

    def get_summary(self) -> dict:
        """Returns a summary of Confirmed vs Refuted counts for each requirement type."""
        summary = {}
        for r in self.records:
            req = r.requirement
            if req not in summary:
                summary[req] = {"confirmed": 0, "refuted": 0}
            if r.confirmed:
                summary[req]["confirmed"] += 1
            else:
                summary[req]["refuted"] += 1
        return summary
