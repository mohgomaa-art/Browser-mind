"""A-4: classify_failure must accept a typed exception and dispatch on type.

Substring matching on `failure_reason` is brittle — a rename of an exception's
message rotates classification silently. The runtime already raises typed
TargetResolutionError / AmbiguousIdentityError; the taxonomy now consumes them
when available, while keeping the substring path for legacy callers.
"""
from __future__ import annotations

import pytest

from browsermind_core.experiments.failure_taxonomy import classify_failure
from browsermind_core.experiments.replay_result import FailureCategory
from browsermind_core.runtime.target_resolver import (
    TargetResolutionError,
    AmbiguousIdentityError,
)


def test_target_resolution_error_classified_as_target_changed():
    cat, reason = classify_failure(
        failure_reason=None,
        exception=TargetResolutionError("nope"),
    )
    assert cat == FailureCategory.TARGET_CHANGED
    assert reason  # not empty


def test_ambiguous_identity_error_classified_as_ambiguous_target():
    err = AmbiguousIdentityError(role="button", name="Submit", candidate_count=3)
    cat, reason = classify_failure(failure_reason=None, exception=err)
    assert cat == FailureCategory.AMBIGUOUS_TARGET
    assert "AMBIGUOUS_IDENTITY" in reason or "ambiguous" in reason.lower()


def test_typed_exception_takes_precedence_over_substring():
    # The reason string would normally be classified as CONTRACT_FAILURE by the
    # substring path. The typed exception must win.
    cat, _ = classify_failure(
        failure_reason="this string contains contract_failure noise",
        exception=TargetResolutionError("nope"),
    )
    assert cat == FailureCategory.TARGET_CHANGED


def test_unknown_exception_falls_through_to_substring():
    # RuntimeError is not one of the typed cases; the substring path still classifies.
    cat, _ = classify_failure(
        failure_reason="targetnotfound generic",
        exception=RuntimeError("targetnotfound generic"),
    )
    assert cat == FailureCategory.TARGET_CHANGED


def test_no_exception_legacy_path_unchanged():
    cat, _ = classify_failure(failure_reason="contract_failure")
    assert cat == FailureCategory.CONTRACT_FAILURE


def test_typed_exception_with_no_reason_uses_str_exception():
    cat, reason = classify_failure(
        failure_reason=None,
        exception=TargetResolutionError("explicit message here"),
    )
    assert cat == FailureCategory.TARGET_CHANGED
    assert "explicit message here" in reason


def test_no_failure_no_step_no_exception_returns_no_failure_recorded():
    cat, reason = classify_failure(failure_reason=None)
    assert cat == FailureCategory.ENVIRONMENT_FAILURE
    assert reason == "no failure recorded"
