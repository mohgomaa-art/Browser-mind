"""ExplorationSpec — template-free exploration directive.

Unlike BatchRunSpec (which requires a pre-written workflow template),
ExplorationSpec describes a site to visit and how much effort to spend.
The ExplorationHarness derives everything else from SiteRegistry.

The self-directed loop
──────────────────────
  CapabilityHypothesisStore.exploration_targets()
    → List[CapabilityHypothesis] (RECURRING / EMERGING)
    → [h.human_hint or h.invariant_hash] → ExplorationSpec.capability_targets
    → ExplorationHarness.run()
    → ExplorationResult.hypothesis_hashes
    → CapabilityHypothesisStore.observe() (new/updated records)
    → next call to exploration_targets() sees updated hypotheses

ExplorationResult.status values
───────────────────────────────
  EXPERIENCED   — at least one known ExperienceLabel was produced
  HYPOTHESISED  — no known experience, but novel intents observed and stored
  EXPLORED      — run completed with no experiences or hypotheses found
  ERROR         — engine raised an exception
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExplorationSpec:
    """Directive for one template-free exploration run.

    Fields
    ──────
    site_key            Key into SITE_REGISTRY. The harness looks up SiteEntry
                        to get the start URL, difficulty, and category.
    budget              Maximum steps the engine may execute before stopping.
                        Compared against len(report.failure_attribution).
    max_depth           Maximum navigation depth from the start URL.
                        Passed to the engine as a step-budget hint.
    capability_targets  Capability hint strings the exploration should prioritise.
                        Populated from CapabilityHypothesisStore.exploration_targets()
                        to implement self-directed exploration.
                        Empty = explore freely with no preference.
    stop_on_experience  Stop early when any of these ExperienceLabel.name values is
                        produced. Useful for "explore until I've authenticated".
    enable_recovery     Forward to the engine to activate recovery strategies.
    label               Human-readable label for logging. Auto-generated if empty.
    """
    site_key: str
    budget: int = 200
    max_depth: int = 5
    capability_targets: List[str] = field(default_factory=list)
    stop_on_experience: List[str] = field(default_factory=list)
    enable_recovery: bool = True
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"explore_{self.site_key}"


@dataclass
class ExplorationResult:
    """Outcome of one ExplorationHarness.run() call.

    Fields
    ──────
    spec                    The spec that produced this result.
    experiences_discovered  ExperienceLabel.name strings the interpreter assigned
                            to the completed intent set. Empty = nothing recognised.
    hypothesis_hashes       invariant_hash values of hypotheses written or updated
                            in CapabilityHypothesisStore during this run.
    steps_executed          Actual step count (≤ spec.budget).
    duration_seconds        Wall-clock time for the full run.
    error                   Error message if the run crashed, else None.
    metadata                Arbitrary annotations set by the harness or caller.
    """
    spec: ExplorationSpec
    experiences_discovered: List[str] = field(default_factory=list)
    hypothesis_hashes: List[str] = field(default_factory=list)
    steps_executed: int = 0
    affordances_executed: int = 0   # execute steps (submit/navigate, not fill)
    verified_effects: int = 0       # steps with SUCCESS or TRANSITION_SUCCESS outcome
    duration_seconds: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True iff the run completed without an engine-level error."""
        return self.error is None

    @property
    def status(self) -> str:
        """Coarse outcome category."""
        if self.error:
            return "ERROR"
        if self.experiences_discovered:
            return "EXPERIENCED"
        if self.hypothesis_hashes:
            return "HYPOTHESISED"
        return "EXPLORED"

    @property
    def novel_hypothesis_count(self) -> int:
        return len(self.hypothesis_hashes)
