"""
sstg_planner.py — Dijkstra shortest-path planner over the SSTG.

Given a current semantic state and a target state fingerprint, finds the
minimum-confidence-weighted path through the Semantic State Transition Graph
and returns an ordered list of capability_hash steps to execute.

Used by the L14 Planning layer (ExecutionCoordinator) to decompose a high-level
goal (e.g. "post a job") into a sequence of capabilities (e.g. login → navigate
to job board → fill form → submit).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from browsermind_core.learning.state_transition_graph import (
    SemanticStateTransitionGraph,
    StateTransitionEdge,
)
from browsermind_core.ontology.semantic_state import SemanticState


@dataclass
class PlanStep:
    """One step in a planned execution path."""
    from_state: str
    to_state: str
    capability_hash: str
    confidence: float
    observation_count: int
    env_keys: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """Complete execution plan from current state to target state."""
    start: str
    goal: str
    steps: List[PlanStep]
    total_cost: float          # sum of (1 - confidence) for each edge
    feasible: bool
    reason: str = ""

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0

    def capability_sequence(self) -> List[str]:
        return [s.capability_hash for s in self.steps]

    def summary(self) -> str:
        if not self.feasible:
            return f"No path from {self.start!r} to {self.goal!r}: {self.reason}"
        seq = " → ".join(s.capability_hash for s in self.steps)
        return f"Plan ({len(self.steps)} steps, cost={self.total_cost:.2f}): {seq}"


class SSTGPlanner:
    """
    Dijkstra shortest-path planner over SemanticStateTransitionGraph.

    Edge weight = 1 - confidence (low-confidence edges are more expensive).
    Zero-confidence edges (never-observed transitions) are excluded by default.
    """

    def __init__(
        self,
        sstg: SemanticStateTransitionGraph,
        min_confidence: float = 0.0,
        max_depth: int = 10,
        prefer_env: Optional[str] = None,
    ) -> None:
        self._sstg = sstg
        self._min_confidence = min_confidence
        self._max_depth = max_depth
        self._prefer_env = prefer_env

    def plan(
        self,
        current: str,
        goal: str,
    ) -> Plan:
        """
        Find the minimum-cost path from `current` fingerprint to `goal` fingerprint.

        Returns Plan(feasible=False) if no path exists within max_depth.
        """
        if current == goal:
            return Plan(start=current, goal=goal, steps=[], total_cost=0.0,
                        feasible=True, reason="already at goal")

        if goal not in self._sstg.nodes:
            return Plan(start=current, goal=goal, steps=[], total_cost=float("inf"),
                        feasible=False, reason=f"goal state {goal!r} not in SSTG")

        # Dijkstra
        # State: (cost, node, path)
        # path is a list of StateTransitionEdge
        dist: Dict[str, float] = {current: 0.0}
        prev: Dict[str, Optional[Tuple[str, StateTransitionEdge]]] = {current: None}

        heap: List[Tuple[float, int, str]] = [(0.0, 0, current)]
        seq = 0
        visited: Set[str] = set()

        # Build forward adjacency
        fwd: Dict[str, List[StateTransitionEdge]] = {}
        for e in self._sstg.edges:
            if e.confidence < self._min_confidence:
                continue
            fwd.setdefault(e.from_state, []).append(e)

        reached = False
        while heap:
            cost, _, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)

            if node == goal:
                reached = True
                break

            # Depth limit
            depth = self._path_depth(node, prev)
            if depth >= self._max_depth:
                continue

            for edge in fwd.get(node, []):
                neighbor = edge.to_state
                # Prefer edges observed on the target environment
                env_bonus = 0.0
                if self._prefer_env and self._prefer_env in edge.env_keys:
                    env_bonus = 0.05

                edge_cost = max(0.0, (1.0 - edge.confidence) - env_bonus)
                new_cost = cost + edge_cost

                if new_cost < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_cost
                    prev[neighbor] = (node, edge)
                    seq += 1
                    heapq.heappush(heap, (new_cost, seq, neighbor))

        if not reached:
            return Plan(start=current, goal=goal, steps=[], total_cost=float("inf"),
                        feasible=False,
                        reason=f"no path within depth={self._max_depth}")

        # Reconstruct path
        steps: List[PlanStep] = []
        node = goal
        while prev.get(node) is not None:
            parent, edge = prev[node]  # type: ignore[misc]
            steps.append(PlanStep(
                from_state=edge.from_state,
                to_state=edge.to_state,
                capability_hash=edge.capability_hash,
                confidence=edge.confidence,
                observation_count=edge.observation_count,
                env_keys=list(edge.env_keys),
            ))
            node = parent
        steps.reverse()

        return Plan(
            start=current,
            goal=goal,
            steps=steps,
            total_cost=round(dist[goal], 4),
            feasible=True,
        )

    def reachable_from(self, start: str) -> List[str]:
        """Return all states reachable from `start` (BFS, no depth limit)."""
        visited: Set[str] = set()
        queue = [start]
        fwd: Dict[str, List[StateTransitionEdge]] = {}
        for e in self._sstg.edges:
            fwd.setdefault(e.from_state, []).append(e)
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            for edge in fwd.get(node, []):
                queue.append(edge.to_state)
        visited.discard(start)
        return sorted(visited)

    def shortest_paths_to(self, goal: str, top_k: int = 3) -> List[Plan]:
        """Return the top-k cheapest plans to `goal` from all known start nodes."""
        plans = []
        for start in self._sstg.nodes:
            if start == goal:
                continue
            plan = self.plan(start, goal)
            if plan.feasible:
                plans.append(plan)
        plans.sort(key=lambda p: p.total_cost)
        return plans[:top_k]

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _path_depth(
        self,
        node: str,
        prev: Dict[str, Optional[Tuple[str, StateTransitionEdge]]],
    ) -> int:
        depth = 0
        cur = node
        while prev.get(cur) is not None:
            parent, _ = prev[cur]  # type: ignore[misc]
            cur = parent
            depth += 1
            if depth > self._max_depth + 1:
                break
        return depth
