"""Ground-truth annotation schema for replay resolution correctness."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from browsermind_core.experiments.reliability_telemetry import telemetry_event


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().lower()


class GroundTruthAnnotation(BaseModel):
    """One human-labeled intended target."""

    model_config = ConfigDict(extra="allow")

    annotation_id: str
    site: str
    step_seq: int = Field(ge=1)
    true_role: str
    true_name: str
    true_container: str = ""
    true_target: str
    template_name: Optional[str] = None
    workflow_id: Optional[UUID] = None
    page_url: str = ""
    annotated_by: str = ""
    annotated_at: datetime = Field(default_factory=utc_now)

    @field_validator("annotation_id", "site", "true_role", "true_name", "true_target")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("ground truth field cannot be blank")
        return value

    def matches_resolution(self, actual: Dict[str, Any]) -> bool:
        """Compare a resolver selection against the human-labeled target."""
        actual_role = actual.get("role") or actual.get("resolved_role") or actual.get("expected_role")
        actual_name = actual.get("name") or actual.get("resolved_name") or actual.get("expected_name")
        actual_container = (
            actual.get("container")
            or actual.get("resolved_container")
            or actual.get("container_label")
            or actual.get("nearest_container_label")
        )
        actual_target = (
            actual.get("target")
            or actual.get("resolved_target")
            or actual.get("selector")
            or actual.get("target_selector")
        )

        role_ok = _norm(actual_role) == _norm(self.true_role)
        name_ok = _norm(actual_name) == _norm(self.true_name)
        container_ok = True if not self.true_container else _norm(actual_container) == _norm(self.true_container)
        target_ok = _norm(actual_target) == _norm(self.true_target)
        return role_ok and name_ok and container_ok and target_ok

    def telemetry(self) -> Dict[str, Any]:
        return telemetry_event(
            component="ground_truth",
            event_type="annotation_loaded",
            phase="phase1_measurement",
            data={
                "annotation_id": self.annotation_id,
                "site": self.site,
                "step_seq": self.step_seq,
                "true_role": self.true_role,
                "true_name": self.true_name,
                "true_container": self.true_container,
                "true_target": self.true_target,
            },
        ).to_mutation_payload()


class GroundTruthDataset(BaseModel):
    """Exactly 100 independently annotated replay targets."""

    schema: str = "browsermind.replay_ground_truth.v1"
    dataset_id: str
    required_size: int = 100
    annotations: List[GroundTruthAnnotation]
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_dataset(self) -> "GroundTruthDataset":
        if len(self.annotations) != self.required_size:
            raise ValueError(
                f"ground truth dataset must contain exactly {self.required_size} annotations; "
                f"got {len(self.annotations)}"
            )
        seen = set()
        for item in self.annotations:
            key = (
                item.site,
                str(item.workflow_id or ""),
                item.template_name or "",
                item.step_seq,
                item.annotation_id,
            )
            if key in seen:
                raise ValueError(f"duplicate ground truth annotation: {item.annotation_id}")
            seen.add(key)
        return self

    def find(
        self,
        *,
        site: str,
        step_seq: int,
        workflow_id: Optional[UUID] = None,
        template_name: Optional[str] = None,
    ) -> Optional[GroundTruthAnnotation]:
        site_norm = _norm(site)
        template_norm = _norm(template_name)
        for item in self.annotations:
            if _norm(item.site) != site_norm or item.step_seq != step_seq:
                continue
            if workflow_id and item.workflow_id and item.workflow_id != workflow_id:
                continue
            if template_name and item.template_name and _norm(item.template_name) != template_norm:
                continue
            return item
        return None

    def telemetry(self) -> Dict[str, Any]:
        return telemetry_event(
            component="ground_truth",
            event_type="dataset_loaded",
            phase="phase1_measurement",
            data={
                "dataset_id": self.dataset_id,
                "annotation_count": len(self.annotations),
                "required_size": self.required_size,
            },
        ).to_mutation_payload()
