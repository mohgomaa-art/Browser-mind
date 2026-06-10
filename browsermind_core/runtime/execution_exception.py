"""
execution_exception.py — Typed exception taxonomy for the L5 Executor.

Replaces the anti-pattern of bare `except Exception` that bleeds every failure
mode into a single `effect_verified = None` bucket, making BCPolicyV2 unable
to distinguish targeting failures from genuine execution uncertainty.

Classification rules (mutually exclusive, checked in this order by classify()):

  ELEMENT_NOT_FOUND   — Playwright could not locate the target element.
                        This is a TARGETING failure, NOT an execution event.
                        Do NOT run EffectVerifier. Do NOT record quality signal.
                        Route to TargetResolver retry immediately.

  TIMEOUT             — Playwright waited for element/nav and exceeded deadline.
                        May indicate the action was partially executed.
                        DO run EffectVerifier on the post-timeout page state.
                        The action may have succeeded despite the timeout.

  NAVIGATION_BLOCKED  — goto/expect_navigation rejected (CSP, same-origin, etc.)
                        Interesting signal: log as NAVIGATION_BLOCKED, continue.
                        Do NOT fail the step. Check if URL changed anyway.

  PAGE_CRASH          — Page/browser context crashed or was closed.
                        Escalate immediately to StepRecoveryEngine with HARD failure.
                        Do NOT verify. Do NOT retry.

  NETWORK_ERROR       — fetch/XHR failed at network layer (ERR_NETWORK_CHANGED etc.)
                        Retry up to RetryPolicy.transient() limits before giving up.
                        Do NOT verify until network is confirmed stable.

  SCRIPT_ERROR        — Site JS threw (SyntaxError in page.evaluate, etc.)
                        Usually indicates a site bug, not our failure.
                        Log and continue. effect_verified = None (genuinely unknown).

  EXECUTION_ERROR     — Generic catch-all for Playwright action failures that
                        don't match the above. Examples: intercepted clicks,
                        element disabled, iframe cross-origin, etc.
                        Run EffectVerifier — the action may have partially executed.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class ExecutionExceptionClass(Enum):
    ELEMENT_NOT_FOUND  = "element_not_found"
    TIMEOUT            = "timeout"
    NAVIGATION_BLOCKED = "navigation_blocked"
    PAGE_CRASH         = "page_crash"
    NETWORK_ERROR      = "network_error"
    SCRIPT_ERROR       = "script_error"
    EXECUTION_ERROR    = "execution_error"   # generic — run verifier


# ---------------------------------------------------------------------------
# Routing table for each exception class
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class ExceptionRouting:
    """
    Tells callers how to handle each exception class.

    Fields:
        run_verifier:    Whether to run EffectVerifier on the post-failure state.
        record_quality:  Whether to write this outcome to OutcomeLedger.
        retry_class:     Which RetryPolicy preset to use ("transient", "stale_dom",
                         "no_retry"). None means caller decides.
        escalate:        Whether to escalate to StepRecoveryEngine immediately.
    """
    run_verifier: bool
    record_quality: bool
    retry_class: Optional[str]
    escalate: bool


EXCEPTION_ROUTING: dict = {
    ExecutionExceptionClass.ELEMENT_NOT_FOUND:  ExceptionRouting(
        run_verifier=False,
        record_quality=False,
        retry_class="stale_dom",
        escalate=False,
    ),
    ExecutionExceptionClass.TIMEOUT:            ExceptionRouting(
        run_verifier=True,   # action may have succeeded before timeout
        record_quality=True,
        retry_class="transient",
        escalate=False,
    ),
    ExecutionExceptionClass.NAVIGATION_BLOCKED: ExceptionRouting(
        run_verifier=True,   # check if URL changed anyway
        record_quality=True,
        retry_class="no_retry",
        escalate=False,
    ),
    ExecutionExceptionClass.PAGE_CRASH:         ExceptionRouting(
        run_verifier=False,
        record_quality=False,
        retry_class="no_retry",
        escalate=True,       # hard escalate to StepRecoveryEngine
    ),
    ExecutionExceptionClass.NETWORK_ERROR:      ExceptionRouting(
        run_verifier=False,
        record_quality=False,
        retry_class="transient",
        escalate=False,
    ),
    ExecutionExceptionClass.SCRIPT_ERROR:       ExceptionRouting(
        run_verifier=False,
        record_quality=False,
        retry_class="no_retry",
        escalate=False,
    ),
    ExecutionExceptionClass.EXECUTION_ERROR:    ExceptionRouting(
        run_verifier=True,
        record_quality=True,
        retry_class="transient",
        escalate=False,
    ),
}


# ---------------------------------------------------------------------------
# Pattern-based classifier
# ---------------------------------------------------------------------------

_PATTERNS: list = [
    # ELEMENT_NOT_FOUND — must be before TIMEOUT
    (ExecutionExceptionClass.ELEMENT_NOT_FOUND, re.compile(
        r"strict mode violation|"
        r"no element.*matching|"
        r"unable to find element|"
        r"element not found|"
        r"locator\..*resolved to \d+ elements|"
        r"has no visible text|"
        r"waiting for.*locator.*resolved to 0|"
        r"selector.*matches nothing",
        re.IGNORECASE,
    )),
    # PAGE_CRASH
    (ExecutionExceptionClass.PAGE_CRASH, re.compile(
        r"page.*closed|"
        r"target.*closed|"
        r"browser.*closed|"
        r"context.*closed|"
        r"session.*closed|"
        r"connection.*refused",
        re.IGNORECASE,
    )),
    # TIMEOUT
    (ExecutionExceptionClass.TIMEOUT, re.compile(
        r"timeout.*exceeded|"
        r"timed out|"
        r"timeout \d+ms|"
        r"waiting for.*timeout|"
        r"navigation timeout|"
        r"TimeoutError",
        re.IGNORECASE,
    )),
    # NAVIGATION_BLOCKED
    (ExecutionExceptionClass.NAVIGATION_BLOCKED, re.compile(
        r"net::ERR_BLOCKED|"
        r"net::ERR_ABORTED|"
        r"navigation.*blocked|"
        r"cross-origin|"
        r"same-origin|"
        r"Content Security Policy",
        re.IGNORECASE,
    )),
    # NETWORK_ERROR
    (ExecutionExceptionClass.NETWORK_ERROR, re.compile(
        r"net::ERR_NETWORK|"
        r"net::ERR_INTERNET|"
        r"net::ERR_NAME_NOT_RESOLVED|"
        r"net::ERR_CONNECTION|"
        r"ECONNREFUSED|"
        r"ETIMEDOUT|"
        r"network.*error",
        re.IGNORECASE,
    )),
    # SCRIPT_ERROR
    (ExecutionExceptionClass.SCRIPT_ERROR, re.compile(
        r"Evaluation failed|"
        r"SyntaxError|"
        r"ReferenceError.*is not defined|"
        r"page\.evaluate|"
        r"frame\.evaluate",
        re.IGNORECASE,
    )),
]


def classify_exception(exc: Exception) -> ExecutionExceptionClass:
    """
    Classify a Playwright exception into one of the ExecutionExceptionClass values.

    Uses pattern matching on the exception message string.
    Falls back to EXECUTION_ERROR (run verifier, record quality) for unknowns.
    """
    msg = str(exc)
    for cls, pattern in _PATTERNS:
        if pattern.search(msg):
            return cls
    return ExecutionExceptionClass.EXECUTION_ERROR


def routing_for(exc: Exception) -> ExceptionRouting:
    """Convenience: classify + look up routing in one call."""
    return EXCEPTION_ROUTING[classify_exception(exc)]
