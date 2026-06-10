"""Structured telemetry helpers for replay reliability components."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReliabilityTelemetryEvent(BaseModel):
    """JSON event that can be wrapped as a MutationLedger payload."""

    schema: str = "browsermind.replay_reliability.telemetry.v1"
    component: str
    event_type: str
    phase: str
    entity_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    data: Dict[str, Any] = Field(default_factory=dict)

    def to_mutation_payload(self, *, actor: Optional[str] = None) -> Dict[str, Any]:
        """Return a payload accepted by MutationLedger's EntityMutated listener."""
        return {
            "entity_type": "ReplayReliabilityTelemetry",
            "entity_id": self.entity_id,
            "old_value": None,
            "new_value": self.model_dump(mode="json"),
            "actor": actor or self.component,
        }


def telemetry_event(
    *,
    component: str,
    event_type: str,
    phase: str,
    data: Optional[Dict[str, Any]] = None,
    entity_id: Optional[UUID] = None,
) -> ReliabilityTelemetryEvent:
    return ReliabilityTelemetryEvent(
        component=component,
        event_type=event_type,
        phase=phase,
        entity_id=entity_id or uuid4(),
        data=data or {},
    )
