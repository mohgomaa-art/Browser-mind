"""
Experiment Sites — WR-X.5 Unification: thin adapter over EnvironmentRegistry.

DO NOT add site data here. Add new environments to:
    browsermind_core/runtime/environment_registry.py

This module derives EXPERIMENT_SITES, GATE_SITES, get_site(), and site_keys()
from the registry. All existing consumers of this module continue to work
unchanged (backward compatible).
"""
from __future__ import annotations

from dataclasses import dataclass

from browsermind_core.runtime.environment_registry import (
    get_benchmark_sites,
    get_gate_sites,
    resolve,
    EnvironmentEntry,
)


@dataclass(frozen=True)
class ExperimentSite:
    """
    Thin view over EnvironmentEntry for use in the experiments layer.
    Shape is preserved for backward compatibility with all existing scripts.
    """
    key: str
    label: str
    suggested_workflow: str
    operator_hint: str
    phase: str = "validation"


def _to_experiment_site(e: EnvironmentEntry) -> ExperimentSite:
    b = e.benchmark  # guaranteed non-None for benchmark sites
    return ExperimentSite(
        key=e.key,
        label=b.label,
        suggested_workflow=b.suggested_workflow,
        operator_hint=b.operator_hint,
        phase=b.phase,
    )


# Derived from registry — order follows registry insertion order.
EXPERIMENT_SITES: tuple[ExperimentSite, ...] = tuple(
    _to_experiment_site(e) for e in get_benchmark_sites()
)

# Resolution-rate gate sites — derived from registry BenchmarkMeta.is_gate
GATE_SITES: tuple[str, ...] = tuple(get_gate_sites())
GATE_MIN_RESOLUTION: float = 0.80


def site_keys() -> list[str]:
    return [site.key for site in EXPERIMENT_SITES]


def get_site(key: str) -> ExperimentSite:
    normalized = key.strip().lower()
    for site in EXPERIMENT_SITES:
        if site.key == normalized:
            return site
    raise KeyError(f"Unknown experiment site: {key!r}")
