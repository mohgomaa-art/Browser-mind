"""
retry_policy.py — Per-step retry policy with exponential backoff and jitter.

Used by StepRecoveryEngine to decide whether and how to retry a failed step
before escalating to harder recovery or marking the step as permanently failed.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RetryDecision(Enum):
    RETRY      = "retry"
    ESCALATE   = "escalate"   # try harder recovery (re-nav, bot-wall)
    ABANDON    = "abandon"    # step is un-retryable; propagate failure


@dataclass
class RetryContext:
    """Mutable state carried between retry attempts for a single step."""
    step_seq: int
    action_type: str
    failure_reason: str
    attempt: int = 0
    total_delay_ms: float = 0.0
    escalated: bool = False


@dataclass
class RetryPolicy:
    """
    Configures retry behaviour for one class of failure.

    Attributes:
        max_attempts:       Total attempts including the first (1 = no retry).
        base_delay_ms:      Initial wait between attempts (ms).
        backoff_factor:     Multiplier applied each retry round.
        max_delay_ms:       Cap on per-attempt delay.
        jitter_ratio:       Fraction of delay to randomise (0.0 = no jitter).
        escalate_on_attempt: Attempt number at which to switch from RETRY to
                             ESCALATE (0 = never escalate, just retry until
                             max_attempts then ABANDON).
    """
    max_attempts: int = 3
    base_delay_ms: float = 500.0
    backoff_factor: float = 2.0
    max_delay_ms: float = 8_000.0
    jitter_ratio: float = 0.3
    escalate_on_attempt: int = 0    # 0 = disabled

    # ------------------------------------------------------------------ #
    # Canonical presets                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def transient(cls) -> "RetryPolicy":
        """For network hiccups, JS exceptions, short element-not-found."""
        return cls(
            max_attempts=3,
            base_delay_ms=300.0,
            backoff_factor=2.0,
            max_delay_ms=4_000.0,
            jitter_ratio=0.25,
            escalate_on_attempt=0,
        )

    @classmethod
    def stale_dom(cls) -> "RetryPolicy":
        """For element detached / stale reference — need to re-resolve."""
        return cls(
            max_attempts=2,
            base_delay_ms=800.0,
            backoff_factor=1.5,
            max_delay_ms=3_000.0,
            jitter_ratio=0.2,
            escalate_on_attempt=2,  # escalate to re-resolve on 2nd attempt
        )

    @classmethod
    def navigation(cls) -> "RetryPolicy":
        """For navigation timeouts — longer waits, fewer retries."""
        return cls(
            max_attempts=2,
            base_delay_ms=2_000.0,
            backoff_factor=2.0,
            max_delay_ms=10_000.0,
            jitter_ratio=0.1,
            escalate_on_attempt=0,
        )

    @classmethod
    def no_retry(cls) -> "RetryPolicy":
        """For fatal errors where retrying never helps."""
        return cls(max_attempts=1, base_delay_ms=0.0, backoff_factor=1.0,
                   max_delay_ms=0.0, jitter_ratio=0.0)

    # ------------------------------------------------------------------ #
    # Decision logic                                                       #
    # ------------------------------------------------------------------ #

    def decide(self, ctx: RetryContext) -> RetryDecision:
        if ctx.attempt >= self.max_attempts:
            return RetryDecision.ABANDON
        if self.escalate_on_attempt > 0 and ctx.attempt >= self.escalate_on_attempt:
            if not ctx.escalated:
                ctx.escalated = True
                return RetryDecision.ESCALATE
        return RetryDecision.RETRY

    async def wait(self, ctx: RetryContext) -> None:
        """Sleep the appropriate backoff duration and increment the attempt counter."""
        delay = min(
            self.base_delay_ms * (self.backoff_factor ** ctx.attempt),
            self.max_delay_ms,
        )
        if self.jitter_ratio > 0:
            jitter = delay * self.jitter_ratio * (random.random() * 2 - 1)
            delay = max(0.0, delay + jitter)
        ctx.total_delay_ms += delay
        ctx.attempt += 1
        if delay > 0:
            await asyncio.sleep(delay / 1000.0)


# ------------------------------------------------------------------ #
# Failure classifier — maps failure_reason to a RetryPolicy preset   #
# ------------------------------------------------------------------ #

def policy_for_failure(failure_reason: Optional[str]) -> RetryPolicy:
    """Select the appropriate RetryPolicy based on the failure string."""
    if not failure_reason:
        return RetryPolicy.transient()
    r = failure_reason.lower()
    if any(k in r for k in ("detached", "stale", "not attached", "element not found")):
        return RetryPolicy.stale_dom()
    if any(k in r for k in ("navigation", "timeout", "net::err", "err_name_not")):
        return RetryPolicy.navigation()
    if any(k in r for k in ("page crash", "session closed", "target closed")):
        return RetryPolicy.no_retry()
    if any(k in r for k in ("unknown action", "unhandled action", "not in registry")):
        return RetryPolicy.no_retry()
    return RetryPolicy.transient()
