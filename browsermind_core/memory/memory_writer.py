"""
MemoryWriter — P4: Writes memory after each step/replay.

Called from:
  - replay_engine.py: after each successful step -> write_step_outcome()
  - harness.py: after each PASS replay -> write_replay_summary()

Also derives SemanticFacts from Capability/Affordance discovery signals
when they reveal something non-obvious about the environment's structure.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from browsermind_core.memory.episode import EpisodeRecord
from browsermind_core.memory.procedural import ProceduralRecord
from browsermind_core.memory.semantic import (
    SemanticFact,
    CONCEPT_SEARCH_INPUT_TYPE,
    CONCEPT_SEARCH_INTERFACE,
    CONCEPT_SUBMIT_METHOD,
)
from browsermind_core.memory.memory_store import MemoryStore

if TYPE_CHECKING:
    from browsermind_core.experiments.replay_result import ReplayResult


class MemoryWriter:
    """
    Writes to all three memory layers.
    Instantiated once per harness/engine session.
    """

    def __init__(self, store: Optional[MemoryStore] = None, persona_id: str = "default"):
        self.store = store or MemoryStore(persona_id=persona_id)

    def write_step_outcome(
        self,
        environment_key: str,
        step_action: str,
        capability_hint: str,
        intent_family: str,
        resolution_strategy: str,
        outcome: str,                    # "success" | "failure"
        timing_ms: Optional[int] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        """
        Called after each step in ReplayEngine.
        Writes an EpisodeRecord and updates the ProceduralRecord priors.
        """
        if not environment_key or not resolution_strategy:
            return

        # P4A: Episode (append-only)
        episode = EpisodeRecord(
            environment_key=environment_key,
            step_action=step_action,
            capability_hint=capability_hint or "unknown",
            intent_family=intent_family or "UNKNOWN",
            resolution_strategy=resolution_strategy,
            outcome=outcome,
            timing_ms=timing_ms,
            failure_reason=failure_reason,
        )
        try:
            self.store.append_episode(episode)
        except Exception:
            pass  # Memory write failure must never crash replay

        # P4B: Procedural priors update
        proc = ProceduralRecord(
            environment_key=environment_key,
            intent_family=intent_family or "UNKNOWN",
            capability_hint=capability_hint or "unknown",
            step_action=step_action,
            strategy_counts={
                resolution_strategy: {
                    "success": 1 if outcome == "success" else 0,
                    "failure": 0 if outcome == "success" else 1,
                }
            },
        )
        try:
            self.store.update_procedural(proc)
        except Exception:
            pass

    def write_semantic_fact(
        self,
        environment_key: str,
        concept: str,
        value: str,
        evidence: str = "",
        confidence: float = 0.9,
    ) -> None:
        """
        Called when Capability/Affordance discovery reveals a structured
        environment fact (e.g. search box is textarea, not input).
        """
        fact = SemanticFact(
            environment_key=environment_key,
            concept=concept,
            value=value,
            confidence=confidence,
            evidence=evidence,
        )
        try:
            self.store.update_semantic(fact)
        except Exception:
            pass

    def infer_semantic_facts_from_step(
        self,
        environment_key: str,
        step_action: str,
        capability_hint: str,
        resolution_strategy: str,
        descriptor: Optional[dict] = None,
    ) -> None:
        """
        Derive SemanticFacts from step resolution signals.
        Called alongside write_step_outcome when signals are present.
        """
        if not descriptor:
            return

        # Infer search_input_type from selector used
        target_sel = descriptor.get("target_selector", "")
        if step_action == "fill" and capability_hint == "search_query_input":
            if "textarea" in target_sel:
                self.write_semantic_fact(
                    environment_key,
                    CONCEPT_SEARCH_INPUT_TYPE,
                    "textarea",
                    evidence=f"selector: {target_sel}",
                )
            elif "input" in target_sel:
                self.write_semantic_fact(
                    environment_key,
                    CONCEPT_SEARCH_INPUT_TYPE,
                    "input",
                    evidence=f"selector: {target_sel}",
                )

        # Infer submit_method from submit resolution
        if step_action == "submit" and capability_hint in ("form_submit", "search_submit"):
            if resolution_strategy == "capability_intent":
                # capability_intent on submit = Enter key path
                self.write_semantic_fact(
                    environment_key,
                    CONCEPT_SUBMIT_METHOD,
                    "enter",
                    evidence=f"resolved by {resolution_strategy}",
                )
