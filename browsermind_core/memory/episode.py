"""
EpisodeRecord — P4A: Episodic Runtime Memory

What happened in a specific execution step.
Write-only audit log. Never modified after write.

Scope: Environment-global (not Persona-scoped until P5).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import json


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EpisodeRecord:
    """
    A single observed step outcome during replay.

    Fields are intentionally narrow:
      - enough to reconstruct what happened
      - enough to compute ProceduralRecord priors later
      - nothing that requires inference or interpretation
    """
    environment_key: str        # e.g. "github"
    step_action: str            # e.g. "fill", "submit", "keydown"
    capability_hint: str        # e.g. "search_query_input"
    intent_family: str          # e.g. "SEARCH" — the portable abstraction
    resolution_strategy: str    # e.g. "capability_intent", "primary_semantic"
    outcome: str                # "success" | "failure"
    timing_ms: Optional[int] = None   # actual step execution time
    failure_reason: Optional[str] = None
    timestamp: datetime = field(default_factory=_utc_now)

    def to_json_line(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeRecord":
        d = dict(d)
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        return cls(**d)
