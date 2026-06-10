import uuid

import pytest

from browsermind_core.runtime.policy_engine import (
    PolicyDecision,
    PolicyEngine,
    PolicyInterventionRequired,
    PolicyRejectionError,
)


def test_default_deny_sensitive():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "checkout") == PolicyDecision.DENY
    assert engine.evaluate(persona, "payment_card_number") == PolicyDecision.DENY
    assert engine.evaluate(persona, "delete_account") == PolicyDecision.DENY


def test_default_ask_sensitive():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "auth_password_input") == PolicyDecision.ASK
    assert engine.evaluate(persona, "captcha") == PolicyDecision.ASK
    assert engine.evaluate(persona, "otp") == PolicyDecision.ASK


def test_default_allow_safe():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "search_query_input") == PolicyDecision.ALLOW
    assert engine.evaluate(persona, "navigation") == PolicyDecision.ALLOW
    assert engine.evaluate(persona, "read") == PolicyDecision.ALLOW


def test_persona_grant_overrides_default():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "checkout") == PolicyDecision.DENY
    engine.grant(persona, "checkout")
    assert engine.evaluate(persona, "checkout") == PolicyDecision.ALLOW


def test_persona_deny_overrides_default():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "search") == PolicyDecision.ALLOW
    engine.deny(persona, "search")
    assert engine.evaluate(persona, "search") == PolicyDecision.DENY


def test_rules_persist_across_instances(tmp_path):
    persona = uuid.uuid4()
    e1 = PolicyEngine(store_dir=tmp_path)
    e1.grant(persona, "checkout")
    e1.deny(persona, "search")
    e1.set_rule(persona, "custom_cap", PolicyDecision.ASK)

    e2 = PolicyEngine(store_dir=tmp_path)
    assert e2.evaluate(persona, "checkout") == PolicyDecision.ALLOW
    assert e2.evaluate(persona, "search") == PolicyDecision.DENY
    assert e2.evaluate(persona, "custom_cap") == PolicyDecision.ASK


def test_enforce_raises_correctly():
    engine = PolicyEngine()
    persona = uuid.uuid4()

    with pytest.raises(PolicyRejectionError):
        engine.enforce(persona, "checkout")

    with pytest.raises(PolicyInterventionRequired):
        engine.enforce(persona, "auth_password_input")

    assert engine.enforce(persona, "search_query_input") is None


def test_empty_capability_allows():
    engine = PolicyEngine()
    persona = uuid.uuid4()
    assert engine.evaluate(persona, "") == PolicyDecision.ALLOW
    assert engine.evaluate(persona, None) == PolicyDecision.ALLOW
    assert engine.enforce(persona, "") is None
    assert engine.enforce(persona, None) is None


def test_back_compat_string_persona():
    engine = PolicyEngine()
    assert engine.evaluate("alpha", "search_query_input") == PolicyDecision.ALLOW
    assert engine.evaluate("alpha", "checkout") == PolicyDecision.DENY

    engine.grant("alpha", "checkout")
    assert engine.evaluate("alpha", "checkout") == PolicyDecision.ALLOW

    assert engine.evaluate("beta", "delete_account") == PolicyDecision.DENY
    assert engine.evaluate("beta", "unknown_cap") == PolicyDecision.ALLOW
