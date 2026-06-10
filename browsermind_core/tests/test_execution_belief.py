"""Tests for ExecutionBelief inter-step belief propagation.

Verifies:
  - belief_from_attribution() correctly populates StepBelief
  - adjust_strategy_order() with None belief = no change
  - Rule 1: url_changed moves affordance strategies to front
  - Rule 2: failed_strategy is deprioritised (moved to end)
  - Rule 3: effect_verified=False pushes structural_path to end
  - Multiple rules compose correctly
  - Source-level: prior_belief wired in replay_engine + target_resolver
"""
from __future__ import annotations

from unittest.mock import MagicMock


# ── belief_from_attribution ───────────────────────────────────────────────────

def test_belief_from_attribution_success_step():
    from browsermind_core.runtime.execution_belief import belief_from_attribution
    attr = MagicMock()
    attr.actual_outcome = "SUCCESS"
    attr.step_seq = 3
    attr.effect_verified = True
    attr.effect_type = "URL_CHANGED"
    attr.resolved_by = "primary_semantic"
    belief = belief_from_attribution(attr)
    assert belief.step_seq == 3
    assert belief.effect_verified is True
    assert belief.url_changed is True
    assert belief.failed_strategy is None
    assert belief.resolved_by == "primary_semantic"


def test_belief_from_attribution_failed_step():
    from browsermind_core.runtime.execution_belief import belief_from_attribution
    attr = MagicMock()
    attr.actual_outcome = "FAILED"
    attr.step_seq = 2
    attr.effect_verified = None
    attr.effect_type = None
    attr.resolved_by = "placeholder"
    belief = belief_from_attribution(attr)
    assert belief.failed_strategy == "placeholder"
    assert belief.resolved_by is None
    assert belief.url_changed is False


def test_belief_from_attribution_transition_success_url_changed():
    from browsermind_core.runtime.execution_belief import belief_from_attribution
    attr = MagicMock()
    attr.actual_outcome = "TRANSITION_SUCCESS"
    attr.step_seq = 1
    attr.effect_verified = True
    attr.effect_type = "DOM_CHANGED"
    attr.resolved_by = "primary_semantic"
    belief = belief_from_attribution(attr)
    assert belief.url_changed is True


# ── adjust_strategy_order ────────────────────────────────────────────────────

def test_adjust_no_belief_unchanged():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order
    strategies = ["primary_semantic", "placeholder", "structural_path"]
    result = adjust_strategy_order(strategies, None)
    assert result == strategies


def test_adjust_failed_strategy_moves_to_end():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order, StepBelief
    belief = StepBelief(
        step_seq=1,
        effect_verified=None,
        effect_type=None,
        url_changed=False,
        failed_strategy="placeholder",
        resolved_by=None,
    )
    strategies = ["placeholder", "primary_semantic", "structural_path"]
    result = adjust_strategy_order(strategies, belief)
    assert result[-1] == "placeholder"
    assert "primary_semantic" in result
    assert "structural_path" in result


def test_adjust_url_changed_moves_affordance_to_front():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order, StepBelief
    belief = StepBelief(
        step_seq=1,
        effect_verified=True,
        effect_type="URL_CHANGED",
        url_changed=True,
        failed_strategy=None,
        resolved_by="primary_semantic",
    )
    strategies = ["primary_semantic", "placeholder", "affordance_intent", "capability_intent"]
    result = adjust_strategy_order(strategies, belief)
    # affordance/capability should be at front
    assert result[0] in ("affordance_intent", "capability_intent")
    assert result[1] in ("affordance_intent", "capability_intent")


def test_adjust_effect_not_verified_pushes_structural_to_end():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order, StepBelief
    belief = StepBelief(
        step_seq=2,
        effect_verified=False,
        effect_type="UNKNOWN",
        url_changed=False,
        failed_strategy=None,
        resolved_by=None,
    )
    strategies = ["structural_path", "primary_semantic", "placeholder"]
    result = adjust_strategy_order(strategies, belief)
    assert result[-1] == "structural_path"


def test_adjust_unknown_failed_strategy_appended():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order, StepBelief
    belief = StepBelief(
        step_seq=1,
        effect_verified=None,
        effect_type=None,
        url_changed=False,
        failed_strategy="loose_semantic",
        resolved_by=None,
    )
    strategies = ["primary_semantic", "loose_semantic", "placeholder"]
    result = adjust_strategy_order(strategies, belief)
    assert result[-1] == "loose_semantic"


def test_adjust_does_not_mutate_original():
    from browsermind_core.runtime.execution_belief import adjust_strategy_order, StepBelief
    belief = StepBelief(
        step_seq=1, effect_verified=False, effect_type="UNKNOWN",
        url_changed=False, failed_strategy="placeholder", resolved_by=None,
    )
    original = ["primary_semantic", "placeholder", "structural_path"]
    original_copy = list(original)
    adjust_strategy_order(original, belief)
    assert original == original_copy


# ── Source-level verification ────────────────────────────────────────────────

def test_replay_engine_imports_belief_from_attribution():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "belief_from_attribution" in src
    assert "_prior_belief" in src
    assert "prior_belief=_prior_belief" in src


def test_target_resolver_imports_adjust_strategy_order():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "target_resolver.py"
    ).read_text(encoding="utf-8")
    assert "adjust_strategy_order" in src
    assert "prior_belief" in src
    assert "execution_belief" in src
