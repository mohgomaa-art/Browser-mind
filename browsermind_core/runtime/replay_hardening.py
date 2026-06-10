"""
replay_hardening.py — Top-level orchestrator that wraps ReplayEngine step execution
with the full Phase 3 hardening stack:

  ┌─────────────────────────────────────────────────────────┐
  │  ReplayHardening.run_step_with_hardening()              │
  │                                                         │
  │  1. Pre-step: bot-wall check                            │
  │  2. Run primary step (via callback)                     │
  │  3. On failure: StepRecoveryEngine.recover()            │
  │     ├─ bot_wall → BotWallRecovery                       │
  │     ├─ dom_churn → wait + RETRY                         │
  │     ├─ page_stale → re-navigate + RETRY                 │
  │     └─ transient → backoff + RETRY                      │
  │  4. Checkpoint write on ESCALATE_HUMAN / bot_wall       │
  │  5. Return HardenedStepResult to caller                 │
  └─────────────────────────────────────────────────────────┘

Integration:
    ReplayEngine wires this in the step loop as:
        hardening = ReplayHardening(page, store_dir, workflow_id, template_name)
        result = await hardening.run_step_with_hardening(
            step=step, step_seq=seq,
            action_type=action_type,
            primary_fn=lambda: executor.execute(...),
            failure_reason_fn=lambda exc: str(exc),
            expected_url=url_before,
        )
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from browsermind_core.runtime.bot_wall_recovery import BotWallRecovery
from browsermind_core.runtime.replay_checkpoint import ReplayCheckpoint
from browsermind_core.runtime.step_recovery_engine import (
    RecoveryOutcome,
    StepRecoveryEngine,
    StepRecoveryResult,
)

if TYPE_CHECKING:
    from playwright.async_api import Page


@dataclass
class HardenedStepResult:
    """Outcome of a single hardened step execution."""
    success: bool
    step_seq: int
    attempts: int = 1
    recovery_type: str = ""      # "" | "bot_wall" | "dom_churn" | "page_stale" | "transient"
    total_delay_ms: float = 0.0
    checkpoint_written: bool = False
    needs_human: bool = False    # True when bot-wall or 2FA requires operator
    bot_wall_signal: str = ""
    error: str = ""


class ReplayHardening:
    """
    Wraps a single step execution with the full Phase 3 hardening stack.

    One instance per replay run (created in ReplayEngine.__init__ or at
    the top of replay()). Stateless between steps — safe to share.
    """

    def __init__(
        self,
        page: "Page",
        store_dir: str,
        workflow_id: str,
        template_name: str,
        max_recovery_attempts: int = 2,
    ) -> None:
        self._page = page
        self._store_dir = store_dir
        self._workflow_id = workflow_id
        self._template_name = template_name
        self._max_recovery = max_recovery_attempts
        self._bwr = BotWallRecovery()
        self._recovery = StepRecoveryEngine(page, bot_wall_recovery=self._bwr)

    def update_page(self, page: "Page") -> None:
        """Call when the Playwright page reference changes (e.g. new tab)."""
        self._page = page
        self._bwr = BotWallRecovery()
        self._recovery = StepRecoveryEngine(page, bot_wall_recovery=self._bwr)

    async def pre_step_check(self) -> Optional[StepRecoveryResult]:
        """
        Run before every step. Returns a non-None StepRecoveryResult only
        if a bot-wall is detected that blocks execution.
        """
        try:
            bw = await self._bwr.check_and_recover(self._page)
            if bw.detected and not bw.resolved:
                from browsermind_core.runtime.step_recovery_engine import RecoveryOutcome
                return StepRecoveryResult(
                    outcome=RecoveryOutcome.ESCALATE_HUMAN,
                    recovery_type="bot_wall",
                    bot_wall_signal=bw.signal,
                    error=f"Bot wall pre-step: {bw.signal!r}",
                )
        except Exception:
            pass
        return None

    async def run_step_with_hardening(
        self,
        step: Dict[str, Any],
        step_seq: int,
        action_type: str,
        primary_fn: Callable,
        completed_steps: int = 0,
        attribution_so_far: Optional[list] = None,
        environment_key: str = "",
        expected_url: Optional[str] = None,
    ) -> HardenedStepResult:
        """
        Execute primary_fn() with recovery on failure.

        primary_fn must be a zero-arg async callable.
        On exception, StepRecoveryEngine drives recovery.
        Up to max_recovery_attempts total recovery rounds.
        """
        attempts = 0
        total_delay: float = 0.0
        last_error = ""
        last_recovery: Optional[StepRecoveryResult] = None

        while attempts <= self._max_recovery:
            try:
                await primary_fn()
                return HardenedStepResult(
                    success=True,
                    step_seq=step_seq,
                    attempts=attempts + 1,
                    recovery_type=last_recovery.recovery_type if last_recovery else "",
                    total_delay_ms=total_delay,
                )
            except Exception as exc:
                last_error = str(exc)
                attempts += 1

                if attempts > self._max_recovery:
                    break

                rec = await self._recovery.recover(
                    step=step,
                    failure_reason=last_error,
                    step_seq=step_seq,
                    action_type=action_type,
                    expected_url=expected_url,
                )
                last_recovery = rec
                total_delay += rec.total_delay_ms

                if rec.outcome == RecoveryOutcome.ESCALATE_HUMAN:
                    # Write checkpoint so the run can be resumed
                    cp_written = self._write_checkpoint(
                        step_seq=step_seq,
                        completed_steps=completed_steps,
                        attribution_so_far=attribution_so_far or [],
                        environment_key=environment_key,
                        reason=rec.recovery_type or "bot_wall",
                    )
                    return HardenedStepResult(
                        success=False,
                        step_seq=step_seq,
                        attempts=attempts,
                        recovery_type=rec.recovery_type,
                        total_delay_ms=total_delay,
                        checkpoint_written=cp_written,
                        needs_human=True,
                        bot_wall_signal=rec.bot_wall_signal,
                        error=rec.error or last_error,
                    )

                if rec.outcome == RecoveryOutcome.ABANDON:
                    break

                # RecoveryOutcome.RETRY — loop back and try primary_fn again

        return HardenedStepResult(
            success=False,
            step_seq=step_seq,
            attempts=attempts,
            recovery_type=last_recovery.recovery_type if last_recovery else "",
            total_delay_ms=total_delay,
            error=last_error,
        )

    # ------------------------------------------------------------------ #
    # Checkpoint helpers                                                   #
    # ------------------------------------------------------------------ #

    def _write_checkpoint(
        self,
        step_seq: int,
        completed_steps: int,
        attribution_so_far: list,
        environment_key: str,
        reason: str,
    ) -> bool:
        """Write a checkpoint file. Returns True on success."""
        try:
            serialised = []
            for attr in attribution_so_far:
                if hasattr(attr, "model_dump"):
                    serialised.append(attr.model_dump(mode="json"))
                elif hasattr(attr, "__dict__"):
                    serialised.append(vars(attr))
                else:
                    serialised.append(attr)

            cp = ReplayCheckpoint(
                workflow_id=self._workflow_id,
                template_name=self._template_name,
                next_step=step_seq,
                completed_steps=completed_steps,
                attribution_so_far=serialised,
                environment_key=environment_key,
                reason=reason,
            )
            cp.save(self._store_dir)
            return True
        except Exception:
            return False

    def delete_checkpoint(self) -> None:
        """Remove checkpoint after a successful replay run."""
        try:
            ReplayCheckpoint.delete(self._store_dir, self._workflow_id)
        except Exception:
            pass
