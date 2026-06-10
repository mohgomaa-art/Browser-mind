"""Unit tests for State Family Builder v5 (no browser required)."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from training.compiler.state_family_builder import StateFamilyBuilder


def _node(idx: int, role: str, name: str = "") -> dict:
    return {"idx": idx, "role": role, "name": name}


def test_password_login():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "textbox", "Username or email address"),
        _node(2, "textbox", "Password"),
        _node(3, "button", "Sign in"),
    ]
    family, _, conf = builder._classify_and_score(nodes, "form")
    assert family == "login_form", family
    assert conf >= 0.85


def test_password_signup_beats_login_by_terms():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "textbox", "Email"),
        _node(2, "textbox", "Password"),
        _node(3, "textbox", "Confirm password"),
        _node(4, "button", "Create account"),
    ]
    family, _, _ = builder._classify_and_score(nodes, "form")
    assert family == "signup_form", family


def test_change_password_not_signup():
    """4 inputs including confirm must not imply signup without signup signals."""
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "textbox", "Current password"),
        _node(2, "textbox", "New password"),
        _node(3, "textbox", "Confirm password"),
        _node(4, "textbox", "Email"),
        _node(5, "button", "Save changes"),
    ]
    family, _, _ = builder._classify_and_score(nodes, "form")
    assert family == "login_form", family


def test_landing_email_no_password():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "textbox", "Enter your email"),
        _node(2, "textbox", "Enter your email"),
        _node(3, "button", "Sign up for GitHub"),
        _node(4, "button", "Explore the latest tools from Universe 2025"),
        _node(5, "button", "Automate any workflow, from the simple to the complex"),
        _node(6, "button", "Sign in"),  # nav CTA — must not force login_form
        _node(7, "link", "Pricing"),
    ]
    family, _, _ = builder._classify_and_score(nodes, "main")
    assert family == "landing_page", family


def test_search_interface():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "searchbox", "Search"),
        _node(2, "button", "Search"),
    ]
    family, _, conf = builder._classify_and_score(nodes, "search")
    assert family == "search_interface", family
    assert conf >= 0.9


def test_duckduckgo_search_not_article():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "combobox", "Search with DuckDuckGo"),
        _node(2, "button", "Search"),
        _node(3, "button", "A simple, secure password manager"),  # password in button only
        _node(4, "link", "About"),
        _node(5, "link", "Privacy"),
        _node(6, "link", "Terms"),
        _node(7, "link", "Help"),
        _node(8, "link", "Blog"),
    ]
    family, _, _ = builder._classify_and_score(nodes, "main")
    assert family == "search_interface", family


def test_newsletter_waitlist():
    builder = StateFamilyBuilder()
    nodes = [
        _node(1, "textbox", "Email address"),
        _node(2, "button", "Join waitlist"),
    ]
    family, _, _ = builder._classify_and_score(nodes, "main")
    assert family == "newsletter_signup", family


def run():
    tests = [
        test_password_login,
        test_password_signup_beats_login_by_terms,
        test_change_password_not_signup,
        test_landing_email_no_password,
        test_search_interface,
        test_duckduckgo_search_not_article,
        test_newsletter_waitlist,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run()
