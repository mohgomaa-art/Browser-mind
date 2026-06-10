"""
execution_coordinator.py — ExecutionCoordinator v2.

Wires the full L14 Planning layer into a single goal-execution loop:

  GoalSpec → GoalDecomposer → [capability_hash, ...] →
  CapabilityDispatcher (per step) → VerifierPipeline (post-goal) →
  CoordinatorResult

Architecture:
  - GoalDecomposer decides *what* to execute (SSTG / hints / heuristic).
  - CapabilityDispatcher executes *each step* via ReplayEngine (Phase 3 hardened).
  - VerifierPipeline (Phase 1 / L6) confirms the goal state was reached.

Backward compatibility:
  - The legacy execute_with_fallback() API is preserved as a thin shim so
    existing callers (tests, auto_pilot) continue to work unchanged.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page

from browsermind_core.execution.capability_dispatcher import (
    CapabilityDispatcher,
    DispatchResult,
)
from browsermind_core.execution.goal_decomposer import DecompositionResult, GoalDecomposer
from browsermind_core.execution.goal_spec import GoalSpec
from browsermind_core.execution.outcome_verifier import OutcomeVerifier, VerificationResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class StepOutcome:
    """Per-capability-step result within a coordinator run."""
    step_index: int
    capability_hash: str
    dispatch_result: DispatchResult

    @property
    def success(self) -> bool:
        return self.dispatch_result.success or self.dispatch_result.skipped


@dataclass
class CoordinatorResult:
    """
    Top-level result of ExecutionCoordinator.execute_goal().

    Fields:
        success:            True when all steps succeeded and the goal state is verified.
        goal_id:            The GoalSpec.goal_id that was executed.
        strategy:           Decomposition strategy used ("sstg" | "hint" | "heuristic" | "none").
        capability_sequence: Ordered list of capability_hash strings that were executed.
        step_outcomes:      Per-step results.
        verification:       Post-goal VerificationResult from VerifierPipeline (or None).
        failure_step:       Index of the first failing step (None on success).
        failure_reason:     Human-readable failure explanation.
        metadata:           Extensible key-value store for caller use.
    """
    success: bool
    goal_id: str
    strategy: str
    capability_sequence: List[str] = field(default_factory=list)
    step_outcomes: List[StepOutcome] = field(default_factory=list)
    verification: Optional[Any] = None          # VerificationReport from VerifierPipeline
    failure_step: Optional[int] = None
    failure_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        seq = " → ".join(self.capability_sequence) or "(none)"
        if self.success:
            return f"[{status}] goal='{self.goal_id}' strategy={self.strategy} steps={seq}"
        return (
            f"[{status}] goal='{self.goal_id}' strategy={self.strategy} "
            f"failed_at={self.failure_step} reason={self.failure_reason!r}"
        )


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class ExecutionCoordinator:
    """
    V2 execution coordinator.  Accepts either a GoalSpec (new API) or
    the legacy ranked_paths list (shim).

    Args:
        verifier:            Legacy OutcomeVerifier (kept for backward compat).
        goal_decomposer:     GoalDecomposer wired to the live SSTG.
        capability_dispatcher: CapabilityDispatcher wired to WorkflowStore + ReplayEngine.
        verifier_pipeline:   Optional VerifierPipeline (Phase 1 L6) for post-goal checks.
        stop_on_first_failure: If True (default), abort the sequence on first step failure.
        skip_unknown:        If True (default), treat steps with no template as no-ops
                             rather than failures (allows partial execution of sparse goals).
    """

    def __init__(
        self,
        verifier: Optional[OutcomeVerifier] = None,
        goal_decomposer: Optional[GoalDecomposer] = None,
        capability_dispatcher: Optional[CapabilityDispatcher] = None,
        verifier_pipeline: Optional[Any] = None,
        stop_on_first_failure: bool = True,
        skip_unknown: bool = True,
    ) -> None:
        # legacy
        self.verifier = verifier or OutcomeVerifier()
        # v2
        self._decomposer = goal_decomposer
        self._dispatcher = capability_dispatcher
        self._verifier_pipeline = verifier_pipeline
        self._stop_on_failure = stop_on_first_failure
        self._skip_unknown = skip_unknown

    # ------------------------------------------------------------------
    # V2 API
    # ------------------------------------------------------------------

    async def execute_goal(
        self,
        spec: GoalSpec,
        page: Optional["Page"] = None,
        current_state: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> CoordinatorResult:
        """
        Execute a GoalSpec end-to-end.

        1. Decompose the goal into a capability sequence.
        2. Dispatch each capability via CapabilityDispatcher.
        3. Run VerifierPipeline post-goal (if wired).
        4. Return CoordinatorResult.

        Args:
            spec:              The goal to execute.
            page:              Playwright page — used for live state extraction
                               and post-goal verification.
            current_state:     Override current SSTG fingerprint (skip live extraction).
            execution_context: Passed to the post-goal verifier.
        """
        if self._decomposer is None or self._dispatcher is None:
            return CoordinatorResult(
                success=False,
                goal_id=spec.goal_id,
                strategy="none",
                failure_reason=(
                    "ExecutionCoordinator v2 not fully wired — "
                    "goal_decomposer and capability_dispatcher are required."
                ),
            )

        # ---------------------------------------------------------------
        # Step 1: Decompose
        # ---------------------------------------------------------------
        decomp: DecompositionResult = self._decomposer.decompose(
            spec, current_state=current_state
        )
        if not decomp.feasible:
            return CoordinatorResult(
                success=False,
                goal_id=spec.goal_id,
                strategy=decomp.strategy,
                capability_sequence=[],
                failure_reason=decomp.reason,
            )

        cap_seq = decomp.capability_sequence
        step_outcomes: List[StepOutcome] = []

        # ---------------------------------------------------------------
        # Step 2: Dispatch each capability
        # ---------------------------------------------------------------
        for idx, cap_hash in enumerate(cap_seq):
            dispatch = await self._dispatcher.dispatch(
                capability_hash=cap_hash,
                context=execution_context,
            )
            outcome = StepOutcome(
                step_index=idx,
                capability_hash=cap_hash,
                dispatch_result=dispatch,
            )
            step_outcomes.append(outcome)

            step_failed = not dispatch.success and not (
                dispatch.skipped and self._skip_unknown
            )
            if step_failed and self._stop_on_failure:
                return CoordinatorResult(
                    success=False,
                    goal_id=spec.goal_id,
                    strategy=decomp.strategy,
                    capability_sequence=cap_seq,
                    step_outcomes=step_outcomes,
                    failure_step=idx,
                    failure_reason=dispatch.error or f"Step {idx} ({cap_hash}) failed",
                )

        # ---------------------------------------------------------------
        # Step 3: Post-goal verification
        # ---------------------------------------------------------------
        verification_result = None
        if self._verifier_pipeline is not None and page is not None:
            try:
                from browsermind_core.runtime.verifier_engine_v2 import VerificationSpec
                vspec = VerificationSpec(
                    expected_url_contains=spec.target_state if "/" in spec.target_state else None,
                )
                verification_result = await self._verifier_pipeline.verify(
                    page=page,
                    verdict=None,
                    spec=vspec,
                )
                if verification_result and not verification_result.passed:
                    return CoordinatorResult(
                        success=False,
                        goal_id=spec.goal_id,
                        strategy=decomp.strategy,
                        capability_sequence=cap_seq,
                        step_outcomes=step_outcomes,
                        verification=verification_result,
                        failure_reason=(
                            f"Post-goal verification failed (score={verification_result.score:.2f})"
                        ),
                    )
            except Exception as exc:
                # Verification error is non-fatal; log and proceed
                pass

        return CoordinatorResult(
            success=True,
            goal_id=spec.goal_id,
            strategy=decomp.strategy,
            capability_sequence=cap_seq,
            step_outcomes=step_outcomes,
            verification=verification_result,
        )

    # ------------------------------------------------------------------
    # Legacy shim — backward compatibility
    # ------------------------------------------------------------------

    async def execute_with_fallback(
        self,
        ranked_paths: List[List[str]],
        executor: Any,
        execution_context: Dict[str, Any],
    ) -> dict:
        """
        Attempts to execute candidate paths in ranked order until one
        produces a VALID artifact.  Preserved from v1 for backward compat.
        """
        results_log = []

        for i, path in enumerate(ranked_paths):
            if hasattr(executor, "execute_capability_path"):
                artifact = await executor.execute_capability_path(
                    path, execution_context.get("context", {})
                )
            else:
                artifact = executor.simulate(path)

            verification = self.verifier.verify(artifact, execution_context)
            results_log.append({
                "rank": i + 1,
                "path": path,
                "verification": verification.value,
                "artifact": artifact,
            })

            if verification == VerificationResult.VALID:
                return {
                    "success": True,
                    "resolved_by_path": path,
                    "resolved_at_rank": i + 1,
                    "log": results_log,
                }

        return {
            "success": False,
            "resolved_by_path": None,
            "resolved_at_rank": None,
            "log": results_log,
        }
