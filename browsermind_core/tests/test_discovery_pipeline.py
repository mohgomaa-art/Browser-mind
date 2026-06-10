"""Tests for the discovery pipeline — vocab expansion, importance scoring, pause/resume."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── 1. normalize() takes 3 positional args (not keyword role/name) ────────────

def test_extract_completed_intents_bug_fix():
    """normalize() must be called with 3 positional args; keyword args TypeError is gone."""
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer(collapse_level=1)
    # This should NOT raise
    result = norm.normalize("click", "button", "Sign in")
    assert isinstance(result, str)
    assert len(result) > 0


# ── 2. SUCCESS outcomes yield intents; FAILED outcomes are ignored ─────────────

def test_extract_completed_intents_returns_intents():
    """SUCCESS and TRANSITION_SUCCESS outcomes land in the completed set."""
    from browsermind_core.exploration.exploration_harness import _extract_completed_intents

    class FakeAttr:
        def __init__(self, outcome, action_type="click", role="button", name="Sign in"):
            self.actual_outcome = outcome
            self.action_type = action_type
            self.target_role = role
            self.target_name = name

    attrs = [
        FakeAttr("SUCCESS",            action_type="click",  role="button",  name="Sign in"),
        FakeAttr("TRANSITION_SUCCESS", action_type="fill",   role="textbox", name="search query"),
        FakeAttr("FAILED",             action_type="click",  role="button",  name="does not count"),
    ]
    intents = _extract_completed_intents(attrs)
    assert len(intents) >= 1
    assert not any("does not count" in i for i in intents)


def test_extract_completed_intents_skips_failed():
    """FAILED outcomes do NOT appear in the completed intent set."""
    from browsermind_core.exploration.exploration_harness import _extract_completed_intents

    class FakeAttr:
        def __init__(self, outcome):
            self.actual_outcome = outcome
            self.action_type = "click"
            self.target_role = "button"
            self.target_name = "fail target"

    intents = _extract_completed_intents([FakeAttr("FAILED"), FakeAttr("FAILED")])
    assert len(intents) == 0


# ── 3. New vocabulary patterns ────────────────────────────────────────────────

def test_normalizer_upload_file_pattern():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer(collapse_level=0)
    assert norm.normalize("click", "button", "Upload File") == "UPLOAD_FILE"
    assert norm.normalize("click", "button", "Attach file") == "UPLOAD_FILE"


def test_normalizer_accept_consent_pattern():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer(collapse_level=0)
    assert norm.normalize("click", "button", "Accept all cookies") == "ACCEPT_CONSENT"
    assert norm.normalize("click", "button", "I agree") == "ACCEPT_CONSENT"


def test_normalizer_add_to_cart_pattern():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer(collapse_level=0)
    assert norm.normalize("click", "button", "Add to cart") == "ADD_TO_CART"
    assert norm.normalize("click", "button", "Add to bag") == "ADD_TO_CART"


def test_normalizer_next_page_pattern():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer(collapse_level=0)
    assert norm.normalize("click", "button", "Load more") == "NEXT_PAGE"
    assert norm.normalize("click", "button", "Show more results") == "NEXT_PAGE"


def test_normalizer_known_vocab_size():
    """Level-0 vocabulary must have expanded to at least 30 named patterns."""
    from browsermind_core.representation.primitive_normalizer import _KNOWN_L0
    assert len(_KNOWN_L0) >= 30


# ── 4. Importance scoring ─────────────────────────────────────────────────────

def test_hypothesis_importance_low_value_penalized():
    """Hypotheses about cookie consent are penalized below baseline."""
    from browsermind_core.learning.capability_hypothesis import make_hypothesis

    hyp = make_hypothesis(
        invariants=["ACCEPT_CONSENT", "DECLINE_CONSENT", "CLOSE_DIALOG"],
        env_key="site_a",
        source="exploration",
    )
    score = hyp.compute_importance()
    # Noise-heavy pattern: all three invariants contain low-value keywords
    assert score < 1.0


def test_hypothesis_importance_transfer_bonus():
    """transfer_successes > 0 adds 0.5 bonus to importance."""
    from browsermind_core.learning.capability_hypothesis import make_hypothesis

    # High frequency, single environment → low transfer_diversity → base score < 1.5
    # so the +0.5 bonus is measurable (not capped away).
    def make_high_freq(with_transfer: bool):
        hyp = make_hypothesis(
            invariants=["SUBMIT_FORM", "SELECT_OPTION"],
            env_key="site_a",
            source="exploration",
        )
        hyp.frequency = 20          # seen many times
        hyp.environments = ["site_a"]  # but only one site → low diversity
        if with_transfer:
            hyp.transfer_successes = 3
        return hyp

    score_base  = make_high_freq(False).compute_importance()
    score_bonus = make_high_freq(True).compute_importance()
    assert score_bonus > score_base


# ── 5. Pause / resume mechanics ───────────────────────────────────────────────

def test_replay_engine_has_pause_event():
    """ReplayEngine must expose _pause_event, pause(), resume(), is_paused."""
    from browsermind_core.runtime.replay_engine import ReplayEngine
    import asyncio

    mock_session = MagicMock()
    mock_session.store_dir = "/tmp/fake_store"

    engine = ReplayEngine(auth_session=mock_session)

    # Initially not paused
    assert hasattr(engine, "_pause_event")
    assert hasattr(engine, "pause")
    assert hasattr(engine, "resume")
    assert hasattr(engine, "is_paused")
    assert engine.is_paused is False

    engine.pause("unit test reason")
    assert engine.is_paused is True
    assert engine._pause_reason == "unit test reason"

    engine.resume()
    assert engine.is_paused is False
    assert engine._pause_reason == ""
