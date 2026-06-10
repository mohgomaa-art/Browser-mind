"""Tests for Reward Layers 1-5 implementation.

Verifies:
  - compute_reward_signal() sets each layer independently
  - Layer 2: transfer_to_new_env detected correctly
  - Layer 3: novelty detection against hardcoded taxonomy
  - Layer 5: competence_delta computed from baseline/current
  - composite_score weights and bounds
  - CapabilityRecord has reuse_count and is_novel fields
  - CapabilityRecord.record_reuse increments count
"""
from __future__ import annotations


# ── Layer 1-5 signal computation ─────────────────────────────────────────────

def test_layer1_task_completed():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(task_completed=True)
    assert sig.task_completed is True


def test_layer2_transfer_new_env():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(
        current_env_key="gitlab",
        training_envs=["github"],
        existing_transfer_envs=[],
    )
    assert sig.transferred_to_new_env is True
    assert sig.new_env_key == "gitlab"


def test_layer2_known_env_not_transfer():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(
        current_env_key="github",
        training_envs=["github"],
        existing_transfer_envs=[],
    )
    assert sig.transferred_to_new_env is False


def test_layer2_already_seen_env_not_new_transfer():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(
        current_env_key="gitlab",
        training_envs=["github"],
        existing_transfer_envs=["gitlab"],
    )
    assert sig.transferred_to_new_env is False


def test_layer3_known_hint_not_novel():
    from browsermind_core.learning.reward_layers import is_novel_capability
    assert is_novel_capability("search_query_input") is False
    assert is_novel_capability("auth_password_input") is False


def test_layer3_unknown_hint_is_novel():
    from browsermind_core.learning.reward_layers import is_novel_capability
    assert is_novel_capability("community_upvote_button") is True
    assert is_novel_capability("xyz_never_seen_widget_999") is True


def test_layer3_empty_hint_not_novel():
    from browsermind_core.learning.reward_layers import is_novel_capability
    assert is_novel_capability("") is False


def test_layer4_reuse_count_forwarded():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(reuse_count=7)
    assert sig.reuse_count == 7


def test_layer5_competence_delta():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(baseline_score=0.4, current_score=0.75)
    assert abs(sig.competence_delta - 0.35) < 0.001
    assert sig.baseline_score == 0.4
    assert sig.current_score == 0.75


def test_layer5_no_baseline_none():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal()
    assert sig.competence_delta is None


# ── composite_score ───────────────────────────────────────────────────────────

def test_composite_zero_when_no_signals():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal()
    assert sig.composite_score == 0.0


def test_composite_task_complete_adds_weight():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    sig = compute_reward_signal(task_completed=True)
    assert sig.composite_score >= 0.2


def test_composite_transfer_adds_more_than_task():
    from browsermind_core.learning.reward_layers import compute_reward_signal
    s_task_only = compute_reward_signal(task_completed=True)
    s_transfer = compute_reward_signal(
        task_completed=True,
        current_env_key="gitlab",
        training_envs=["github"],
    )
    assert s_transfer.composite_score > s_task_only.composite_score


def test_composite_positive_delta_adds_most():
    from browsermind_core.learning.reward_layers import RewardSignal
    sig = RewardSignal(
        task_completed=True,
        transferred_to_new_env=True,
        is_novel=True,
        reuse_count=4,
        competence_delta=0.40,
    )
    assert sig.composite_score > 1.0  # can exceed 1.0 intentionally


# ── CapabilityRecord: reuse_count and is_novel ────────────────────────────────

def test_capability_record_has_reuse_count_and_is_novel():
    from browsermind_core.learning.capability_record import CapabilityRecord
    import dataclasses
    fields = {f.name for f in dataclasses.fields(CapabilityRecord)}
    assert "reuse_count" in fields
    assert "is_novel" in fields


def test_capability_record_reuse_count_default_zero():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["ACT"])
    assert r.reuse_count == 0


def test_capability_record_record_reuse_increments():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["ACT"])
    r.record_reuse("github")
    r.record_reuse("gitlab")
    assert r.reuse_count == 2
    assert "github" in r.transfer_envs
    assert "gitlab" in r.transfer_envs


def test_capability_record_from_dict_old_record_no_reuse_fields():
    from browsermind_core.learning.capability_record import CapabilityRecord
    old = {
        "invariant_hash": "abcd1234abcd1234",
        "invariants": ["AUTHENTICATE"],
        "first_seen": "2026-06-01T00:00:00+00:00",
        "last_seen": "2026-06-01T00:00:00+00:00",
    }
    r = CapabilityRecord.from_dict(old)
    assert r.reuse_count == 0
    assert r.is_novel is None


# ── Source-level: replay_engine wires novelty and reuse ──────────────────────

def test_replay_engine_calls_is_novel_capability():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "is_novel_capability" in src
    assert "record_reuse" in src
    assert "reuse_count" in src
