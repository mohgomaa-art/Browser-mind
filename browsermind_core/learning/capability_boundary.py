"""CapabilityBoundary — extracts WHERE a capability fails from step OutcomeRecords.

Implements the Boundary Law:
  A capability is incomplete until BrowserMind knows its limits.
  A failed transfer is not merely failure. It is boundary discovery.

Each CapabilityBoundary describes one failure mode for one capability hint:
  - Which capability was being exercised (capability_hint)
  - How it failed (failure_mode / failure_class)
  - What environment pattern the failure occurred on (environment_pattern)
  - How often (frequency, evidence_count)

These are extracted from step-scope OutcomeRecords where success=False and
failure_class is populated, then stored on ProceduralRecord.known_boundaries.

This is NOT the general unsupervised outcome estimator. It is the first
boundary signal available from existing causal attribution data.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class CapabilityBoundary:
    """One observed failure mode for a capability hypothesis.

    Populated from FailureAttribution.failure_class and FailureAttribution.failure_reason
    via the step OutcomeRecord's metrics dict.
    """
    capability_hint: str          # e.g. "search_query_input"
    failure_mode: str             # e.g. "TARGET_CHANGED"
    failure_reason: str           # raw reason string
    environment_pattern: str      # environment_instance where failure was observed
    frequency: int = 1            # how many times this boundary was hit
    evidence_count: int = 1       # distinct executions that contributed
    first_seen_env: str = ""      # environment_instance of first observation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapabilityBoundary":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def extract_boundaries_from_failures(
    step_records: List[Any],
    *,
    environment_instance: str = "",
) -> List[CapabilityBoundary]:
    """Extract CapabilityBoundary objects from failed step OutcomeRecords.

    Args:
        step_records: OutcomeRecord objects with scope='step'.
        environment_instance: The environment where these records originated.
            Used as the environment_pattern when the record doesn't carry one.

    Returns:
        List of CapabilityBoundary — one per (capability_hint, failure_mode) pair.
        Multiple records for the same pair are merged (frequency aggregated).
    """
    # Key: (capability_hint, failure_mode)
    boundary_map: Dict[tuple, CapabilityBoundary] = {}

    for rec in step_records:
        if getattr(rec, "success", True):
            continue  # only learn from failures
        metrics = getattr(rec, "metrics", None) or {}

        failure_class = str(metrics.get("failure_class") or "")
        if not failure_class:
            continue

        capability_hint = str(metrics.get("name") or metrics.get("capability_hint") or "")
        if not capability_hint:
            # Fall back to role as the capability signal
            capability_hint = str(metrics.get("role") or "unknown")

        failure_reason = str(metrics.get("failure_reason") or failure_class)
        env_pattern = str(
            getattr(rec, "environment_instance", None)
            or metrics.get("environment_instance", "")
            or environment_instance
            or "unknown"
        )

        key = (capability_hint, failure_class)
        if key in boundary_map:
            boundary_map[key].frequency += 1
            # evidence_count: only increment if this is from a distinct execution
            existing_exec = boundary_map[key].__dict__.get("_exec_ids", set())
            rec_exec = str(getattr(rec, "execution_id", "") or "")
            if rec_exec and rec_exec not in existing_exec:
                boundary_map[key].evidence_count += 1
                existing_exec.add(rec_exec)
                boundary_map[key].__dict__["_exec_ids"] = existing_exec
        else:
            b = CapabilityBoundary(
                capability_hint=capability_hint,
                failure_mode=failure_class,
                failure_reason=failure_reason,
                environment_pattern=env_pattern,
                frequency=1,
                evidence_count=1,
                first_seen_env=env_pattern,
            )
            rec_exec = str(getattr(rec, "execution_id", "") or "")
            b.__dict__["_exec_ids"] = {rec_exec} if rec_exec else set()
            boundary_map[key] = b

    # Strip internal tracking attribute before returning
    boundaries = list(boundary_map.values())
    for b in boundaries:
        b.__dict__.pop("_exec_ids", None)

    return sorted(boundaries, key=lambda b: (-b.frequency, b.capability_hint))


def merge_boundaries(
    existing: List[Dict[str, Any]],
    new_boundaries: List[CapabilityBoundary],
) -> List[Dict[str, Any]]:
    """Merge new CapabilityBoundary observations into an existing list of dicts.

    Existing entries are dicts (as stored on ProceduralRecord.known_boundaries).
    New observations increment frequency for matching (capability_hint, failure_mode)
    pairs, or append new entries.

    Returns updated list of dicts ready for ProceduralRecord.known_boundaries.
    """
    # Build map of existing entries
    existing_map: Dict[tuple, Dict[str, Any]] = {}
    for d in existing:
        k = (d.get("capability_hint", ""), d.get("failure_mode", ""))
        existing_map[k] = d

    for b in new_boundaries:
        key = (b.capability_hint, b.failure_mode)
        if key in existing_map:
            existing_map[key]["frequency"] = (
                existing_map[key].get("frequency", 1) + b.frequency
            )
            existing_map[key]["evidence_count"] = (
                existing_map[key].get("evidence_count", 1) + b.evidence_count
            )
        else:
            existing_map[key] = b.to_dict()

    return list(existing_map.values())
