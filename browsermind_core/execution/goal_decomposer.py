"""
goal_decomposer.py — Breaks a GoalSpec into an ordered capability_hash sequence.

Strategy (in order of preference):
  1. SSTG-based: if the graph has a path from start_state → target_state,
     return the capability_sequence from SSTGPlanner.plan().
  2. Hint-only: if GoalSpec.capability_hints is non-empty, use that sequence directly.
  3. Heuristic: map goal_id to a hardcoded fallback sequence for common goals.
  4. Fail: return a DecompositionResult with feasible=False.

Callers should always check DecompositionResult.feasible before proceeding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from browsermind_core.execution.goal_spec import GoalSpec
from browsermind_core.learning.sstg_planner import Plan, SSTGPlanner


# ---------------------------------------------------------------------------
# Fallback heuristics — used when SSTG has insufficient coverage
# ---------------------------------------------------------------------------

_HEURISTIC: dict = {
    "login":             ["navigate_to_login", "login"],
    "search":            ["search"],
    "checkout":          ["add_to_cart", "checkout", "place_order"],
    "submit_form":       ["fill_form", "submit_form"],
    "apply_job":         ["navigate_to_job", "fill_application", "submit_form"],
    "register":          ["navigate_to_register", "register"],
    "logout":            ["logout"],
    "navigate":          ["navigate"],
    "add_to_cart":       ["add_to_cart"],
    "place_order":       ["place_order"],
    "upload":            ["upload"],
    "download":          ["download"],
    "fill_form":         ["fill_form"],
}


@dataclass
class DecompositionResult:
    """
    Output of GoalDecomposer.decompose().

    Fields:
        feasible:           Whether a path was found.
        strategy:           "sstg" | "hint" | "heuristic" | "none"
        capability_sequence: Ordered list of capability_hash strings.
        plan:               The SSTGPlanner Plan when strategy == "sstg".
        reason:             Human-readable explanation (populated on failure).
    """
    feasible: bool
    strategy: str
    capability_sequence: List[str] = field(default_factory=list)
    plan: Optional[Plan] = None
    reason: str = ""

    def summary(self) -> str:
        if not self.feasible:
            return f"Decomposition failed ({self.strategy}): {self.reason}"
        seq = " → ".join(self.capability_sequence)
        return f"[{self.strategy}] {len(self.capability_sequence)} steps: {seq}"


class GoalDecomposer:
    """
    Decomposes a GoalSpec into an ordered capability_hash sequence.

    Args:
        sstg_planner:     SSTGPlanner built from the live SSTG.
        default_start:    Fallback start_state when GoalSpec.start_state is None.
                          Typically the current SemanticState fingerprint of the page.
        min_confidence:   Minimum SSTG edge confidence for the planner to use.
    """

    def __init__(
        self,
        sstg_planner: SSTGPlanner,
        default_start: str = "unauthenticated",
        min_confidence: float = 0.3,
    ) -> None:
        self._planner = sstg_planner
        self._default_start = default_start
        self._min_confidence = min_confidence

    def decompose(
        self,
        spec: GoalSpec,
        current_state: Optional[str] = None,
    ) -> DecompositionResult:
        """
        Decompose spec into a capability sequence.

        Args:
            spec:          The goal to decompose.
            current_state: Override for the start state (e.g. live page state).
        """
        start = current_state or spec.start_state or self._default_start

        # ------------------------------------------------------------------
        # 1. SSTG-based path
        # ------------------------------------------------------------------
        try:
            plan = self._planner.plan(
                current=start,
                goal=spec.target_state,
            )
            if plan.feasible and plan.steps:
                return DecompositionResult(
                    feasible=True,
                    strategy="sstg",
                    capability_sequence=plan.capability_sequence(),
                    plan=plan,
                )
        except Exception:
            pass  # SSTG unavailable / graph too sparse — fall through

        # ------------------------------------------------------------------
        # 2. Hint-only path
        # ------------------------------------------------------------------
        if spec.capability_hints:
            return DecompositionResult(
                feasible=True,
                strategy="hint",
                capability_sequence=list(spec.capability_hints),
            )

        # ------------------------------------------------------------------
        # 3. Heuristic path
        # ------------------------------------------------------------------
        fallback = _HEURISTIC.get(spec.goal_id)
        if fallback:
            return DecompositionResult(
                feasible=True,
                strategy="heuristic",
                capability_sequence=list(fallback),
            )

        # ------------------------------------------------------------------
        # 4. No path found
        # ------------------------------------------------------------------
        return DecompositionResult(
            feasible=False,
            strategy="none",
            reason=(
                f"No SSTG path from '{start}' to '{spec.target_state}', "
                f"no capability hints, and no heuristic for goal_id='{spec.goal_id}'."
            ),
        )
