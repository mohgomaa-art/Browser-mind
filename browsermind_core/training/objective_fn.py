"""Objective Function — per-execution Task Value Score.

Scores every execution on 5 dimensions and produces a weighted aggregate.
Integrates into dataset selection: episodes below a threshold are excluded
from BC training so the model learns from high-value demonstrations only.

All five components are bounded [0, 1].  Default weights are equal (0.2
each).  No side-effects; pure functions of ledger data + a CorpusStats object
built once per training run.

Components
----------
transferability        How broadly the workflow_class appears across
                       environments in the corpus.  Higher = more general.
workflow_depth         Normalised step count.  Deeper = more complex.
resource_acquisition_value
                       Fraction of steps that resolved via vault.
                       Higher = learned a vault-dependent skill.
capability_rarity      Inverse-frequency of the workflow_class.
                       Rare workflow classes receive higher weight.
success_outcome        Fraction of steps that succeeded.
                       Penalises executions that mostly fail.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskValueScore:
    transferability: float
    workflow_depth: float
    resource_acquisition_value: float
    capability_rarity: float
    success_outcome: float
    weights: List[float] = field(default_factory=lambda: [0.2, 0.2, 0.2, 0.2, 0.2])

    @property
    def aggregate(self) -> float:
        components = [
            self.transferability,
            self.workflow_depth,
            self.resource_acquisition_value,
            self.capability_rarity,
            self.success_outcome,
        ]
        return sum(w * c for w, c in zip(self.weights, components))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "transferability": round(self.transferability, 4),
            "workflow_depth": round(self.workflow_depth, 4),
            "resource_acquisition_value": round(self.resource_acquisition_value, 4),
            "capability_rarity": round(self.capability_rarity, 4),
            "success_outcome": round(self.success_outcome, 4),
            "aggregate": round(self.aggregate, 4),
        }


@dataclass
class CorpusStats:
    """Pre-computed corpus-level statistics needed to score executions.

    Build once from the full ledger before scoring individual executions.

    Attributes
    ----------
    workflow_class_env_count  : {workflow_class: set of environment_instance}
    workflow_class_exec_count : {workflow_class: number of executions}
    total_envs                : total distinct environments in corpus
    """
    workflow_class_env_count: Dict[str, set] = field(default_factory=dict)
    workflow_class_exec_count: Dict[str, int] = field(default_factory=dict)
    total_envs: int = 0

    @classmethod
    def from_episodes(cls, episodes: List[Dict[str, Any]]) -> "CorpusStats":
        """Build from a list of BC episode dicts (from episode_extractor)."""
        from browsermind_core.ledger.cascade import workflow_class_for

        stats = cls()
        env_set: set = set()

        for ep in episodes:
            site = ep.get("site") or ""
            template_id = ep.get("template_id") or ""
            wc = workflow_class_for(template_name=template_id, environment_instance=site)
            exec_id = ep.get("execution_id") or ""

            if site:
                env_set.add(site)
            if wc not in stats.workflow_class_env_count:
                stats.workflow_class_env_count[wc] = set()
            if site:
                stats.workflow_class_env_count[wc].add(site)

            # count distinct executions per class
            if exec_id:
                stats.workflow_class_exec_count.setdefault(wc, 0)

        # second pass: count distinct executions per workflow class
        exec_by_class: Dict[str, set] = {}
        for ep in episodes:
            site = ep.get("site") or ""
            template_id = ep.get("template_id") or ""
            exec_id = ep.get("execution_id") or ""
            if not exec_id:
                continue
            wc = workflow_class_for(template_name=template_id, environment_instance=site)
            exec_by_class.setdefault(wc, set()).add(exec_id)

        for wc, ids in exec_by_class.items():
            stats.workflow_class_exec_count[wc] = len(ids)

        stats.total_envs = max(1, len(env_set))
        return stats


def score_execution(
    step_records: List[Dict[str, Any]],
    corpus_stats: CorpusStats,
    *,
    weights: Optional[List[float]] = None,
    depth_norm: int = 15,
) -> TaskValueScore:
    """Compute a TaskValueScore from a list of step-level episode dicts.

    Parameters
    ----------
    step_records   : episode dicts from episode_extractor for one execution_id
    corpus_stats   : pre-built CorpusStats from the full ledger
    weights        : optional override [t, wd, rav, cr, so]; must sum to 1.0
    depth_norm     : step count at which workflow_depth saturates to 1.0
    """
    if weights is None:
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]

    if not step_records:
        return TaskValueScore(0.0, 0.0, 0.0, 0.0, 0.0, weights=weights)

    from browsermind_core.ledger.cascade import workflow_class_for

    total = len(step_records)
    first = step_records[0]
    site = first.get("site") or ""
    template_id = first.get("template_id") or ""
    wc = workflow_class_for(template_name=template_id, environment_instance=site)

    # transferability: distinct envs where wc appears / total corpus envs
    wc_envs = len(corpus_stats.workflow_class_env_count.get(wc, set()))
    transferability = min(1.0, wc_envs / corpus_stats.total_envs)

    # workflow_depth: step count normalised by depth_norm
    workflow_depth = min(1.0, total / max(1, depth_norm))

    # resource_acquisition_value: vault steps / total steps
    vault_steps = sum(
        1 for r in step_records
        if r.get("resolution_strategy") in ("vault", "env_secrets", "env_resources", "generic_vault")
        or r.get("vault_resolution_path") is not None
    )
    resource_acquisition_value = vault_steps / total

    # capability_rarity: inverse frequency of workflow_class in corpus
    exec_count = corpus_stats.workflow_class_exec_count.get(wc, 0)
    capability_rarity = 1.0 / (1.0 + math.log(1 + exec_count))

    # success_outcome: successful steps / total
    success_steps = sum(1 for r in step_records if r.get("label", 0) == 1)
    success_outcome = success_steps / total

    return TaskValueScore(
        transferability=transferability,
        workflow_depth=workflow_depth,
        resource_acquisition_value=resource_acquisition_value,
        capability_rarity=capability_rarity,
        success_outcome=success_outcome,
        weights=weights,
    )


def score_all_executions(
    episodes: List[Dict[str, Any]],
    corpus_stats: CorpusStats,
    *,
    weights: Optional[List[float]] = None,
) -> Dict[str, TaskValueScore]:
    """Score every execution_id in `episodes`.  Returns {execution_id: score}."""
    from collections import defaultdict

    by_exec: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ep in episodes:
        eid = ep.get("execution_id") or "__none__"
        by_exec[eid].append(ep)

    return {
        eid: score_execution(recs, corpus_stats, weights=weights)
        for eid, recs in by_exec.items()
    }
