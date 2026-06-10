"""Replay validation experiments — empirical evidence only, no new architecture."""

from browsermind_core.experiments.replay_result import FailureCategory, ReplayResult
from browsermind_core.experiments.failure_taxonomy import classify_failure
from browsermind_core.experiments.report_generator import evaluate_decision_thresholds, generate_summary_report
from browsermind_core.experiments.sites import EXPERIMENT_SITES, GATE_MIN_RESOLUTION, GATE_SITES

# ReplayExperimentHarness is intentionally NOT imported at module level to avoid
# a circular import: harness -> ReplayEngine -> state_verifier -> experiments/__init__.py
# Use: from browsermind_core.experiments.harness import ReplayExperimentHarness
def _get_harness():
    from browsermind_core.experiments.harness import ReplayExperimentHarness
    return ReplayExperimentHarness

__all__ = [
    "FailureCategory",
    "ReplayResult",
    "classify_failure",
    "ReplayExperimentHarness",
    "generate_summary_report",
    "EXPERIMENT_SITES",
]
