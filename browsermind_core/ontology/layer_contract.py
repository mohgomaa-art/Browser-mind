"""
layer_contract.py — Typed boundary contracts for BrowserMind OS layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FailureSeverity(Enum):
    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"
    FATAL = "fatal"


@dataclass
class FailureMode:
    code: str
    description: str
    severity: FailureSeverity
    recovery: Optional[str] = None


@dataclass
class LayerContract:
    """
    Typed boundary contract between OS layers.

    Declares input/output schema, failure modes, and recovery semantics.
    """
    name: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    failure_modes: List[FailureMode] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    def failure_severity(self, code: str) -> FailureSeverity:
        for fm in self.failure_modes:
            if fm.code == code:
                return fm.severity
        return FailureSeverity.RECOVERABLE

    def is_fatal(self, code: str) -> bool:
        return self.failure_severity(code) == FailureSeverity.FATAL


# Canonical contracts for each layer that has formal boundaries

L5_EXECUTOR_CONTRACT = LayerContract(
    name="L5_Executor",
    version="2.0",
    input_schema={
        "action_type": "str",
        "locator": "Optional[Locator]",
        "value": "Optional[str]",
        "url": "Optional[str]",
        "page": "Page",
        "profile": "Optional[BehaviorProfile]",
    },
    output_schema={
        "success": "bool",
        "verdict": "Optional[EffectVerdict]",
        "reach_result": "Optional[ReachResult]",
        "error": "Optional[str]",
        "duration_ms": "int",
        "failed_phase": "Optional[str]",
    },
    failure_modes=[
        FailureMode("REACH_BLOCKED", "Element blocked by overlay", FailureSeverity.RECOVERABLE,
                    "dismiss_overlay or scroll"),
        FailureMode("EXECUTION_TIMEOUT", "Action timed out", FailureSeverity.RECOVERABLE,
                    "retry or skip"),
        FailureMode("ELEMENT_DETACHED", "Locator detached from DOM", FailureSeverity.RECOVERABLE,
                    "re-resolve locator"),
        FailureMode("PAGE_CRASH", "Browser page crashed", FailureSeverity.FATAL, None),
        FailureMode("UNKNOWN_ACTION", "Action type not in registry", FailureSeverity.FATAL, None),
    ],
    dependencies=["L4_TargetResolver", "L3_Browser"],
)

L6_VERIFIER_CONTRACT = LayerContract(
    name="L6_Verifier",
    version="2.0",
    input_schema={
        "page": "Page",
        "before_snapshot": "EffectSnapshot",
        "spec": "Optional[VerificationSpec]",
        "expected_effects": "Optional[List[str]]",
    },
    output_schema={
        "passed": "bool",
        "score": "float",
        "layer_results": "Dict[str, VerificationResult]",
        "failures": "List[str]",
        "duration_ms": "int",
    },
    failure_modes=[
        FailureMode("SNAPSHOT_FAILED", "Could not capture DOM state", FailureSeverity.DEGRADED,
                    "use partial evidence"),
        FailureMode("CONDITION_TIMEOUT", "Verification timed out", FailureSeverity.RECOVERABLE,
                    "extend timeout"),
    ],
    dependencies=["L5_Executor"],
)
