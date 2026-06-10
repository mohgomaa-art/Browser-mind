"""Failure taxonomy — classify replay failures into fixed categories."""
from __future__ import annotations

from typing import Any, Dict, Optional

from browsermind_core.experiments.replay_result import FailureCategory

_GENERIC_ROLES = frozenset({"img", "div", "span", "section", "li", "ul", "ol", "canvas"})

_ENV_SIGNALS = (
    "timeout",
    "timed out",
    "navigation",
    "net::",
    "session",
    "system error",
    "browser closed",
    "target closed",
    "connection",
)

_CONTRACT_SIGNALS = (
    "contract_failure",
    "contract failed",
    "contract verifier",
    "state not persisted",
    "outcome not satisfied",
)

_PORTAL_SIGNALS = (
    "portal_context_failure",
    "environment_instance_mismatch",
    "portal association",
    "environment instance mismatch",
)

_FALSE_POSITIVE_SIGNALS = (
    "false_positive_resolution",
    "resolved_incorrect",
    "wrong element",
    "incorrect target",
)


def _step_replayability_reasons(step: Optional[Dict[str, Any]]) -> list[str]:
    if not step:
        return []
    assessment = step.get("replayability") or {}
    return list(assessment.get("reasons") or [])


def _is_empty_semantics(step: Optional[Dict[str, Any]]) -> bool:
    if not step:
        return False

    role = (step.get("target_role") or "").strip().lower()
    name = (step.get("target_name") or "").strip()
    descriptor = step.get("descriptor") or {}
    accessible_name = (descriptor.get("accessible_name") or "").strip()
    text_content = (descriptor.get("text_content") or "").strip()
    reasons = _step_replayability_reasons(step)

    if role in _GENERIC_ROLES and not name and not accessible_name and not text_content:
        return True
    if "generic_role_with_no_name" in reasons:
        return True
    if "missing_name" in reasons and not name and not accessible_name:
        return True
    if not role and not name:
        return True
    return False


_TEXT_INPUT_ROLES = frozenset({"textbox", "searchbox", "spinbutton"})


def _is_orphaned_semantic_signal(step: Optional[Dict[str, Any]]) -> bool:
    """
    True when a text input has an empty accessible name but the step carries
    evidence that a human-visible label exists nearby (orphaned_label reason
    set by the Compiler, or a non-empty target_selector whose label id we can
    infer from a sibling label element).

    The key criterion: this is an ENVIRONMENTAL failure (website broke the
    label association), not a recorder bug.
    """
    if not step:
        return False
    role = (step.get("target_role") or "").strip().lower()
    name = (step.get("target_name") or "").strip()
    if role not in _TEXT_INPUT_ROLES:
        return False
    if name:  # if we resolved a name, it's not orphaned
        return False
    reasons = _step_replayability_reasons(step)
    return "orphaned_label" in reasons


def _empty_semantics_label(step: Optional[Dict[str, Any]]) -> str:
    role = (step.get("target_role") or "unknown").strip().lower() if step else "unknown"
    name = (step.get("target_name") or "").strip() if step else ""
    if not name:
        return f"{role} + empty name"
    return f"{role} + {name}"


def classify_failure(
    *,
    failure_reason: Optional[str],
    failed_step: Optional[Dict[str, Any]] = None,
    exception: Optional[BaseException] = None,
) -> tuple[FailureCategory, str]:
    """
    Map a replay failure to a taxonomy category and a human-readable reason.

    Returns (category, normalized_reason).
    """
    reason = (failure_reason or "").strip()
    lower = reason.lower()

    if not reason and failed_step is None and exception is None:
        return FailureCategory.ENVIRONMENT_FAILURE, "no failure recorded"

    # Typed-exception dispatch — preferred path when a runtime exception is
    # available. Falls through to substring matching for legacy callers.
    if exception is not None:
        from browsermind_core.runtime.target_resolver import (
            TargetResolutionError,
            AmbiguousIdentityError,
        )
        if isinstance(exception, AmbiguousIdentityError):
            return FailureCategory.AMBIGUOUS_TARGET, reason or str(exception) or "ambiguous target"
        if isinstance(exception, TargetResolutionError):
            return FailureCategory.TARGET_CHANGED, reason or str(exception) or "recorded target no longer exists"

    if any(signal in lower for signal in _FALSE_POSITIVE_SIGNALS):
        return FailureCategory.FALSE_POSITIVE_RESOLUTION, reason or "false positive resolution"

    if any(signal in lower for signal in _CONTRACT_SIGNALS):
        return FailureCategory.CONTRACT_FAILURE, reason or "contract failure"

    if any(signal in lower for signal in _PORTAL_SIGNALS):
        return FailureCategory.PORTAL_CONTEXT_FAILURE, reason or "portal context failure"

    if "descriptor_loss" in lower or "low_confidence" in lower:
        return FailureCategory.DESCRIPTOR_LOSS, reason or "descriptor loss"

    if any(signal in lower for signal in _ENV_SIGNALS):
        return FailureCategory.ENVIRONMENT_FAILURE, reason or "environment failure"

    # ORPHANED_SEMANTIC_SIGNAL must be checked before NO_VISIBLE_SIGNAL: it is the more
    # specific environmental diagnosis (website broke label association).
    if _is_orphaned_semantic_signal(failed_step):
        label = _empty_semantics_label(failed_step)
        return FailureCategory.ORPHANED_SEMANTIC_SIGNAL, label

    if _is_empty_semantics(failed_step):
        return FailureCategory.NO_VISIBLE_SIGNAL, _empty_semantics_label(failed_step)

    reasons = _step_replayability_reasons(failed_step)
    if "multiple_candidates" in reasons or "multiple matching" in lower or "ambiguous" in lower:
        label = reason or "multiple matching elements"
        return FailureCategory.AMBIGUOUS_TARGET, label

    if "targetnotfound" in lower.replace("_", "").replace(" ", ""):
        return FailureCategory.TARGET_CHANGED, reason or "recorded target no longer exists"

    if reason:
        return FailureCategory.ENVIRONMENT_FAILURE, reason

    return FailureCategory.ENVIRONMENT_FAILURE, "classification impossible"
