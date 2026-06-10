"""
MemoryReader — P4: Reads strategy priors before Resolver runs.

Called from target_resolver.py as the first lookup before Depth 0.

CRITICAL: Returns priors as ranking weights, NOT as an override.
The Resolver uses these to sort its strategy list — it still runs
the full resolution chain. If the top-prior strategy fails, the
Resolver continues to the next one normally.

Minimum observations threshold (MIN_OBSERVATIONS):
  Priors are only returned if there are at least this many observations.
  Below threshold: returns empty dict (Resolver runs unguided, same as before P4).
"""
from __future__ import annotations

from typing import Dict, Optional

from browsermind_core.memory.memory_store import MemoryStore

# Only return priors if we have enough observations to trust them
MIN_OBSERVATIONS = 3

class MemoryReader:
    """
    Reads procedural and semantic memory for the Resolver and Discoverer.
    """

    def __init__(self, store: Optional[MemoryStore] = None, persona_id: str = "default"):
        self.store = store or MemoryStore(persona_id=persona_id)

    def get_strategy_priors(
        self,
        environment_key: str,
        intent_family: str,
        capability_hint: str,
        step_action: str,
    ) -> Dict[str, float]:
        """
        Returns strategy ranking weights for this (env, intent, capability, action).

        Returns {} if:
          - No history exists (env/combo never seen before)
          - Fewer than MIN_OBSERVATIONS total observations (not enough data to trust)

        Returns dict like: {"capability_intent": 0.85, "primary_semantic": 0.10, ...}
        Resolver uses this to sort its candidate strategies before trying them.
        """
        try:
            record = self.store.get_procedural(
                env_key=environment_key,
                intent_family=intent_family,
                capability_hint=capability_hint,
                step_action=step_action,
            )
        except Exception:
            return {}

        if record is None:
            return {}

        if record.total_observations < MIN_OBSERVATIONS:
            return {}

        return record.strategy_priors

    def get_semantic_fact(
        self,
        environment_key: str,
        concept: str,
    ) -> Optional[str]:
        """
        Returns the value for a structured semantic fact, or None.
        Example: get_semantic_fact("brave_search", "search_input_type") -> "textarea"
        """
        try:
            fact = self.store.get_semantic(environment_key, concept)
            if fact and fact.confidence >= 0.5:
                return fact.value
        except Exception:
            pass
        return None

    def get_all_semantic_facts(
        self,
        environment_key: str,
    ) -> Dict[str, str]:
        """
        Returns all known semantic facts for an environment as {concept: value}.
        Only includes facts with confidence >= 0.5.
        """
        try:
            all_facts = self.store.get_all_semantic(environment_key)
            return {
                concept: fact.value
                for concept, fact in all_facts.items()
                if fact.confidence >= 0.5
            }
        except Exception:
            return {}

    def has_memory(self, environment_key: str) -> bool:
        """Quick check: do we have any memory for this environment?"""
        try:
            episodes_path = self.store._env_dir(environment_key) / "episodes.jsonl"
            return episodes_path.exists() and episodes_path.stat().st_size > 0
        except Exception:
            return False
