"""Outcome Cascade — annotation only.

Stage 2 of the architecture investigation enshrines Outcome Cascade as
*vocabulary* and *telemetry*, not as execution logic. This module derives
three annotations from existing OutcomeRecord data:

  cascade_layer          int       1 = step (proximal), 2 = execution,
                                   3..N reserved for distal layers.
  cascade_workflow_class str       Coarse class shared across instances
                                   (e.g. "ats_apply", "ecommerce_checkout").
  cascade_proxy_for      str|None  When known, the distal layer this
                                   record is a proxy of. Currently None
                                   for all rows -- the slot is reserved
                                   for future distal signal ingestion.

These fields ride on `OutcomeRecord.metrics` and are pure functions of
fields already present. Removing them later is a no-op for any downstream
consumer that doesn't reference them.

EXPLICIT CONSTRAINT (Stage 2 authorization): cascade execution logic,
cascade decision making, cascade planners, and cascade-driven behavior
are NOT permitted. This module derives annotations and nothing more.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_TAXONOMY_JSON = Path(__file__).parent.parent / "data" / "cascade_taxonomy.json"

# Load taxonomy from JSON; fall back to empty dicts so the module never
# raises on import even if the file is missing (tests, partial installs).
def _load_taxonomy():
    try:
        data = json.loads(_TAXONOMY_JSON.read_text(encoding="utf-8"))
        return data.get("by_template", {}), data.get("by_environment", {})
    except Exception:
        return {}, {}

_WORKFLOW_CLASS_BY_TEMPLATE, _WORKFLOW_CLASS_BY_ENVIRONMENT = _load_taxonomy()


def workflow_class_for(template_name: str = "", environment_instance: str = "") -> str:
    """Return the cascade_workflow_class string for a (template, env) pair.

    Pure function. Falls back through:
      1. Exact template_name match
      2. Environment match
      3. "unclassified"
    """
    if template_name and template_name in _WORKFLOW_CLASS_BY_TEMPLATE:
        return _WORKFLOW_CLASS_BY_TEMPLATE[template_name]
    if environment_instance and environment_instance in _WORKFLOW_CLASS_BY_ENVIRONMENT:
        return _WORKFLOW_CLASS_BY_ENVIRONMENT[environment_instance]
    return "unclassified"


def cascade_layer_for(scope: str) -> int:
    """Return cascade_layer for an OutcomeRecord scope.

    Layer 1: step  — proximal (the action ran)
    Layer 2: execution / workflow_instance  — workflow completed
    Layers 3+: reserved (distal observations land here when ingestion exists)

    `task` is workflow-instance-equivalent for cascade purposes (a task is
    a wrapper around an execution; its outcome is at workflow-completion
    granularity).
    """
    if scope == "step":
        return 1
    if scope in ("execution", "task", "workflow_instance"):
        return 2
    # Unknown scope → 0 sentinel; keeps queries safe without inventing layers.
    return 0


def proxy_for(cascade_layer: int) -> Optional[str]:
    """Return what distal layer this record is a proxy of, when known.

    Currently None for all current layers because no distal ingestion
    exists yet. Reserved as a stable interface so future distal ingesters
    can populate it without changing the OutcomeRecord shape.
    """
    return None


def annotate(metrics: dict, *, scope: str, template_name: str = "",
             environment_instance: str = "") -> dict:
    """Add cascade annotations to a metrics dict in-place. Returns the
    same dict for caller convenience.

    Idempotent: setting a key that already has a value leaves it
    unchanged. This is important for replay-of-replay scenarios where
    a stored record might be reannotated.
    """
    if "cascade_layer" not in metrics:
        metrics["cascade_layer"] = cascade_layer_for(scope)
    if "cascade_workflow_class" not in metrics:
        metrics["cascade_workflow_class"] = workflow_class_for(
            template_name=template_name,
            environment_instance=environment_instance,
        )
    if "cascade_proxy_for" not in metrics:
        metrics["cascade_proxy_for"] = proxy_for(metrics["cascade_layer"])
    return metrics
