from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.verification import AIRTIGHT, MODERATE, WEAK
from training.verification.task_verifiers import AuthenticationVerifier, NavigationVerifier, SearchVerifier


def _assert(name: str, condition: bool, details: dict) -> None:
    if not condition:
        print(json.dumps({"case": name, "passed": False, "details": details}, indent=2, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"case": name, "passed": True, "strength": details.get("causality_strength")}, ensure_ascii=False))


def main() -> None:
    auth = AuthenticationVerifier()
    result = auth.verify(
        before={
            "url": "https://example.com/login",
            "state_hash": "login-form",
            "cookies": {},
            "dom_text": "Email Password Sign in",
        },
        after={
            "url": "https://example.com/dashboard",
            "state_hash": "dashboard",
            "cookies": {"sessionid": "abc"},
            "dom_text": "Dashboard Welcome Logout",
        },
        trace={
            "actions": [{"type": "click", "target": "Sign in"}],
            "network": [{"method": "POST", "url": "https://example.com/login", "status": 302}],
        },
        goal="log in to example account",
    ).to_dict()
    _assert("auth_airtight", result["gold_eligible"] is True and result["causality_strength"] == AIRTIGHT, result)

    weak_auth = auth.verify(
        before={"url": "https://example.com/login", "state_hash": "login-form", "dom_text": "Sign in"},
        after={"url": "https://example.com/login", "state_hash": "login-form", "dom_text": "Logout Dashboard"},
        trace={},
        goal="log in to example account",
    ).to_dict()
    _assert("auth_outcome_only_rejected", weak_auth["gold_eligible"] is False and weak_auth["causality_strength"] == WEAK, weak_auth)

    search = SearchVerifier()
    weak_search = search.verify(
        before={"url": "https://example.com/search", "state_hash": "same", "dom_text": "Search"},
        after={"url": "https://example.com/search", "state_hash": "same", "dom_text": "Search results for browsermind"},
        trace={"actions": [{"type": "type", "target": "search", "value": "browsermind"}]},
        goal="search for browsermind",
    ).to_dict()
    _assert(
        "search_no_transition_rejected",
        weak_search["gold_eligible"] is False and weak_search["causality_strength"] == MODERATE,
        weak_search,
    )

    nav = NavigationVerifier()
    nav_result = nav.verify(
        before={"url": "https://example.com/home", "state_hash": "home", "dom_text": "Home"},
        after={"url": "https://example.com/docs", "state_hash": "docs", "dom_text": "Documentation BrowserMind docs"},
        trace={
            "actions": [{"type": "click", "target": "Docs"}],
            "network": [{"method": "GET", "url": "https://example.com/docs", "status": 200}],
        },
        goal="navigate to https://example.com/docs",
    ).to_dict()
    _assert("navigation_airtight", nav_result["gold_eligible"] is True and nav_result["causality_strength"] == AIRTIGHT, nav_result)


if __name__ == "__main__":
    main()
