"""Reward Layers 1-5 — multi-layer learning signal computation.

The five layers answer progressively harder questions:

  Layer 1  Task Completed?
           Binary: did the workflow terminal state match the contract?
           Source: contract_goal_completed in OutcomeRecord.metrics

  Layer 2  Did it transfer?
           Binary: was this capability exercised on a never-seen environment?
           Source: CapabilityRecord.transfer_envs — any env outside training set

  Layer 3  Is this novel?
           Binary: does this capability_hint appear in the hardcoded taxonomy?
           A hint outside CAPABILITY_RULES = genuine discovery event.
           Source: CapabilityClassifier.CAPABILITY_RULES

  Layer 4  Is it being reused?
           Integer: how many times has this capability been successfully reused
           across executions (not just discovered)?
           Source: CapabilityRecord.reuse_count (new field, incremented by
           _verify_capabilities_in_execution when contract passes)

  Layer 5  Did future competence improve?
           Float: delta between a baseline_score and a current_score on a
           comparable test set. This is the real reward — not task success,
           but future capability gain.
           Source: provided externally (TransferArena.evaluate().test_rate)

Architecture note
─────────────────
This module is pure computation — no browser, no I/O, no LLM.
Callers supply the raw signals; this module normalises and weights them.

compute_reward_signal() returns a RewardSignal that can be:
  - Logged as a metric on CapabilityRecord
  - Used as training signal for BC policy
  - Used to rank capability candidates for promotion
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set


@dataclass
class RewardSignal:
    """Multi-layer reward for a capability or execution event."""
    # Layer 1: did the task terminal state complete?
    task_completed: Optional[bool] = None

    # Layer 2: was this the first time this capability ran on a new environment?
    transferred_to_new_env: Optional[bool] = None
    new_env_key: Optional[str] = None

    # Layer 3: is this capability_hint absent from the hardcoded taxonomy?
    is_novel: Optional[bool] = None
    capability_hint: Optional[str] = None

    # Layer 4: how many times has this capability been successfully reused?
    reuse_count: int = 0

    # Layer 5: competence delta (test_rate_after - test_rate_before)
    competence_delta: Optional[float] = None
    baseline_score: Optional[float] = None
    current_score: Optional[float] = None

    @property
    def composite_score(self) -> float:
        """Weighted composite reward in [0, 1+] range.

        Weights reflect the difficulty/value hierarchy:
          Layer 1: 0.2  (task success, but may be site-specific)
          Layer 2: 0.3  (transfer is worth more than single-site success)
          Layer 3: 0.1  (novelty bonus — raw discovery, not validated)
          Layer 4: 0.2  (sustained reuse proves utility)
          Layer 5: 0.5  (future competence gain is the ground truth — can exceed 1.0)

        Unset layers contribute 0.
        """
        score = 0.0
        if self.task_completed:
            score += 0.2
        if self.transferred_to_new_env:
            score += 0.3
        if self.is_novel:
            score += 0.1
        if self.reuse_count > 0:
            score += min(0.2, 0.05 * self.reuse_count)  # caps at 4 reuses
        if self.competence_delta is not None and self.competence_delta > 0:
            score += min(0.5, self.competence_delta)
        return round(score, 4)

    def summary(self) -> str:
        parts = [
            f"L1={int(self.task_completed) if self.task_completed is not None else '?'}",
            f"L2={int(self.transferred_to_new_env) if self.transferred_to_new_env is not None else '?'}",
            f"L3(novel)={int(self.is_novel) if self.is_novel is not None else '?'}",
            f"L4(reuse)={self.reuse_count}",
            f"L5(delta)={f'{self.competence_delta:+.3f}' if self.competence_delta is not None else '?'}",
            f"composite={self.composite_score:.3f}",
        ]
        return " | ".join(parts)


# ── Known taxonomy ────────────────────────────────────────────────────────────

def _known_capability_hints() -> Set[str]:
    """Return the set of all capability_hint values in the hardcoded taxonomy."""
    try:
        from browsermind_core.recorder.capability_classifier import CAPABILITY_RULES
        return {rule["capability"] for rule in CAPABILITY_RULES if "capability" in rule}
    except Exception:
        return set()


# Cache at import time — CAPABILITY_RULES is a module-level constant
_KNOWN_HINTS: Optional[Set[str]] = None


def is_novel_capability(capability_hint: str) -> bool:
    """Return True iff capability_hint does NOT appear in the hardcoded taxonomy.

    A hint absent from CAPABILITY_RULES is a genuine discovery: the system
    encountered a pattern that human rules did not anticipate.
    """
    global _KNOWN_HINTS
    if _KNOWN_HINTS is None:
        _KNOWN_HINTS = _known_capability_hints()
    if not capability_hint:
        return False
    return capability_hint not in _KNOWN_HINTS


# ── Signal computation ────────────────────────────────────────────────────────

def compute_reward_signal(
    *,
    capability_hint: str = "",
    task_completed: Optional[bool] = None,
    current_env_key: str = "",
    training_envs: Optional[list] = None,
    existing_transfer_envs: Optional[list] = None,
    reuse_count: int = 0,
    baseline_score: Optional[float] = None,
    current_score: Optional[float] = None,
) -> RewardSignal:
    """Compute a RewardSignal from the available evidence.

    Args:
        capability_hint:       The capability_hint string (for Layer 3).
        task_completed:        Layer 1 — contract_goal_completed result.
        current_env_key:       The environment this execution ran on.
        training_envs:         Known training environments for this family.
                               If current_env_key is NOT in training_envs,
                               this is a transfer event (Layer 2).
        existing_transfer_envs: Envs already in CapabilityRecord.transfer_envs
                               before this run. Used to determine if this is a
                               *new* transfer (not just a repeat).
        reuse_count:           CapabilityRecord.reuse_count (Layer 4).
        baseline_score:        Test rate before recent training (Layer 5).
        current_score:         Test rate after recent training (Layer 5).
    """
    # Layer 2: transfer to new env
    transferred = None
    new_env = None
    if current_env_key:
        known = set(training_envs or [])
        seen = set(existing_transfer_envs or [])
        if current_env_key not in known and current_env_key not in seen:
            transferred = True
            new_env = current_env_key
        else:
            transferred = False

    # Layer 3: novelty
    novel = is_novel_capability(capability_hint) if capability_hint else None

    # Layer 5: competence delta
    delta = None
    if baseline_score is not None and current_score is not None:
        delta = round(current_score - baseline_score, 4)

    return RewardSignal(
        task_completed=task_completed,
        transferred_to_new_env=transferred,
        new_env_key=new_env,
        is_novel=novel,
        capability_hint=capability_hint or None,
        reuse_count=reuse_count,
        competence_delta=delta,
        baseline_score=baseline_score,
        current_score=current_score,
    )
