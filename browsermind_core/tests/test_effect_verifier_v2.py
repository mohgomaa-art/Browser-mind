"""
Unit tests for EffectVerifier v2 (#97):
  - 9-priority diff system
  - url_transition → TRANSITION_SUCCESS
  - return_to_origin → FAILED (NAVIGATION_LOOP)
  - form_validation_fail → FAILED (FORM_VALIDATION_REJECTED)
  - alert_error → FAILED (EXPLICIT_ERROR_RESPONSE)
  - alert_success → SUCCESS
  - dom_mutation → SUCCESS
  - content_change → SUCCESS
  - no_signal → FAILED
  - quality_score field presence
  - outcome_label and failure_reason mapping

Tests use EffectSnapshot/EffectVerifier directly — no Playwright required.
"""
from __future__ import annotations

import pytest

from browsermind_core.exploration.effect_verifier import (
    EffectVerifier,
    EffectSnapshot,
    EffectVerdict,
)


START_URL = "https://example.com/"


def _snap(**kwargs) -> EffectSnapshot:
    """Build a minimal valid EffectSnapshot with sensible defaults."""
    defaults = dict(
        url="https://example.com/",
        title="Example",
        element_count=50,
        list_item_count=0,
        result_count=0,
        alert_count=0,
        success_alert_count=0,
        error_alert_count=0,
        validation_count=0,
        heading_count=2,
        form_count=0,
        content_snippet="hello world content",
        content_hash="stablehash123",
        snapshot_ok=True,
    )
    defaults.update(kwargs)
    return EffectSnapshot(**defaults)


# ── url_transition → TRANSITION_SUCCESS ──────────────────────────────────────

def test_url_transition_success():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/search")
    after = _snap(url="https://example.com/results")
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "url_transition"
    assert verdict.has_effect is True
    assert verdict.outcome_label == "TRANSITION_SUCCESS"
    assert 0.0 <= verdict.quality_score <= 1.0


def test_url_transition_beats_dom_mutation():
    """URL change takes priority over any DOM change."""
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/form", element_count=10)
    after = _snap(url="https://example.com/thanks", element_count=99)
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "url_transition"


# ── return_to_origin → FAILED (NAVIGATION_LOOP) ───────────────────────────────

def test_return_to_origin_detects_loop():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/checkout")
    after = _snap(url="https://example.com/")   # back to start
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "return_to_origin"
    assert verdict.has_effect is False
    assert verdict.outcome_label == "FAILED"
    assert verdict.failure_reason == "NAVIGATION_LOOP"


def test_no_loop_when_moving_away_from_origin():
    """Forward navigation from origin → not a loop."""
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/")
    after = _snap(url="https://example.com/dashboard")
    verdict = verifier.diff(before, after)

    assert verdict.effect_type != "return_to_origin"
    assert verdict.has_effect is True


# ── form_validation_fail → FAILED ────────────────────────────────────────────

def test_form_validation_fail():
    """Validation errors appearing on a form page → form_validation_fail."""
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/register", form_count=1, validation_count=0)
    after = _snap(url="https://example.com/register", form_count=1, validation_count=3)
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "form_validation_fail"
    assert verdict.has_effect is False
    assert verdict.outcome_label == "FAILED"
    assert verdict.failure_reason == "FORM_VALIDATION_REJECTED"


# ── alert_error → FAILED (EXPLICIT_ERROR_RESPONSE) ───────────────────────────

def test_alert_error_maps_to_explicit_error():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(error_alert_count=0)
    after = _snap(error_alert_count=1)
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "alert_error"
    assert verdict.has_effect is False
    assert verdict.outcome_label == "FAILED"
    assert verdict.failure_reason == "EXPLICIT_ERROR_RESPONSE"


# ── alert_success → SUCCESS ────────────────────────────────────────────────────

def test_alert_success_maps_to_success():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(success_alert_count=0)
    after = _snap(success_alert_count=1)
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "alert_success"
    assert verdict.has_effect is True
    assert verdict.outcome_label == "SUCCESS"


# ── dom_mutation → SUCCESS ────────────────────────────────────────────────────

def test_dom_mutation_from_results():
    """New result elements appearing → dom_mutation SUCCESS."""
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(result_count=0)
    after = _snap(result_count=10)
    verdict = verifier.diff(before, after)

    assert verdict.effect_type == "dom_mutation"
    assert verdict.has_effect is True
    assert verdict.outcome_label == "SUCCESS"


def test_dom_mutation_from_element_change():
    """Large element count shift → dom_mutation SUCCESS."""
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(element_count=10)
    after = _snap(element_count=25)   # +150% > 5% threshold
    verdict = verifier.diff(before, after)

    assert verdict.has_effect is True
    assert verdict.outcome_label == "SUCCESS"


# ── content_change → SUCCESS ──────────────────────────────────────────────────

def test_content_change_success():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(content_hash="before_hash")
    after = _snap(content_hash="after_hash")
    verdict = verifier.diff(before, after)

    assert verdict.has_effect is True
    assert verdict.effect_type in ("content_change", "dom_mutation")
    assert verdict.outcome_label == "SUCCESS"


# ── no_signal → FAILED ────────────────────────────────────────────────────────

def test_no_signal_when_nothing_changes():
    verifier = EffectVerifier(start_url=START_URL)
    snap = _snap()
    verdict = verifier.diff(snap, snap)

    assert verdict.effect_type == "no_signal"
    assert verdict.has_effect is False
    assert verdict.outcome_label == "FAILED"


# ── quality_score ─────────────────────────────────────────────────────────────

def test_quality_score_present_on_all_verdicts():
    verifier = EffectVerifier(start_url=START_URL)
    snap = _snap()
    verdict = verifier.diff(snap, snap)

    assert hasattr(verdict, "quality_score")
    assert isinstance(verdict.quality_score, float)
    assert 0.0 <= verdict.quality_score <= 1.0


def test_quality_score_url_transition_highest():
    """URL transitions should score higher than no_signal."""
    verifier = EffectVerifier(start_url=START_URL)
    snap_same = _snap()
    snap_nav = _snap(url="https://example.com/success")

    no_signal = verifier.diff(snap_same, snap_same)
    transition = verifier.diff(snap_same, snap_nav)

    assert transition.quality_score > no_signal.quality_score


def test_quality_score_degraded_snapshot():
    """snapshot_ok=False should yield quality_score=0.0."""
    verifier = EffectVerifier(start_url=START_URL)
    bad = _snap(snapshot_ok=False)
    verdict = verifier.diff(bad, bad)

    assert verdict.quality_score == 0.0


# ── failure_reason semantics ──────────────────────────────────────────────────

def test_failure_reason_none_on_success():
    verifier = EffectVerifier(start_url=START_URL)
    before = _snap(url="https://example.com/search")
    after = _snap(url="https://example.com/results")
    verdict = verifier.diff(before, after)

    assert verdict.has_effect is True
    assert verdict.failure_reason is None


def test_failure_reason_no_visible_signal():
    verifier = EffectVerifier(start_url=START_URL)
    snap = _snap()
    verdict = verifier.diff(snap, snap)
    assert verdict.failure_reason == "NO_VISIBLE_SIGNAL"


# ── outcome_label parametric ─────────────────────────────────────────────────

@pytest.mark.parametrize("before_url,after_url,before_results,after_results,expected_label", [
    # URL transition
    ("https://ex.com/a", "https://ex.com/b", 0, 0, "TRANSITION_SUCCESS"),
    # No change at all
    ("https://ex.com/a", "https://ex.com/a", 0, 0, "FAILED"),
    # Results appeared — dom_mutation → SUCCESS
    ("https://ex.com/s", "https://ex.com/s", 0, 5, "SUCCESS"),
])
def test_outcome_label(before_url, after_url, before_results, after_results, expected_label):
    verifier = EffectVerifier(start_url="https://ex.com/")
    before = _snap(url=before_url, result_count=before_results)
    after = _snap(url=after_url, result_count=after_results)
    verdict = verifier.diff(before, after)
    assert verdict.outcome_label == expected_label


# ── set_start_url helper ──────────────────────────────────────────────────────

def test_set_start_url():
    verifier = EffectVerifier()
    verifier.set_start_url("https://example.com/")
    before = _snap(url="https://example.com/checkout")
    after = _snap(url="https://example.com/")
    verdict = verifier.diff(before, after)
    assert verdict.effect_type == "return_to_origin"
