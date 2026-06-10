"""
goal_registry.py — In-process registry for GoalSpec definitions.

Supports registering, looking up, and listing GoalSpecs.  This is intentionally
a lightweight in-process registry; persisted goals live in the caller's store.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from browsermind_core.execution.goal_spec import (
    GoalSpec,
    GOAL_LOGIN,
    GOAL_SEARCH,
    GOAL_CHECKOUT,
    GOAL_SUBMIT_FORM,
    GOAL_APPLY_JOB,
)


class GoalRegistry:
    """
    Stores GoalSpec definitions keyed by goal_id.

    At construction the five built-in goals are pre-registered.
    Callers may register additional goals at any point.
    """

    def __init__(self) -> None:
        self._specs: Dict[str, GoalSpec] = {}
        for spec in (
            GOAL_LOGIN,
            GOAL_SEARCH,
            GOAL_CHECKOUT,
            GOAL_SUBMIT_FORM,
            GOAL_APPLY_JOB,
        ):
            self.register(spec)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, spec: GoalSpec) -> None:
        """Register or overwrite a GoalSpec."""
        if not spec.goal_id:
            raise ValueError("GoalSpec.goal_id must not be empty")
        self._specs[spec.goal_id] = spec

    def unregister(self, goal_id: str) -> bool:
        """Remove a GoalSpec. Returns True if it existed."""
        return self._specs.pop(goal_id, None) is not None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, goal_id: str) -> Optional[GoalSpec]:
        """Exact lookup by goal_id. Returns None if not found."""
        return self._specs.get(goal_id)

    def require(self, goal_id: str) -> GoalSpec:
        """Lookup that raises KeyError if the goal is not registered."""
        spec = self._specs.get(goal_id)
        if spec is None:
            raise KeyError(
                f"Goal '{goal_id}' is not registered. "
                f"Available: {sorted(self._specs.keys())}"
            )
        return spec

    def find(self, query: str) -> List[GoalSpec]:
        """Case-insensitive substring search over goal_id and description."""
        q = query.lower()
        return [
            s for s in self._specs.values()
            if q in s.goal_id.lower() or q in s.description.lower()
        ]

    def all(self) -> List[GoalSpec]:
        return list(self._specs.values())

    def __iter__(self) -> Iterator[GoalSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, goal_id: str) -> bool:
        return goal_id in self._specs
