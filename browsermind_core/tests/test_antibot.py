"""Tests for anti-bot infrastructure and PrimitiveNormalizer instrumentation.

Covers:
  - SiteEntry.anti_bot_tier default value
  - SiteEntry.to_dict() includes anti_bot_tier
  - SiteEntry.from_dict() round-trip preserves anti_bot_tier
  - FailureAttribution.actual_outcome accepts BOT_DETECTED
  - PrimitiveNormalizer logger captures fallback records
  - PrimitiveNormalizer known vocab items are NOT flagged as fallback
"""
from __future__ import annotations

import pytest


# ── SiteEntry.anti_bot_tier ───────────────────────────────────────────────────

def test_site_entry_anti_bot_tier_default():
    from browsermind_core.registry.site_registry import SiteEntry
    entry = SiteEntry(key="test", url="https://example.com", category="unknown_frontier")
    assert entry.anti_bot_tier == 0


def test_site_entry_anti_bot_tier_set():
    from browsermind_core.registry.site_registry import SiteEntry
    entry = SiteEntry(key="cf", url="https://dash.cloudflare.com", category="cloud_platforms",
                      anti_bot_tier=3)
    assert entry.anti_bot_tier == 3


def test_site_entry_to_dict_includes_anti_bot_tier():
    from browsermind_core.registry.site_registry import SiteEntry
    entry = SiteEntry(key="test", url="https://example.com", category="search_engines",
                      anti_bot_tier=2)
    d = entry.to_dict()
    assert "anti_bot_tier" in d
    assert d["anti_bot_tier"] == 2


def test_site_entry_from_dict_roundtrip():
    from browsermind_core.registry.site_registry import SiteEntry
    original = SiteEntry(key="x", url="https://x.com", category="social_networks",
                         anti_bot_tier=2)
    restored = SiteEntry.from_dict(original.to_dict())
    assert restored.anti_bot_tier == 2
    assert restored.key == "x"


def test_site_entry_from_dict_backward_compat():
    from browsermind_core.registry.site_registry import SiteEntry
    d = {"key": "old", "url": "https://old.com", "category": "unknown_frontier"}
    entry = SiteEntry.from_dict(d)
    assert entry.anti_bot_tier == 0


def test_seed_entries_have_correct_tiers():
    from browsermind_core.registry.site_registry import SITE_REGISTRY
    assert SITE_REGISTRY["twitter_x"].anti_bot_tier == 2
    assert SITE_REGISTRY["linkedin"].anti_bot_tier == 2
    assert SITE_REGISTRY["cloudflare"].anti_bot_tier == 3
    assert SITE_REGISTRY["coinbase"].anti_bot_tier == 3
    assert SITE_REGISTRY["github"].anti_bot_tier == 0   # no bot protection


# ── FailureAttribution.BOT_DETECTED ──────────────────────────────────────────

def test_failure_attribution_bot_detected():
    from browsermind_core.ontology.p1_schemas import FailureAttribution
    fa = FailureAttribution(
        step_seq=1,
        action_type="click",
        role="button",
        name="Submit",
        predicted_tier="HIGH",
        predicted_score=0.9,
        actual_outcome="BOT_DETECTED",
        failure_reason="cloudflare_challenge",
    )
    assert fa.actual_outcome == "BOT_DETECTED"
    assert fa.failure_reason == "cloudflare_challenge"


def test_failure_attribution_existing_outcomes_unchanged():
    from browsermind_core.ontology.p1_schemas import FailureAttribution
    for outcome in ("SUCCESS", "FAILED", "TRANSITION_SUCCESS", "AMBIGUOUS_IDENTITY", "ASK"):
        fa = FailureAttribution(
            step_seq=0, action_type="click", role="button", name="x",
            predicted_tier="HIGH", predicted_score=0.5,
            actual_outcome=outcome,
        )
        assert fa.actual_outcome == outcome


# ── PrimitiveNormalizer logger ────────────────────────────────────────────────

def test_primitive_normalizer_logs_fallback():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

    records = []
    norm = PrimitiveNormalizer(logger=records.append)

    # "hover" is not handled by any known-vocab branch → fallback code path
    result = norm.normalize("hover", "div", "tooltip content")
    assert len(records) == 1
    rec = records[0]
    assert rec["action_type"] == "hover"
    assert rec["result"] == result
    assert rec["is_fallback"] is True


def test_primitive_normalizer_known_vocab_not_fallback():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

    records = []
    norm = PrimitiveNormalizer(logger=records.append)

    norm.normalize("click", "button", "Sign in")   # → SIGN_IN
    assert records[-1]["result"] == "SIGN_IN"
    assert records[-1]["is_fallback"] is False


def test_primitive_normalizer_no_logger_does_not_error():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
    norm = PrimitiveNormalizer()
    result = norm.normalize("fill", "textbox", "email")
    assert isinstance(result, str)


def test_primitive_normalizer_logger_failure_silent():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

    def bad_logger(_):
        raise RuntimeError("logger exploded")

    norm = PrimitiveNormalizer(logger=bad_logger)
    result = norm.normalize("click", "button", "Sign in")
    assert result == "SIGN_IN"  # result is unaffected by logger failure


def test_primitive_normalizer_fallback_rate_measurement():
    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

    records = []
    norm = PrimitiveNormalizer(logger=records.append)

    actions = [
        ("click", "button", "Sign in"),         # known → SIGN_IN (not fallback)
        ("fill", "textbox", "email"),            # known → AUTHENTICATE (not fallback)
        ("hover", "div", "tooltip"),             # fallback: hover is unhandled
        ("scroll", "main", "page content"),      # fallback: scroll is unhandled
        ("click", "button", "Star"),             # known → TOGGLE_STAR (not fallback)
    ]
    for args in actions:
        norm.normalize(*args)

    fallback_count = sum(1 for r in records if r["is_fallback"])
    total = len(records)
    fallback_rate = fallback_count / total
    assert total == 5
    assert fallback_count == 2
    assert abs(fallback_rate - 0.4) < 0.01
