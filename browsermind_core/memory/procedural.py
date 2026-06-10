"""
ProceduralRecord — P4B: Procedural Memory

Strategy priors per (intent_family, capability_hint).

CRITICAL DESIGN PRINCIPLE:
  This is NOT a cache. The priors are passed to the Resolver as ranking weights.
  The Resolver still runs its full decision process — memory only boosts or
  de-emphasizes strategies based on observed history.

  This means:
    - If GitHub changes its DOM, the Resolver tries all depths normally.
    - Memory merely says "capability_intent has worked 40 times here" → rank it higher.
    - A fresh environment with no memory behaves identically to before P4.

Scope: Environment-global (not Persona-scoped until P5).
Key: (environment_key, intent_family, capability_hint, step_action)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Strategies the resolver can use — must match resolver's resolved_by values
KNOWN_STRATEGIES = [
    "primary_semantic",
    "placeholder",
    "nearby_text",
    "structural_path",
    "affordance_intent",
    "capability_intent",
    "loose_semantic",
    "navigate",
]


@dataclass
class ProceduralRecord:
    """
    Aggregated strategy performance for a (intent_family, capability_hint, step_action)
    tuple, scoped to an environment.

    intent_family is the portable key: "SEARCH" transfers from DDG to GitHub.
    environment_key narrows it: GitHub's SEARCH may differ from DDG's SEARCH.

    strategy_counts: raw outcome counts per strategy
    strategy_priors: normalized probability weights (0.0–1.0, sum to 1.0)
                     computed from strategy_counts. Passed to Resolver for ranking.
    """
    environment_key: str        # e.g. "github"
    intent_family: str          # e.g. "SEARCH" — portable cross-env key
    capability_hint: str        # e.g. "search_query_input"
    step_action: str            # e.g. "fill"
    strategy_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # strategy_counts shape: {"capability_intent": {"success": 5, "failure": 1}, ...}
    last_seen: datetime = field(default_factory=_utc_now)
    # Boundary Law: known failure modes for this capability hypothesis.
    # Each entry is a CapabilityBoundary.to_dict() — stored as plain dicts to
    # avoid cross-module circular imports at the dataclass field level.
    # Shape: [{"capability_hint": str, "failure_mode": str, "failure_reason": str,
    #          "environment_pattern": str, "frequency": int, "evidence_count": int}]
    known_boundaries: List[Dict[str, Any]] = field(default_factory=list)
    # source: how this record was created — "execution" (normal path) or
    # "affordance_discovery" (seeded from AffordanceDiscoverer on novel environment).
    source: str = "execution"

    @property
    def strategy_priors(self) -> Dict[str, float]:
        """
        Compute normalized success-rate priors per strategy.
        Returns dict of {strategy: prior_weight} where weights sum to ~1.0.
        Strategies with zero successes get a small floor weight (0.01).
        """
        scores: Dict[str, float] = {}
        for strategy, counts in self.strategy_counts.items():
            s = counts.get("success", 0)
            f = counts.get("failure", 0)
            # Weight by absolute successes, penalize failures
            scores[strategy] = max(0.0, float(s - f))

        total_score = sum(scores.values())
        if total_score == 0:
            return {}

        # Normalize
        priors = {k: round(v / total_score, 4) for k, v in scores.items()}
        return priors

    @property
    def best_strategy(self) -> Optional[str]:
        """Returns the strategy with highest success rate, or None if no history."""
        priors = self.strategy_priors
        if not priors:
            return None
        return max(priors, key=lambda k: priors[k])

    @property
    def total_observations(self) -> int:
        total = 0
        for counts in self.strategy_counts.values():
            total += counts.get("success", 0) + counts.get("failure", 0)
        return total

    def record_outcome(self, strategy: str, success: bool) -> None:
        """Update counts for a strategy outcome."""
        if strategy not in self.strategy_counts:
            self.strategy_counts[strategy] = {"success": 0, "failure": 0}
        key = "success" if success else "failure"
        self.strategy_counts[strategy][key] += 1
        self.last_seen = _utc_now()

    def to_json_line(self) -> str:
        d = asdict(self)
        d["last_seen"] = self.last_seen.isoformat()
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "ProceduralRecord":
        d = dict(d)
        if isinstance(d.get("last_seen"), str):
            d["last_seen"] = datetime.fromisoformat(d["last_seen"])
        # Forward-compatibility: old records without these fields get defaults.
        d.setdefault("known_boundaries", [])
        d.setdefault("source", "execution")
        # Drop any unknown keys so old serialized records don't break __init__.
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)
