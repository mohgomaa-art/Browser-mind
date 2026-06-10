"""P2B — Semantic human demonstration (Observation, Action, Result)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DemonstrationStep(BaseModel):
    seq: int
    timestamp: datetime = Field(default_factory=utc_now)
    action_type: Literal["click", "fill", "submit", "navigate", "keydown", "session"]
    url: str = ""
    target_role: str = ""       # AX role (e.g. "button", "textbox")
    target_name: str = ""       # Accessible name (e.g. "Log in")
    target_selector: str = ""   # Fallback CSS/XPath selector
    value: Optional[str] = None # DO NOT STORE RAW PASSWORDS HERE
    vault_ref: Optional[str] = None # If value is a password, store vault key here
    result_url: str = ""
    result_state: str = ""      # e.g., "success", "navigation", "error"
    screenshot_hash: str = ""
    descriptor: Dict[str, Any] = Field(default_factory=dict)
    recording_evidence: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DemonstrationSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    persona_name: str = ""
    environment_family: str = ""
    environment_instance: str = ""
    profile_path: str = ""
    start_url: str = ""
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: Optional[datetime] = None
    status: Literal["recording", "completed", "aborted"] = "recording"
    actions: List[DemonstrationStep] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def append(self, step: DemonstrationStep) -> DemonstrationStep:
        step.seq = len(self.actions) + 1
        self.actions.append(step)
        return step

    def complete(self):
        self.ended_at = utc_now()
        self.status = "completed"

    def abort(self, reason: str = ""):
        self.ended_at = utc_now()
        self.status = "aborted"
        if reason:
            self.append(
                DemonstrationStep(
                    seq=0,
                    action_type="session",
                    metadata={"reason": reason},
                )
            )
