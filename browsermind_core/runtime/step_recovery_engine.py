"""
step_recovery_engine.py — Step-level recovery for failed replay steps.

Handles three recovery scenarios after a step's primary execution fails:

  1. DOM_CHURN — element detached / stale; re-run TargetResolver with
     fresh page state before retrying the action.

  2. PAGE_STALE — URL changed unexpectedly, page lost session; navigate
     back to the expected URL and retry from the failed step.

  3. BOT_WALL — bot detection page appeared mid-replay; call
     BotWallRecovery and, if resolved, re-issue the step.

The engine is called from ReplayHardening.run_step_with_hardening() and
NEVER raises into the replay main loop — it returns a StepRecoveryResult
that the caller uses to decide continue / pause / abandon.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

from browsermind_core.runtime.bot_wall_recovery import BotWallRecovery, BotWallSeverity
from browsermind_core.runtime.retry_policy import (
    RetryContext,
    RetryDecision,
    RetryPolicy,
    policy_for_failure,
)

if TYPE_CHECKING:
    from playwright.async_api import Page


class RecoveryOutcome(Enum):
    SUCCEEDED      = "succeeded"       # step passed after recovery
    RETRY          = "retry"           # should re-attempt primary execution
    ESCALATE_HUMAN = "escalate_human"  # needs a human (bot-wall, 2FA, etc.)
    ABANDON        = "abandon"         # recovery exhausted; mark step failed


@dataclass
class StepRecoveryResult:
    outcome: RecoveryOutcome
    attempts: int = 0
    total_delay_ms: float = 0.0
    recovery_type: str = ""     # "dom_churn" | "bot_wall" | "page_stale" | ""
    bot_wall_signal: str = ""
    error: str = ""


class StepRecoveryEngine:
    """
    Orchestrates recovery for a single failed step.

    Called after the primary execution attempt fails.  Returns
    StepRecoveryResult indicating what happened and what to do next.
    """

    def __init__(
        self,
        page: "Page",
        bot_wall_recovery: Optional[BotWallRecovery] = None,
    ) -> None:
        self._page = page
        self._bwr = bot_wall_recovery or BotWallRecovery()

    async def recover(
        self,
        step: Dict[str, Any],
        failure_reason: str,
        step_seq: int,
        action_type: str,
        expected_url: Optional[str] = None,
    ) -> StepRecoveryResult:
        """
        Attempt recovery after a step failure.

        Recovery is attempted in priority order:
          1. Bot-wall check (pre-empts DOM-level recovery)
          2. DOM churn recovery (re-resolve)
          3. Page-stale recovery (re-navigate)
          4. Transient retry (pure backoff)
        """
        try:
            return await self._do_recover(
                step, failure_reason, step_seq, action_type, expected_url
            )
        except Exception as exc:
            return StepRecoveryResult(
                outcome=RecoveryOutcome.ABANDON,
                error=f"StepRecoveryEngine internal error: {exc}",
            )

    async def _do_recover(
        self,
        step: Dict[str, Any],
        failure_reason: str,
        step_seq: int,
        action_type: str,
        expected_url: Optional[str],
    ) -> StepRecoveryResult:
        # --- 1. Bot-wall check ---
        try:
            bw_result = await self._bwr.check_and_recover(self._page)
        except Exception:
            bw_result = None

        if bw_result and bw_result.detected:
            if bw_result.resolved:
                return StepRecoveryResult(
                    outcome=RecoveryOutcome.RETRY,
                    recovery_type="bot_wall",
                    bot_wall_signal=bw_result.signal,
                    total_delay_ms=float(bw_result.wait_ms),
                )
            # Not auto-resolved — escalate to human
            severity_label = bw_result.severity.value
            return StepRecoveryResult(
                outcome=RecoveryOutcome.ESCALATE_HUMAN,
                recovery_type="bot_wall",
                bot_wall_signal=bw_result.signal,
                error=f"Bot wall ({severity_label}) could not be auto-resolved: {bw_result.signal!r}",
            )

        # --- 2. DOM churn recovery ---
        if self._is_dom_churn(failure_reason):
            await asyncio.sleep(0.8)
            # Re-check page is stable before retrying
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=5_000)
            except Exception:
                pass
            return StepRecoveryResult(
                outcome=RecoveryOutcome.RETRY,
                recovery_type="dom_churn",
                total_delay_ms=800.0,
            )

        # --- 3. Page-stale recovery ---
        if expected_url and self._is_page_stale(expected_url):
            try:
                await self._page.goto(expected_url, timeout=20_000)
                await self._page.wait_for_load_state("domcontentloaded", timeout=10_000)
                return StepRecoveryResult(
                    outcome=RecoveryOutcome.RETRY,
                    recovery_type="page_stale",
                    total_delay_ms=2_000.0,
                )
            except Exception as nav_err:
                return StepRecoveryResult(
                    outcome=RecoveryOutcome.ABANDON,
                    recovery_type="page_stale",
                    error=f"Re-navigation failed: {nav_err}",
                )

        # --- 4. Transient retry (pure policy backoff) ---
        policy = policy_for_failure(failure_reason)
        ctx = RetryContext(
            step_seq=step_seq,
            action_type=action_type,
            failure_reason=failure_reason,
        )
        decision = policy.decide(ctx)
        if decision == RetryDecision.RETRY:
            await policy.wait(ctx)
            return StepRecoveryResult(
                outcome=RecoveryOutcome.RETRY,
                recovery_type="transient",
                attempts=ctx.attempt,
                total_delay_ms=ctx.total_delay_ms,
            )

        return StepRecoveryResult(
            outcome=RecoveryOutcome.ABANDON,
            error=failure_reason,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _is_dom_churn(self, reason: str) -> bool:
        r = (reason or "").lower()
        return any(k in r for k in (
            "detached", "stale", "not attached", "element is not attached",
            "element handle is disposed", "target closed",
        ))

    def _is_page_stale(self, expected_url: str) -> bool:
        try:
            current = self._page.url or ""
            # Stale if we're on a completely different domain
            from urllib.parse import urlparse
            exp_host = urlparse(expected_url).netloc
            cur_host = urlparse(current).netloc
            return exp_host != "" and exp_host != cur_host
        except Exception:
            return False
