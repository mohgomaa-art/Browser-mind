"""Tests for ExperienceInterpreter.

Covers:
  - ExperiencePattern.matches() — full and partial required sets
  - ExperiencePattern.confidence() — 0.8 floor, 1.0 ceiling
  - ExperienceInterpreter.interpret() — empty input returns []
  - interpret() with known pattern — returns ExperienceLabel
  - interpret() confidence ranking
  - interpret() multiple patterns matched simultaneously
  - interpret() does not match on partial required set
  - interpret() unknown cluster sentinel appended for ≥2 unmatched intents
  - sentinel NOT appended when <2 unmatched intents
  - ExperienceLabel.is_known reflects whether pattern was registered
  - ExperienceLabel.matched_intents correct
  - ExperienceLabel.unmatched_intents correct (only on sentinel)
  - register() adds custom pattern to instance
  - interpret_and_report() returns non-empty string
  - known_experience_names() returns sorted names
  - Source-level: ExperienceInterpreter used in exploration_harness
"""
from __future__ import annotations


# ── ExperiencePattern ─────────────────────────────────────────────────────────

def test_pattern_matches_full_required_set():
    from browsermind_core.exploration.experience_interpreter import ExperiencePattern
    p = ExperiencePattern(
        name="test_auth",
        required_intents=frozenset({"auth_login", "auth_password_input"}),
        optional_intents=frozenset(),
        description="test",
    )
    assert p.matches({"auth_login", "auth_password_input", "extra_intent"})


def test_pattern_does_not_match_partial_required():
    from browsermind_core.exploration.experience_interpreter import ExperiencePattern
    p = ExperiencePattern(
        name="test_auth",
        required_intents=frozenset({"auth_login", "auth_password_input"}),
        optional_intents=frozenset(),
        description="test",
    )
    # Only one of two required intents present
    assert not p.matches({"auth_login"})


def test_pattern_confidence_no_optionals():
    from browsermind_core.exploration.experience_interpreter import ExperiencePattern
    p = ExperiencePattern(
        name="test",
        required_intents=frozenset({"A", "B"}),
        optional_intents=frozenset(),
        description="test",
    )
    conf = p.confidence({"A", "B"})
    # No optionals → 0.8 * 1.0 + 0.2 * 1.0 (max for empty optional set) = 1.0
    assert conf >= 0.8


def test_pattern_confidence_with_all_optionals():
    from browsermind_core.exploration.experience_interpreter import ExperiencePattern
    p = ExperiencePattern(
        name="test",
        required_intents=frozenset({"A"}),
        optional_intents=frozenset({"B", "C"}),
        description="test",
    )
    conf_all = p.confidence({"A", "B", "C"})
    conf_none = p.confidence({"A"})
    assert conf_all > conf_none
    assert conf_all <= 1.0
    assert conf_none >= 0.8


def test_pattern_confidence_zero_when_no_match():
    from browsermind_core.exploration.experience_interpreter import ExperiencePattern
    p = ExperiencePattern(
        name="test",
        required_intents=frozenset({"A", "B"}),
        optional_intents=frozenset(),
        description="test",
    )
    assert p.confidence({"A"}) == 0.0


# ── ExperienceInterpreter.interpret() ─────────────────────────────────────────

def test_interpret_empty_returns_empty():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    assert interp.interpret(set()) == []


def test_interpret_known_pattern_matched():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    labels = interp.interpret({"auth_password_input", "auth_login"})
    names = [lb.name for lb in labels]
    assert "session_authentication" in names


def test_interpret_label_is_known_true():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    labels = interp.interpret({"auth_password_input", "auth_login"})
    known = [lb for lb in labels if lb.name == "session_authentication"]
    assert known
    assert known[0].is_known is True
    assert known[0].confidence >= 0.8


def test_interpret_sorted_by_confidence_descending():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    # Provide intents that match multiple patterns
    intents = {
        "auth_password_input", "auth_login", "auth_mfa_input",  # session_authentication (high conf)
        "content_navigation",                                     # site_navigated (lower conf)
    }
    labels = interp.interpret(intents)
    # Filter known-only to check ordering
    known = [lb for lb in labels if lb.is_known]
    confs = [lb.confidence for lb in known]
    assert confs == sorted(confs, reverse=True)


def test_interpret_partial_required_not_matched():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    # account_registration requires auth_password_input + auth_username_input + form_submit
    # Provide only two of three
    labels = interp.interpret({"auth_password_input", "auth_username_input"})
    names = [lb.name for lb in labels]
    assert "account_registration" not in names


def test_interpret_multiple_patterns_simultaneously():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    # Intents that satisfy both search and navigation patterns
    labels = interp.interpret({
        "search_query_input",
        "content_navigation",
    })
    names = [lb.name for lb in labels if lb.is_known]
    # At minimum search_query_executed should match
    assert "search_query_executed" in names


def test_interpret_unknown_sentinel_for_two_unmatched():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    # Completely unknown intents — no pattern should match
    labels = interp.interpret({"bizarre_action_x", "bizarre_action_y", "bizarre_action_z"})
    sentinel = [lb for lb in labels if not lb.is_known]
    assert len(sentinel) == 1
    assert sentinel[0].name == "unknown_capability_cluster"
    assert len(sentinel[0].unmatched_intents) >= 2


def test_interpret_no_sentinel_for_single_unmatched():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    # One known match + one unmatched intent → no sentinel (< 2 unmatched)
    labels = interp.interpret({"auth_password_input", "auth_login", "one_unknown_intent"})
    sentinel = [lb for lb in labels if not lb.is_known]
    # "one_unknown_intent" is only 1 unmatched, so sentinel should not appear
    assert len(sentinel) == 0


def test_interpret_sentinel_is_last():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    labels = interp.interpret({"novel_x", "novel_y", "novel_z"})
    if len(labels) > 1:
        assert not labels[-1].is_known  # sentinel last


def test_interpret_matched_intents_populated():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    labels = interp.interpret({"auth_password_input", "auth_login"})
    auth_labels = [lb for lb in labels if lb.name == "session_authentication"]
    assert auth_labels
    assert len(auth_labels[0].matched_intents) >= 2


# ── Custom pattern registration ───────────────────────────────────────────────

def test_register_custom_pattern():
    from browsermind_core.exploration.experience_interpreter import (
        ExperienceInterpreter, ExperiencePattern,
    )
    custom = ExperiencePattern(
        name="custom_checkout",
        required_intents=frozenset({"custom_cart", "custom_pay"}),
        optional_intents=frozenset(),
        description="Custom checkout",
        capability_family="form_fill",
    )
    interp = ExperienceInterpreter()
    interp.register(custom)
    labels = interp.interpret({"custom_cart", "custom_pay"})
    names = [lb.name for lb in labels]
    assert "custom_checkout" in names


def test_register_does_not_pollute_global():
    """Instance registration should not affect other instances."""
    from browsermind_core.exploration.experience_interpreter import (
        ExperienceInterpreter, ExperiencePattern,
    )
    custom = ExperiencePattern(
        name="instance_only_pattern",
        required_intents=frozenset({"inst_x", "inst_y"}),
        optional_intents=frozenset(),
        description="Instance only",
    )
    interp1 = ExperienceInterpreter()
    interp1.register(custom)

    interp2 = ExperienceInterpreter()
    labels2 = interp2.interpret({"inst_x", "inst_y"})
    names2 = [lb.name for lb in labels2]
    assert "instance_only_pattern" not in names2


# ── Utility methods ───────────────────────────────────────────────────────────

def test_interpret_and_report_nonempty():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    report = interp.interpret_and_report({"auth_password_input", "auth_login"})
    assert report
    assert "session_authentication" in report or "authentication" in report.lower()


def test_interpret_and_report_no_matches():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    report = interp.interpret_and_report(set())
    assert "no experiences" in report.lower()


def test_known_experience_names_sorted():
    from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter
    interp = ExperienceInterpreter()
    names = interp.known_experience_names()
    assert names == sorted(names)
    assert "session_authentication" in names
    assert "search_query_executed" in names


# ── Source-level: harness uses ExperienceInterpreter ─────────────────────────

def test_harness_imports_experience_interpreter():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "exploration" / "exploration_harness.py"
    ).read_text(encoding="utf-8")
    assert "ExperienceInterpreter" in src
    assert "interpret" in src
    assert "hypothesis_store" in src
