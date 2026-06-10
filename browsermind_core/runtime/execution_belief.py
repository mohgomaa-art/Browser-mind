"""ExecutionBelief — inter-step belief state for the resolver.

The resolver currently treats every step independently. ExecutionBelief carries
the outcome of the *previous* step into the resolution of the *current* step.

This closes the observe-update-act cycle at the step boundary:
  - If the previous step's strategy FAILED, de-prioritise it for this step.
  - If the previous step triggered an unexpected URL change, try affordance_intent
    earlier (the page may have navigated to an unexpected state).
  - If the previous step had effect_verified=False, log it as a soft warning
    so boundary extraction can pick it up.

Design
──────
- Pure dataclass + helper functions. No I/O, no LLM, no browser.
- TargetResolver.resolve() receives prior_belief=None (default).
  When set, adjust_strategy_order() reorders the resolver's fallback ladder.
- Backward compatible: None belief = existing behaviour unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class StepBelief:
    """Belief state derived from the outcome of the previous step.

    Built by relay_engine.replay() from the most recent FailureAttribution
    entry before calling resolver.resolve() for the next step.
    """
    step_seq: int               # which step this belief was derived from
    effect_verified: Optional[bool]   # True/False/None from FailureAttribution
    effect_type: Optional[str]        # e.g. "URL_CHANGED", "ELEMENT_DISAPPEARED"
    url_changed: bool                 # shorthand: effect_type == "URL_CHANGED"
    failed_strategy: Optional[str]    # resolved_by of the failed step (or None on success)
    resolved_by: Optional[str]        # resolved_by of a successful step


# Strategy execution order when a prior belief changes priorities
_AFFORDANCE_EARLY_STRATEGIES = ["affordance_intent", "capability_intent"]
_DEPRIORITISED_FLOOR = 999  # push deprioritised strategies to end of ladder


def adjust_strategy_order(
    ordered_strategies: List[str],
    belief: Optional[StepBelief],
) -> List[str]:
    """Reorder strategy list based on prior_belief.

    Rules applied in priority order:
    1. If belief.url_changed unexpectedly (effect_type not TRANSITION_SUCCESS
       but URL still changed), try affordance_intent / capability_intent first —
       the page is in an unexpected state, structural strategies are unreliable.
    2. If belief.failed_strategy is set, move that strategy to end —
       it just failed on the previous step, same page structure.
    3. If belief.effect_verified is False, prefer semantic strategies over
       structural ones (structural_path deprioritised).

    Returns a new list (original is not mutated).
    """
    if belief is None:
        return list(ordered_strategies)

    result = list(ordered_strategies)

    # Rule 2: deprioritise the previously-failed strategy
    if belief.failed_strategy and belief.failed_strategy in result:
        result.remove(belief.failed_strategy)
        result.append(belief.failed_strategy)

    # Rule 1: unexpected URL change → afford-based strategies move to front
    if belief.url_changed and belief.effect_type not in ("TRANSITION_SUCCESS",):
        for s in reversed(_AFFORDANCE_EARLY_STRATEGIES):
            if s in result:
                result.remove(s)
                result.insert(0, s)

    # Rule 3: effect_verified=False → structural_path to end
    if belief.effect_verified is False and "structural_path" in result:
        result.remove("structural_path")
        result.append("structural_path")

    return result


def belief_from_attribution(attr) -> StepBelief:
    """Build a StepBelief from a FailureAttribution row.

    Called by replay_engine after each step to prepare the belief
    for the next step's resolver call.
    """
    success = getattr(attr, "actual_outcome", "") in ("SUCCESS", "TRANSITION_SUCCESS")
    effect_type = getattr(attr, "effect_type", None)
    url_changed = effect_type == "URL_CHANGED" or effect_type == "DOM_CHANGED"
    return StepBelief(
        step_seq=getattr(attr, "step_seq", 0),
        effect_verified=getattr(attr, "effect_verified", None),
        effect_type=effect_type,
        url_changed=url_changed,
        failed_strategy=None if success else getattr(attr, "resolved_by", None),
        resolved_by=getattr(attr, "resolved_by", None) if success else None,
    )
