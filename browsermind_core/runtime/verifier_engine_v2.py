"""
verifier_engine_v2.py — L6 Verifier: multi-layer post-execution verification.

Pipeline:
  1. SemanticVerifier  — URL + effect type expectations
  2. DomVerifier       — selector presence/absence + text presence/absence
  3. AccessibilityVerifier — ARIA role visibility
  4. StorageVerifier   — localStorage key/value expectations
  5. NetworkVerifier   — HTTP call expectations (optional, requires capture)
  6. VisualVerifier    — SSIM screenshot comparison (optional)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from browsermind_core.runtime.verifier_layers import (
    AccessibilityVerifier,
    DomVerifier,
    NetworkVerifier,
    SemanticVerifier,
    StorageVerifier,
    VerificationLayerResult,
    VisualVerifier,
)

if TYPE_CHECKING:
    from playwright.async_api import Page
    from browsermind_core.exploration.effect_verifier import EffectVerdict


@dataclass
class VerificationSpec:
    """Input spec for VerifierPipeline.verify()."""
    # URL assertions
    expected_url_contains: Optional[str] = None
    expected_url_pattern: Optional[str] = None

    # DOM assertions
    expected_selectors: List[str] = field(default_factory=list)
    forbidden_selectors: List[str] = field(default_factory=list)
    expected_texts: List[str] = field(default_factory=list)
    forbidden_texts: List[str] = field(default_factory=list)

    # Effect type assertions
    expected_effects: List[str] = field(default_factory=list)

    # ARIA assertions
    expected_aria_roles: List[str] = field(default_factory=list)

    # Network assertions
    expected_network_calls: List[Dict[str, Any]] = field(default_factory=list)
    captured_requests: List[Dict[str, str]] = field(default_factory=list)

    # Storage assertions
    expected_local_storage: Dict[str, str] = field(default_factory=dict)

    # Visual regression
    visual_baseline_path: Optional[str] = None
    visual_selector: Optional[str] = None
    visual_threshold: float = 0.95

    # Meta
    description: str = ""
    min_confidence: float = 0.5


@dataclass
class VerificationReport:
    """Full output of VerifierPipeline.verify()."""
    passed: bool
    score: float                              # 0.0–1.0, weighted average
    duration_ms: int
    layer_results: Dict[str, Dict[str, Any]]  # layer_name → VerificationLayerResult.to_dict()
    failures: List[str]
    description: str = ""
    spec_description: str = ""


class VerifierPipeline:
    """
    Runs all verification layers against the current page state.

    Usage:
        pipeline = VerifierPipeline()
        spec = VerificationSpec(
            expected_url_contains="/dashboard",
            expected_selectors=[".user-menu"],
        )
        report = await pipeline.verify(page, verdict, spec)
    """

    def __init__(self) -> None:
        self._semantic = SemanticVerifier()
        self._dom      = DomVerifier()
        self._aria     = AccessibilityVerifier()
        self._storage  = StorageVerifier()
        self._network  = NetworkVerifier()
        self._visual   = VisualVerifier()

    async def verify(
        self,
        page: "Page",
        verdict: Optional["EffectVerdict"],
        spec: Optional[VerificationSpec] = None,
    ) -> VerificationReport:
        start = time.monotonic()
        spec = spec or VerificationSpec()
        all_failures: List[str] = []
        layer_results: Dict[str, Dict[str, Any]] = {}

        # Layer weights — layers with harder assertions weigh more
        _WEIGHTS = {
            "semantic":      0.25,
            "dom":           0.30,
            "accessibility": 0.15,
            "storage":       0.15,
            "network":       0.10,
            "visual":        0.05,
        }

        # 1. Semantic
        current_url = page.url if page else ""
        sem_result = self._semantic.verify(
            verdict_effect_type=verdict.effect_type if verdict else None,
            expected_effects=spec.expected_effects,
            url_contains=spec.expected_url_contains,
            url_pattern=spec.expected_url_pattern,
            actual_url=current_url,
        )
        layer_results["semantic"] = sem_result.to_dict()
        all_failures.extend(sem_result.failures)

        # 2. DOM
        dom_result = await self._dom.verify(
            page,
            expected_selectors=spec.expected_selectors,
            forbidden_selectors=spec.forbidden_selectors,
            expected_texts=spec.expected_texts,
            forbidden_texts=spec.forbidden_texts,
        )
        layer_results["dom"] = dom_result.to_dict()
        all_failures.extend(dom_result.failures)

        # 3. Accessibility
        aria_result = await self._aria.verify(page, spec.expected_aria_roles)
        layer_results["accessibility"] = aria_result.to_dict()
        all_failures.extend(aria_result.failures)

        # 4. Storage
        storage_result = await self._storage.verify(page, spec.expected_local_storage)
        layer_results["storage"] = storage_result.to_dict()
        all_failures.extend(storage_result.failures)

        # 5. Network
        net_result = self._network.verify(
            spec.expected_network_calls,
            spec.captured_requests,
        )
        layer_results["network"] = net_result.to_dict()
        all_failures.extend(net_result.failures)

        # 6. Visual (best-effort — never blocks)
        try:
            visual_result = await self._visual.verify(
                page,
                baseline_path=spec.visual_baseline_path,
                selector=spec.visual_selector,
                threshold=spec.visual_threshold,
            )
        except Exception:
            visual_result = VerificationLayerResult(True, 1.0, "skipped — exception")
        layer_results["visual"] = visual_result.to_dict()
        all_failures.extend(visual_result.failures)

        # Weighted score
        score = sum(
            _WEIGHTS[name] * layer_results[name]["score"]
            for name in _WEIGHTS
        )
        passed = (
            not all_failures
            and score >= spec.min_confidence
        )

        duration = int((time.monotonic() - start) * 1000)
        return VerificationReport(
            passed=passed,
            score=round(score, 4),
            duration_ms=duration,
            layer_results=layer_results,
            failures=all_failures,
            description=spec.description,
            spec_description=spec.description,
        )
