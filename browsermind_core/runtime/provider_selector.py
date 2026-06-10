"""
P7D: Evidence-Based Provider Selector

NOT a planner. NOT a hardcoded rule engine.

Reads historical effectiveness data from the ledger and scores each
capable provider using:

    score = success_rate × confidence(n) × (1 / latency_factor)

where:
    confidence(n) = n / (n + CONFIDENCE_PRIOR)  # shrinks toward 0 for low-sample providers
    latency_factor = normalized latency (1.0 = fast, higher = slower)

The AcquisitionRuntime can then sort providers by score before executing them.
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from browsermind_core.ontology.resource_ontology import ResourceClass

# Bayesian prior: number of "pseudo-observations" to stabilize estimates with few samples.
# With CONFIDENCE_PRIOR=5, a provider with 1/1 success gets score ~0.16, not 1.0.
CONFIDENCE_PRIOR = 5

# Latency normalization anchor: providers faster than this get full score.
# Providers slower than this get a small penalty.
FAST_LATENCY_MS = 50.0

@dataclass
class ProviderScore:
    provider_id: str
    score: float
    success_rate: float
    confidence: float
    avg_latency_ms: Optional[float]
    n_attempts: int

class ProviderSelector:
    """
    P7D: Ranks capable providers for a given resource using historical
    effectiveness evidence. Returns a sorted list of ProviderScores.
    """

    def __init__(self, effectiveness_data: Dict[str, Any]):
        """
        effectiveness_data: the content of provider_effectiveness_report.json
        {
          "resume": {
            "vault": {"success_rate": 0.0, "avg_latency_ms": null},
            "drive": {"success_rate": 1.0, "avg_latency_ms": 310.2}
          }, ...
        }
        """
        self._data = effectiveness_data

    def rank(self, resource_key: str, capable_providers: List[str]) -> List[ProviderScore]:
        """
        Given a resource key and a list of capable provider IDs,
        return them ranked by evidence-based score (highest first).

        Providers with no historical data receive a neutral prior score.
        """
        resource_data = self._data.get(resource_key, {})
        scores = []

        for provider_id in capable_providers:
            provider_data = resource_data.get(provider_id)
            
            if provider_data:
                success_rate = provider_data.get("success_rate", 0.0)
                avg_latency_ms = provider_data.get("avg_latency_ms")
                # Estimate n_attempts from success_rate (we don't store it directly,
                # so use confidence prior to express uncertainty)
                n = max(1, round(success_rate * 10))  # heuristic from success_rate magnitude
            else:
                # No evidence yet → use neutral prior (0.5 success, unknown latency)
                success_rate = 0.5
                avg_latency_ms = None
                n = 0

            confidence = n / (n + CONFIDENCE_PRIOR)
            
            if avg_latency_ms is not None and avg_latency_ms > 0:
                latency_factor = 1.0 + math.log(1 + avg_latency_ms / FAST_LATENCY_MS)
            else:
                latency_factor = 1.0  # Unknown latency = no penalty

            score = (success_rate * confidence) / latency_factor

            scores.append(ProviderScore(
                provider_id=provider_id,
                score=round(score, 4),
                success_rate=success_rate,
                confidence=round(confidence, 3),
                avg_latency_ms=avg_latency_ms,
                n_attempts=n
            ))

        # Sort: highest score first. Ties broken by provider_id (deterministic)
        scores.sort(key=lambda s: (-s.score, s.provider_id))
        return scores


class ProviderGapDetector:
    """
    P7D / P7E: Analyzes effectiveness data to detect resources where
    ALL known providers have 0% success rate — indicating a missing
    provider class.
    
    This answers: "What provider classes does the system need but doesn't have?"
    """

    @staticmethod
    def detect_gaps(effectiveness_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a dict of resources with unresolved gaps and a suggested
        provider class hint.
        """
        gaps = {}

        for resource, providers in effectiveness_data.items():
            all_failed = all(
                p.get("success_rate", 0.0) == 0.0
                for p in providers.values()
            )
            if all_failed:
                suggested_class = ProviderGapDetector._suggest_class(resource, providers)
                gaps[resource] = {
                    "providers_attempted": list(providers.keys()),
                    "all_failed": True,
                    "suggested_missing_provider": suggested_class
                }

        return gaps

    @staticmethod
    def _suggest_class(resource: str, providers: Dict) -> str:
        key = resource.lower()
        attempted = set(providers.keys())
        
        if "password" in key or "secret" in key or "token" in key:
            return "SecretProvider (e.g. password manager, OS keychain)"
        if "github" in key or "profile" in key:
            return "SocialIdentityProvider (e.g. OAuth, browser-cached session)"
        if "captcha" in key:
            return "CaptchaProvider (e.g. solver service, human relay)"
        if "drive" not in attempted:
            return "DriveProvider (document not in vault and drive not attempted)"
        return "UnknownProvider — requires investigation"
