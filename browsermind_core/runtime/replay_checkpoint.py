"""
replay_checkpoint.py — Mid-run checkpoint serialization for ReplayEngine.

Allows a replay to be suspended and resumed from an exact step index with
the full attribution history preserved. Checkpoints are atomic writes to
{store_dir}/checkpoints/{workflow_id}.json.

Resume flow:
    checkpoint = ReplayCheckpoint.load(store_dir, workflow_id)
    if checkpoint:
        report = await engine.replay(
            site, template, instance,
            start_step_index=checkpoint.next_step,
            is_resume=True,
        )
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReplayCheckpoint:
    """
    Serialisable mid-run state for a ReplayEngine run.

    Fields:
        workflow_id:      WorkflowInstance.id (str)
        template_name:    WorkflowTemplate.name — for human identification
        next_step:        0-based index of the NEXT step to execute on resume
        completed_steps:  Number of steps that succeeded before suspension
        attribution_so_far: Serialised FailureAttribution list up to this point
        environment_key:  env_key string for logging
        suspended_at:     ISO timestamp of suspension
        reason:           Why we suspended (e.g. "bot_wall", "resource_missing")
    """
    workflow_id: str
    template_name: str
    next_step: int
    completed_steps: int
    attribution_so_far: List[Dict[str, Any]] = field(default_factory=list)
    environment_key: str = ""
    suspended_at: str = field(default_factory=_utc_now)
    reason: str = ""

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def _checkpoint_path(cls, store_dir: str, workflow_id: str) -> Path:
        return Path(store_dir) / "checkpoints" / f"{workflow_id}.json"

    def save(self, store_dir: str) -> None:
        path = self._checkpoint_path(store_dir, self.workflow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "workflow_id":        self.workflow_id,
            "template_name":      self.template_name,
            "next_step":          self.next_step,
            "completed_steps":    self.completed_steps,
            "attribution_so_far": self.attribution_so_far,
            "environment_key":    self.environment_key,
            "suspended_at":       self.suspended_at,
            "reason":             self.reason,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, store_dir: str, workflow_id: str) -> Optional["ReplayCheckpoint"]:
        """Load a checkpoint if one exists. Returns None if not found."""
        path = cls._checkpoint_path(store_dir, str(workflow_id))
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                workflow_id=data["workflow_id"],
                template_name=data.get("template_name", ""),
                next_step=int(data.get("next_step", 0)),
                completed_steps=int(data.get("completed_steps", 0)),
                attribution_so_far=data.get("attribution_so_far", []),
                environment_key=data.get("environment_key", ""),
                suspended_at=data.get("suspended_at", ""),
                reason=data.get("reason", ""),
            )
        except Exception:
            return None

    @classmethod
    def delete(cls, store_dir: str, workflow_id: str) -> None:
        """Remove a checkpoint once the run completes successfully."""
        path = cls._checkpoint_path(store_dir, str(workflow_id))
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    @classmethod
    def list_pending(cls, store_dir: str) -> List["ReplayCheckpoint"]:
        """Return all checkpoints that have not been deleted."""
        cp_dir = Path(store_dir) / "checkpoints"
        if not cp_dir.exists():
            return []
        results = []
        for f in cp_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(cls(
                    workflow_id=data["workflow_id"],
                    template_name=data.get("template_name", ""),
                    next_step=int(data.get("next_step", 0)),
                    completed_steps=int(data.get("completed_steps", 0)),
                    attribution_so_far=data.get("attribution_so_far", []),
                    environment_key=data.get("environment_key", ""),
                    suspended_at=data.get("suspended_at", ""),
                    reason=data.get("reason", ""),
                ))
            except Exception:
                continue
        results.sort(key=lambda c: c.suspended_at, reverse=True)
        return results
