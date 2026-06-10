"""Lock Phase 1 replay baseline numbers before compiler fixes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from browsermind_core.experiments.reliability_telemetry import telemetry_event


PHASE1_ORDER = ["P8A", "P8B", "P8D", "P8E", "P8C"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_identity_sprint_baseline(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    baseline = data.get("Baseline")
    if not baseline:
        return None
    total = int(baseline.get("total_steps") or 0)
    resolved = int(baseline.get("resolved_steps") or 0)
    return {
        "source": str(path),
        "mode": "Baseline",
        "total_steps": total,
        "resolved_steps": resolved,
        "resolution_rate": baseline.get("resolution_rate", resolved / total if total else 0.0),
        "critical_path_success": baseline.get("critical_path_success"),
        "task_success_probability": baseline.get("task_success_probability"),
    }


def lock_phase1_baseline(
    *,
    identity_sprint_path: Path,
    target_changed_dossier_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    baseline = load_identity_sprint_baseline(identity_sprint_path)
    dossier = None
    if target_changed_dossier_path.exists():
        data = json.loads(target_changed_dossier_path.read_text(encoding="utf-8"))
        dossier = {
            "source": str(target_changed_dossier_path),
            "total_cases": data.get("total_cases", 0),
            "root_cause_distribution": data.get("root_cause_distribution", {}),
        }

    locked = {
        "schema": "browsermind.replay_reliability.phase1_baseline_lock.v1",
        "locked_at": utc_now().isoformat(),
        "phase_order": PHASE1_ORDER,
        "measurement_before_fixes": True,
        "asm_greenhouse_baseline": baseline,
        "target_changed_dossier": dossier,
        "required_metrics": [
            "resolution_rate",
            "false_positive_resolution_rate",
            "resolution_accuracy",
            "task_completion_rate",
            "attribution_completeness",
        ],
        "notes": [
            "FPR and resolution accuracy require a 100-element ground truth dataset.",
            "Compiler hardening is intentionally sequenced after this lock.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(locked, indent=2), encoding="utf-8")
    return locked


def baseline_lock_telemetry(locked: Dict[str, Any]) -> Dict[str, Any]:
    return telemetry_event(
        component="baseline_lock",
        event_type="phase1_baseline_locked",
        phase="phase1_measurement",
        data=locked,
    ).to_mutation_payload()
