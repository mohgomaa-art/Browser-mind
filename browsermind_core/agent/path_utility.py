"""
Path Utility Scorer (P7G-B3a).
Implements a Lexicographic Ordering Preference Model.

Tiers of Preference (Evaluated strictly in order):
1. State Quality: AVAILABILITY > OBSERVATION
2. Path Length: Shorter is better (Evaluated ONLY if State Quality ties)

No scalar tuning, no magic numbers.
"""
from dataclasses import dataclass
from typing import List

from browsermind_core.ontology.asset import AssetGraph, StateClass
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry


@dataclass
class PathScore:
    """Lexicographic score data for a capability path. No policy attached."""
    state_quality: StateClass
    path_length: int

    def __str__(self):
        return f"[State: {self.state_quality.value}, Length: {self.path_length}]"


class PathUtilityScorer:
    def __init__(self):
        self.registry = RequirementStateRegistry()

    def score_path(self, path: List[str], target_state: str, graph: AssetGraph) -> PathScore:
        """
        Evaluates a complete structural path and returns a lexicographically sortable score.
        """
        state_class = self._evaluate_state_quality(target_state)
        return PathScore(
            state_quality=state_class,
            path_length=len(path)
        )

    def _evaluate_state_quality(self, target_state: str) -> StateClass:
        """Looks up the target state in the registry to determine its StateClass."""
        for req, target_states in self.registry.requirement_target_states.items():
            for ts in target_states:
                if ts.state == target_state:
                    return ts.state_class
        return StateClass.OBSERVATION  # Safe fallback

    def get_sort_key(self, score: PathScore):
        """
        Ranking Policy: Converts a PathScore data object into a lexicographically sortable tuple.
        AVAILABILITY (2) > OBSERVATION (1).
        Shorter path lengths are better (tie-breaker only).
        """
        quality_val = 2 if score.state_quality == StateClass.AVAILABILITY else 1
        return (quality_val, -score.path_length)
