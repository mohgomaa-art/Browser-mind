"""CapabilityRecord — first-class capability object keyed by structural hash.

This is the architectural inversion: a capability is a named, transferable,
boundary-scoped unit of behaviour, identified by the content-addressed hash
of its invariant intent set rather than by a human-assigned string label.

Key invariant
─────────────
Two executions on different environments that produce the same frozenset of
invariant intents (from InvariantCompiler) share the same invariant_hash and
therefore refer to the same CapabilityRecord. Human names (human_name) are
optional annotations, not identity keys.

Lifecycle
─────────
  CANDIDATE    → compiled from a single execution (InvariantGraph present)
  STRONG       → rediscovered across ≥2 environments
  VALIDATED    → transfer test passed (contract_verified_ratio ≥ threshold)
  DEPRECATED   → boundaries or failure evidence disqualifies it

Storage path: ~/.browsermind/memory/<persona_id>/capabilities/<hash16>.json
  (cross-environment; unlike ProceduralRecord which is per-environment)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CapabilityRecord:
    """A capability identified by structural hash of its invariant intent set.

    Fields
    ──────
    invariant_hash      16-char hex prefix of SHA-256(sorted invariants joined
                        by '|'). Primary identity key — never changes once set.
    invariants          Sorted list of invariant intent strings (support == 1.0)
                        from the InvariantGraph that produced this record.
    promotion_tier      Current maturity: CANDIDATE, STRONG, VALIDATED, DEPRECATED.
    transfer_envs       Set of environment keys where this capability was confirmed.
    known_boundaries    List of CapabilityBoundary.to_dict() entries. Failure modes
                        that constrain where this capability can be applied.
    strategy_counts     Per-strategy success/failure aggregates across all envs.
                        Shape: {"strategy_name": {"success": N, "failure": M}}.
    source_templates    Workflow template IDs that produced this capability.
    contract_verified_ratio  Latest measured ratio of contract-verified executions.
    human_name          Optional annotation. Not used as identity key.
    source              How this record was first created: "compilation" (from
                        _compile_and_promote) or "affordance_discovery".
    first_seen          UTC timestamp of first creation.
    last_seen           UTC timestamp of last update.
    """
    invariant_hash: str
    invariants: List[str]
    promotion_tier: str = "CANDIDATE"
    transfer_envs: List[str] = field(default_factory=list)
    known_boundaries: List[Dict[str, Any]] = field(default_factory=list)
    strategy_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    source_templates: List[str] = field(default_factory=list)
    contract_verified_ratio: Optional[float] = None
    human_name: Optional[str] = None
    source: str = "compilation"
    # Reward Layer 4: cumulative successful reuse count across all environments
    reuse_count: int = 0
    # Reward Layer 3: True if this capability was not in the hardcoded taxonomy at discovery
    is_novel: Optional[bool] = None
    first_seen: datetime = field(default_factory=_utc_now)
    last_seen: datetime = field(default_factory=_utc_now)

    # Semantic pre/post conditions (SemanticState.to_dict() entries)
    requires_states: List[Dict[str, Any]] = field(default_factory=list)
    produces_states: List[Dict[str, Any]] = field(default_factory=list)
    # Per-environment evidence of observed (pre → post) transitions
    # Shape: {env_key: [[pre_dict, post_dict], ...]} capped at 20 per env
    transition_evidence: Dict[str, List[List[Dict[str, Any]]]] = field(default_factory=dict)

    def record_transfer(self, env_key: str) -> None:
        """Register that this capability was observed on env_key."""
        if env_key and env_key not in self.transfer_envs:
            self.transfer_envs.append(env_key)
        self.last_seen = _utc_now()
        if len(self.transfer_envs) >= 2 and self.promotion_tier == "CANDIDATE":
            self.promotion_tier = "STRONG"

    def record_strategy_outcome(self, strategy: str, success: bool) -> None:
        if strategy not in self.strategy_counts:
            self.strategy_counts[strategy] = {"success": 0, "failure": 0}
        key = "success" if success else "failure"
        self.strategy_counts[strategy][key] += 1
        self.last_seen = _utc_now()

    def record_reuse(self, env_key: str = "") -> None:
        """Increment reuse count and update transfer_envs. Called on verified reuse."""
        self.reuse_count += 1
        self.record_transfer(env_key)  # also updates tier if ≥2 envs

    def record_validation(self, ratio: float) -> None:
        self.contract_verified_ratio = round(ratio, 4)
        if ratio >= 0.80 and self.promotion_tier in ("CANDIDATE", "STRONG"):
            self.promotion_tier = "VALIDATED"
        self.last_seen = _utc_now()

    def record_transition(self, pre_state: Dict[str, Any], post_state: Dict[str, Any], env_key: str) -> None:
        """Record an observed (pre → post) semantic state transition for this capability."""
        if env_key not in self.transition_evidence:
            self.transition_evidence[env_key] = []
        self.transition_evidence[env_key].append([pre_state, post_state])
        # Cap at 20 observations per environment to control file size
        self.transition_evidence[env_key] = self.transition_evidence[env_key][-20:]
        self._merge_state(self.requires_states, pre_state)
        self._merge_state(self.produces_states, post_state)
        self.last_seen = _utc_now()

    def _merge_state(self, state_list: List[Dict[str, Any]], state: Dict[str, Any]) -> None:
        """Add state to list if its fingerprint is not already represented."""
        fp = f"{state.get('auth_level', 'unknown')}:{state.get('page_context', 'unknown')}"
        if not any(
            f"{s.get('auth_level')}:{s.get('page_context')}" == fp
            for s in state_list
        ):
            state_list.append(state)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["first_seen"] = self.first_seen.isoformat()
        d["last_seen"] = self.last_seen.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityRecord":
        d = dict(d)
        for ts_field in ("first_seen", "last_seen"):
            if isinstance(d.get(ts_field), str):
                d[ts_field] = datetime.fromisoformat(d[ts_field])
        d.setdefault("transfer_envs", [])
        d.setdefault("known_boundaries", [])
        d.setdefault("strategy_counts", {})
        d.setdefault("source_templates", [])
        d.setdefault("contract_verified_ratio", None)
        d.setdefault("human_name", None)
        d.setdefault("source", "compilation")
        d.setdefault("reuse_count", 0)
        d.setdefault("is_novel", None)
        d.setdefault("requires_states", [])
        d.setdefault("produces_states", [])
        d.setdefault("transition_evidence", {})
        # Drop unknown keys for forward-compatibility
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)
