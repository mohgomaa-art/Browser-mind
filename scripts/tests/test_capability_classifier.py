"""
Unit tests for CapabilityClassifier — WR-IR
Run: python -m pytest scripts/tests/test_capability_classifier.py -v
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.recorder.capability_classifier import CapabilityClassifier

clf = CapabilityClassifier()


def make_payload(role="", selector="", name="", placeholder="", text=""):
    return {
        "target_role": role,
        "target_name": name,
        "target_selector": selector,
        "descriptor": {"placeholder": placeholder, "text_content": text},
    }


# ---------------------------------------------------------------------------
# capability_hint
# ---------------------------------------------------------------------------

def test_search_by_type():
    p = make_payload(role="searchbox", selector="input[type='search']")
    r = clf.classify(p)
    assert r["capability_hint"] == "search_query_input"

def test_search_by_role_searchbox():
    p = make_payload(role="searchbox")
    r = clf.classify(p)
    assert r["capability_hint"] == "search_query_input"

def test_search_by_placeholder():
    p = make_payload(role="textbox", name="search", placeholder="Search")
    r = clf.classify(p)
    assert r["capability_hint"] == "search_query_input"

def test_auth_email():
    p = make_payload(role="textbox", selector="input[type='email']")
    r = clf.classify(p)
    assert r["capability_hint"] == "auth_email_input"

def test_auth_password():
    p = make_payload(selector="input[type='password']")
    r = clf.classify(p)
    assert r["capability_hint"] == "auth_password_input"

def test_auth_username():
    p = make_payload(role="textbox", name="username")
    r = clf.classify(p)
    assert r["capability_hint"] == "auth_username_input"

def test_search_submit_button():
    p = make_payload(role="button", name="Search")
    r = clf.classify(p)
    assert r["capability_hint"] == "search_submit"

def test_login_submit_button():
    p = make_payload(role="button", name="Sign in")
    r = clf.classify(p)
    assert r["capability_hint"] == "auth_submit"

def test_form_submit_type():
    p = make_payload(role="button", selector="input[type='submit']")
    r = clf.classify(p)
    assert r["capability_hint"] == "form_submit"

def test_generic_button_fallback():
    p = make_payload(role="button", name="Random Thing")
    r = clf.classify(p)
    assert r["capability_hint"] == "generic_button"

def test_navigation_link():
    p = make_payload(role="link", name="Home")
    r = clf.classify(p)
    assert r["capability_hint"] == "navigation_link"


# ---------------------------------------------------------------------------
# workflow_role
# ---------------------------------------------------------------------------

def test_workflow_role_global_search():
    p = make_payload(role="searchbox")
    r = clf.classify(p, capability_context="header nav")
    assert r["workflow_role"] == "global_search"

def test_workflow_role_package_search():
    p = make_payload(role="searchbox")
    r = clf.classify(p, capability_context="pypi package search")
    assert r["workflow_role"] == "package_search"

def test_workflow_role_repo_search():
    p = make_payload(role="searchbox")
    r = clf.classify(p, capability_context="search repositories code")
    assert r["workflow_role"] == "repository_search"

def test_workflow_role_login_password():
    p = make_payload(selector="input[type='password']")
    r = clf.classify(p)
    assert r["workflow_role"] == "login_password"

def test_workflow_role_login_email():
    p = make_payload(role="textbox", selector="input[type='email']")
    r = clf.classify(p)
    assert r["workflow_role"] == "login_email"


# ---------------------------------------------------------------------------
# ordinal
# ---------------------------------------------------------------------------

def test_ordinal_preserved():
    p = make_payload(role="textbox", name="username")
    r = clf.classify(p, capability_context="login form", capability_ordinal=2)
    assert r["capability_ordinal"] == 2

def test_ordinal_default_is_1():
    p = make_payload(role="textbox", name="username")
    r = clf.classify(p)
    assert r["capability_ordinal"] == 1


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [
        test_search_by_type, test_search_by_role_searchbox, test_search_by_placeholder,
        test_auth_email, test_auth_password, test_auth_username,
        test_search_submit_button, test_login_submit_button, test_form_submit_type,
        test_generic_button_fallback, test_navigation_link,
        test_workflow_role_global_search, test_workflow_role_package_search,
        test_workflow_role_repo_search,
        test_workflow_role_login_password, test_workflow_role_login_email,
        test_ordinal_preserved, test_ordinal_default_is_1,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed}/{passed+failed} passed")
    if failed:
        sys.exit(1)
