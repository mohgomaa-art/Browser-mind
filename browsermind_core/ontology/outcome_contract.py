"""
outcome_contract.py — Declarative post-execution expectations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OutcomeContract:
    """
    Declares what a successful action execution should produce.

    Used by VerifierPipeline to produce a VerificationSpec.
    """
    # URL-level expectations
    expected_url_contains: Optional[str] = None
    expected_url_pattern: Optional[str] = None    # regex

    # DOM presence expectations
    expected_selectors: List[str] = field(default_factory=list)
    forbidden_selectors: List[str] = field(default_factory=list)

    # Text expectations
    expected_texts: List[str] = field(default_factory=list)
    forbidden_texts: List[str] = field(default_factory=list)

    # Effect expectations
    expected_effects: List[str] = field(default_factory=list)
    # e.g. ["url_transition", "dom_mutation", "alert_success"]

    # Accessibility expectations
    expected_aria_roles: List[str] = field(default_factory=list)
    # e.g. after a dialog opens: ["dialog"]

    # Network expectations (optional — requires response capture)
    expected_network_calls: List[Dict[str, Any]] = field(default_factory=list)
    # e.g. [{"url_contains": "/api/login", "method": "POST"}]

    # Storage expectations
    expected_local_storage: Dict[str, str] = field(default_factory=dict)

    # Meta
    description: str = ""
    min_confidence: float = 0.5

    def to_verification_spec(self) -> "VerificationSpec":
        from browsermind_core.runtime.verifier_engine_v2 import VerificationSpec
        return VerificationSpec(
            expected_url_contains=self.expected_url_contains,
            expected_url_pattern=self.expected_url_pattern,
            expected_selectors=list(self.expected_selectors),
            forbidden_selectors=list(self.forbidden_selectors),
            expected_texts=list(self.expected_texts),
            forbidden_texts=list(self.forbidden_texts),
            expected_effects=list(self.expected_effects),
            expected_aria_roles=list(self.expected_aria_roles),
            expected_network_calls=list(self.expected_network_calls),
            expected_local_storage=dict(self.expected_local_storage),
            min_confidence=self.min_confidence,
            description=self.description,
        )
