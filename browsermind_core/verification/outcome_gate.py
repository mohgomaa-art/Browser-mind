"""OutcomeGate — policy class for outcome-verified capability promotion gates.

Controls three gates in the learning pipeline, each behind an env-var feature flag
(default: off = existing behaviour preserved):

  OUTCOME_GATE_MINE_FILTER    — _mine_step_outcomes() prefers effect_verified=True records
  OUTCOME_GATE_COMPILE_FILTER — _compile_and_promote() compiles from verified records when available
  OUTCOME_GATE_PROMOTION      — stress_test_passed is derived from contract_verified_ratio, not stubbed

Rollback: set any flag to 'false' (or unset it) to revert that gate immediately.
No records are deleted or retroactively downgraded.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from browsermind_core.ledger.outcome_ledger import OutcomeRecord
    from browsermind_core.ontology.p1_schemas import WorkflowTemplate

# Feature flags — False by default so existing behaviour is preserved.
OUTCOME_GATE_MINE_FILTER: bool = os.getenv("OUTCOME_GATE_MINE_FILTER", "false").lower() == "true"
OUTCOME_GATE_COMPILE_FILTER: bool = os.getenv("OUTCOME_GATE_COMPILE_FILTER", "false").lower() == "true"
OUTCOME_GATE_PROMOTION: bool = os.getenv("OUTCOME_GATE_PROMOTION", "false").lower() == "true"

# Minimum verified ratio for stress_test_passed=True when OUTCOME_GATE_PROMOTION is enabled.
_MIN_VERIFIED_RATIO: float = 0.80
# Minimum verified records for compile filter to activate.
_MIN_VERIFIED_FOR_COMPILE: int = 2
# Minimum verified records for mine filter to activate.
_MIN_VERIFIED_FOR_MINE: int = 2


def is_effect_verified(record: "OutcomeRecord") -> bool:
    """True iff this step OutcomeRecord carries a confirmed effect_verified=True signal."""
    return bool((record.metrics or {}).get("effect_verified") is True)


def is_contract_verified(record: "OutcomeRecord") -> bool:
    """True iff this execution-scope OutcomeRecord was verified by ContractVerifier."""
    return bool((record.metrics or {}).get("contract_goal_completed") is True)


def contract_verified_ratio(records: List["OutcomeRecord"]) -> float:
    """Fraction of records that carry contract_goal_completed=True.

    Returns 0.0 for an empty list. Only counts records that have the key set
    (True or False); records with None/missing are excluded from the denominator
    so that 'unverified' records do not penalise early-stage templates that have
    never been run against a contract.
    """
    with_result = [
        r for r in records
        if (r.metrics or {}).get("contract_goal_completed") is not None
    ]
    if not with_result:
        return 0.0
    verified = sum(1 for r in with_result if r.metrics.get("contract_goal_completed") is True)
    return verified / len(with_result)


def resolve_stress_test(
    template_name: str,
    env_key: str,
    execution_records: List["OutcomeRecord"],
    *,
    has_contract: bool,
) -> tuple[bool, str]:
    """Determine stress_test_passed for PromotionRules.evaluate_candidate().

    Returns (stress_test_passed: bool, reason: str).

    When OUTCOME_GATE_PROMOTION is disabled, returns (True, 'STUBBED') — same
    as the prior hardcoded behaviour.

    When enabled:
      - No contract:  returns (False, 'no_contract') — caps tier at STRONG_CANDIDATE max.
      - Has contract: returns (True, 'ratio=X.XX') iff contract_verified_ratio >= 0.80.
    """
    if not OUTCOME_GATE_PROMOTION:
        return True, "STUBBED"

    if not has_contract:
        return False, f"no_contract: template={template_name} env={env_key}"

    ratio = contract_verified_ratio(execution_records)
    if ratio >= _MIN_VERIFIED_RATIO:
        return True, f"ratio={ratio:.2f}"
    return False, f"ratio={ratio:.2f} below threshold={_MIN_VERIFIED_RATIO:.2f}"


def filter_for_mining(
    step_records: List["OutcomeRecord"],
) -> tuple[List["OutcomeRecord"], str]:
    """Return the record pool to mine, plus a diagnostic label.

    When OUTCOME_GATE_MINE_FILTER is disabled: returns the full list unchanged.
    When enabled: returns verified records if >= _MIN_VERIFIED_FOR_MINE exist,
    otherwise falls back to the full list with a logged reason.
    """
    if not OUTCOME_GATE_MINE_FILTER:
        return step_records, f"gate_off total={len(step_records)}"

    verified = [r for r in step_records if is_effect_verified(r)]
    if len(verified) >= _MIN_VERIFIED_FOR_MINE:
        return verified, f"verified={len(verified)}/{len(step_records)}"
    return step_records, f"fallback: verified={len(verified)}<{_MIN_VERIFIED_FOR_MINE} total={len(step_records)}"


def filter_for_compilation(
    step_records: List["OutcomeRecord"],
) -> tuple[List["OutcomeRecord"], str, bool]:
    """Return the record pool for InvariantCompiler, a diagnostic label, and a
    `verified_compile: bool` flag that callers can use to cap the promotion tier.

    When OUTCOME_GATE_COMPILE_FILTER is disabled: returns full list, verified_compile=False.
    When enabled: returns verified records if >= _MIN_VERIFIED_FOR_COMPILE exist
    (verified_compile=True), otherwise falls back to full list (verified_compile=False).
    """
    if not OUTCOME_GATE_COMPILE_FILTER:
        return step_records, f"gate_off total={len(step_records)}", False

    verified = [r for r in step_records if is_effect_verified(r)]
    if len(verified) >= _MIN_VERIFIED_FOR_COMPILE:
        return verified, f"verified={len(verified)}/{len(step_records)}", True
    return (
        step_records,
        f"fallback: verified={len(verified)}<{_MIN_VERIFIED_FOR_COMPILE} total={len(step_records)}",
        False,
    )
