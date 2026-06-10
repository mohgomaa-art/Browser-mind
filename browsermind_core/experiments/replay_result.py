"""ReplayResult — canonical schema for replay validation experiments."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    # No semantic identifier of any kind — no label, no placeholder, no aria, nothing.
    NO_VISIBLE_SIGNAL = "NO_VISIBLE_SIGNAL"
    # Human-visible label exists but the DOM broke the binding (no for=, no aria-labelledby,
    # not nested). Environmental failure — the website's bug, not BrowserMind's.
    ORPHANED_SEMANTIC_SIGNAL = "ORPHANED_SEMANTIC_SIGNAL"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    TARGET_CHANGED = "TARGET_CHANGED"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    DESCRIPTOR_LOSS = "DESCRIPTOR_LOSS"
    PORTAL_CONTEXT_FAILURE = "PORTAL_CONTEXT_FAILURE"
    CONTRACT_FAILURE = "CONTRACT_FAILURE"
    FALSE_POSITIVE_RESOLUTION = "FALSE_POSITIVE_RESOLUTION"
    UNKNOWN = "UNKNOWN"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReplayResult(BaseModel):
    """One replay experiment observation.

    Primary KPI: resolution_rate (target resolution).
    Secondary: workflow_failed / replay_success (full workflow completion).
    P4E: ambiguity_rate (identity ambiguity rate).
    """

    workflow_id: UUID
    site: str
    status: Literal["SUCCESS", "FAILED", "INTERRUPTED", "BLOCKED"] = "SUCCESS"
    total_steps: int
    resolved_steps: int
    failed_steps: int
    resolution_rate: float
    # P4E: Identity Preservation
    ambiguous_steps: int = 0
    ambiguity_rate: float = 0.0
    resource_resolution_rate: float = 0.0
    recovery_rate: Optional[float] = None
    false_positive_resolution_rate: Optional[float] = None
    resolution_accuracy: Optional[float] = None
    task_completion_rate: Optional[float] = None
    task_completed: Optional[bool] = None
    reliability_metrics: dict = Field(default_factory=dict)
    workflow_failed: bool
    replay_success: bool
    failure_reason: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    failed_step: Optional[int] = None
    template_name: Optional[str] = None
    demonstration_id: Optional[UUID] = None
    # P4C: State Achievement Verification (Evidence → Inference → State)
    # Full StateInference dict, stored as JSON for portability.
    # Access inferred_state via: result.state_inference["inferred_state"]
    # Access match via:          result.state_inference["match"]
    state_inference: Optional[dict] = None
    verification_report: Optional[dict] = None
    # Verifier failures: {"type", "message", "traceback"} when StateVerifier raised.
    verification_error: Optional[dict] = None
    timestamp: datetime = Field(default_factory=utc_now)
    # Per-step resolution outcomes — enables cross-run step-level aggregation.
    # Each entry: {seq, action_type, role, name,
    #              outcome: RESOLVED_CORRECT | RESOLVED_INCORRECT |
    #                       RESOLVED_UNJUDGED | AMBIGUOUS_IDENTITY | NO_VISIBLE_SIGNAL |
    #                       ORPHANED_SEMANTIC_SIGNAL | TARGET_CHANGED | SKIPPED,
    #              candidate_count, identity_confidence, resolution_strategy,
    #              candidates_info: [...]}
    step_outcomes: list[dict] = Field(default_factory=list)
