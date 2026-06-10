"""
Runtime ABAC Policy Engine.

Persona-UUID-keyed, default-deny on sensitive capabilities, persistable.
Gates step execution inside replay_engine via enforce().
"""
import json
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Union


class PolicyDecision(Enum):
    ALLOW = "ALLOW"
    ASK = "ASK"
    DENY = "DENY"


class PolicyRejectionError(Exception):
    pass


class PolicyInterventionRequired(Exception):
    pass


# Default-DENY: sensitive capabilities that must be explicitly granted.
SENSITIVE_DENY = frozenset({
    "checkout",
    "payment",
    "delete_account",
    "share_pii",
    "purchase",
    "confirm_order",
    "payment_card_input",
    "payment_card_cvv",
    "payment_card_number",
})

# Default-ASK: capabilities requiring human approval.
SENSITIVE_ASK = frozenset({
    "auth_password_input",
    "submit",
    "terms_acceptance",
    "age_gate",
    "captcha",
    "verification",
    "otp",
})

# Default-ALLOW: known-safe capabilities.
SAFE_ALLOW = frozenset({
    "search_query_input",
    "search",
    "navigation",
    "filter",
    "read",
})


class PolicyEngine:
    """
    ABAC policy evaluator.

    Persona keys may be UUIDs or string names; normalized via str().
    Rules: {persona_id_str: {capability_hint: "ALLOW"|"ASK"|"DENY"}}.
    """

    NAMESPACE = "policy"
    KEY = "persona_rules"

    def __init__(self, store_dir: Optional[Union[str, Path]] = None):
        self.store_dir = Path(store_dir) if store_dir is not None else None
        self.rules: Dict[str, Dict[str, PolicyDecision]] = {}
        if self.store_dir is not None:
            self._load()

    def _rules_path(self) -> Path:
        assert self.store_dir is not None
        return self.store_dir / self.NAMESPACE / f"{self.KEY}.json"

    def _load(self) -> None:
        path = self._rules_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for persona_id, caps in raw.items():
            if not isinstance(caps, dict):
                continue
            self.rules[persona_id] = {}
            for cap, decision_str in caps.items():
                try:
                    self.rules[persona_id][cap] = PolicyDecision(decision_str)
                except ValueError:
                    continue

    def _persist(self) -> None:
        if self.store_dir is None:
            return
        path = self._rules_path()
        os.makedirs(path.parent, exist_ok=True)
        serializable = {
            pid: {cap: dec.value for cap, dec in caps.items()}
            for pid, caps in self.rules.items()
        }
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp, path)

    @staticmethod
    def _key(persona_id) -> str:
        return str(persona_id)

    def evaluate(self, persona_id, capability_hint: Optional[str]) -> PolicyDecision:
        if not capability_hint:
            return PolicyDecision.ALLOW

        pid = self._key(persona_id)
        persona_rules = self.rules.get(pid, {})
        if capability_hint in persona_rules:
            return persona_rules[capability_hint]

        if capability_hint in SENSITIVE_DENY:
            return PolicyDecision.DENY
        if capability_hint in SENSITIVE_ASK:
            return PolicyDecision.ASK
        if capability_hint in SAFE_ALLOW:
            return PolicyDecision.ALLOW

        return PolicyDecision.ALLOW

    def enforce(self, persona_id, capability_hint: Optional[str]) -> None:
        decision = self.evaluate(persona_id, capability_hint)
        if decision == PolicyDecision.DENY:
            raise PolicyRejectionError(
                f"Action '{capability_hint}' is DENIED for persona '{persona_id}'."
            )
        if decision == PolicyDecision.ASK:
            raise PolicyInterventionRequired(
                f"Action '{capability_hint}' requires approval for persona '{persona_id}'. (ASK)"
            )

    def set_rule(self, persona_id, capability_hint: str, decision: PolicyDecision) -> None:
        if not capability_hint:
            raise ValueError("capability_hint required")
        if not isinstance(decision, PolicyDecision):
            decision = PolicyDecision(decision)
        pid = self._key(persona_id)
        self.rules.setdefault(pid, {})[capability_hint] = decision
        self._persist()

    def grant(self, persona_id, capability_hint: str) -> None:
        self.set_rule(persona_id, capability_hint, PolicyDecision.ALLOW)

    def deny(self, persona_id, capability_hint: str) -> None:
        self.set_rule(persona_id, capability_hint, PolicyDecision.DENY)
