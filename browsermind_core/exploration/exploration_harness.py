"""ExplorationHarness — bridges ExplorationSpec to ReplayEngine.

The harness is the machinery that connects:

  ExplorationSpec    (what site, what budget, what capability targets)
        ↓
  SiteRegistry       (start URL, category, difficulty)
        ↓
  _MinimalExplorationTemplate  (navigate-to-URL synthetic template)
        ↓
  engine_factory(site_key) → ReplayEngine.replay()
        ↓
  ExperienceInterpreter     (completed intents → ExperienceLabel list)
        ↓
  CapabilityHypothesisStore  (novel intents → CapabilityHypothesis)
        ↓
  ExplorationResult

Key differences from BatchRunner
─────────────────────────────────
  - No template required: harness creates a minimal navigate-and-explore template
  - Hypothesis feedback loop: novel intents auto-written to CapabilityHypothesisStore
  - Experience labelling: ExperienceInterpreter runs on every result
  - stop_on_experience: early-stop when a target experience is reached
  - Budget enforcement: stops after spec.budget steps

The exploration_targets feedback loop
──────────────────────────────────────
  CapabilityHypothesisStore.exploration_targets()   (RECURRING / EMERGING)
    → spec.capability_targets                       (names to prioritise)
    → _MinimalExplorationTemplate.capability_targets
    → engine recovery strategies reorder            (via prior_belief / TargetResolver)
    → more evidence for the same patterns
    → CapabilityHypothesisStore.observe()           (frequency++)
    → next .exploration_targets() returns updated list
"""
from __future__ import annotations

import time
import uuid as _uuid_mod
from typing import Any, Callable, Dict, List, Optional

from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
from browsermind_core.exploration.experience_interpreter import ExperienceInterpreter


class ExplorationHarness:
    """Execute ExplorationSpec instances against live ReplayEngine sessions.

    Usage
    ─────
      harness = ExplorationHarness(
          hypothesis_store=CapabilityHypothesisStore(...),
          on_result=lambda r: print(r.status, r.experiences_discovered),
      )
      result = await harness.run(spec, engine_factory)

    engine_factory
    ──────────────
    Async callable: engine_factory(site_key: str) -> ReplayEngine.
    Called fresh per spec (same contract as BatchRunner).
    """

    def __init__(
        self,
        hypothesis_store=None,
        on_result: Optional[Callable[[ExplorationResult], None]] = None,
        normalizer_logger: Optional[Callable] = None,
    ):
        self._hypothesis_store = hypothesis_store
        self._on_result = on_result
        self._normalizer_logger = normalizer_logger

    async def run(
        self,
        spec: ExplorationSpec,
        engine_factory: Callable,
    ) -> ExplorationResult:
        """Execute one exploration run. Never raises — errors captured in result."""
        t0 = time.perf_counter()
        result = ExplorationResult(spec=spec)

        try:
            # 1. Look up SiteEntry
            site_entry = _lookup_site(spec.site_key)
            if site_entry is None:
                result.error = f"SiteRegistry: key '{spec.site_key}' not found"
                return result

            # 2. Build synthetic template and proxy objects
            template = _MinimalExplorationTemplate(
                site_key=spec.site_key,
                start_url=site_entry.url,
                budget=spec.budget,
                capability_targets=list(spec.capability_targets),
            )
            site    = _SiteProxy(key=spec.site_key, start_url=site_entry.url)
            instance = _ExplorationInstance(spec=spec)

            # 3. Execute via engine
            engine = await engine_factory(spec.site_key)
            report = await engine.replay(
                site, template, instance,
                enable_recovery=spec.enable_recovery,
            )

            # 4. Collect metrics from report
            attribution = getattr(report, "failure_attribution", []) if report else []
            result.steps_executed = len(attribution)
            result.affordances_executed = sum(
                1 for a in attribution
                if getattr(a, "action_type", "") in ("submit", "navigate")
            )
            result.verified_effects = sum(
                1 for a in attribution
                if getattr(a, "actual_outcome", "") in ("SUCCESS", "TRANSITION_SUCCESS")
                and getattr(a, "action_type", "") != "fill"
            )

            # 5. Extract completed intents
            completed_intents = _extract_completed_intents(
                attribution, normalizer_logger=self._normalizer_logger
            )

            # 6. Interpret experiences (module-level import makes this patchable)
            interpreter = ExperienceInterpreter()
            labels = interpreter.interpret(completed_intents)
            result.experiences_discovered = [lb.name for lb in labels]

            # 7. Feed unknown patterns to hypothesis store
            if self._hypothesis_store is not None and completed_intents:
                unknown_intents = _extract_unknown_intents(completed_intents, labels)
                if unknown_intents:
                    h = self._hypothesis_store.observe(
                        invariants=sorted(unknown_intents),
                        env_key=spec.site_key,
                        source="exploration",
                        context_hint=spec.label,
                        site_category=site_entry.category,
                    )
                    result.hypothesis_hashes.append(h.invariant_hash)

            # 8. Stop-on-experience annotation
            if spec.stop_on_experience:
                for exp_name in result.experiences_discovered:
                    if exp_name in spec.stop_on_experience:
                        result.metadata["stopped_on"] = exp_name
                        break

        except Exception as exc:
            result.error = str(exc)

        result.duration_seconds = round(time.perf_counter() - t0, 3)

        if self._on_result is not None:
            try:
                self._on_result(result)
            except Exception:
                pass

        return result

    async def run_batch(
        self,
        specs: List[ExplorationSpec],
        engine_factory: Callable,
    ) -> List[ExplorationResult]:
        """Run a list of specs sequentially. Same error-capture guarantee as run()."""
        results = []
        for spec in specs:
            results.append(await self.run(spec, engine_factory))
        return results

    def summarise(self, results: List[ExplorationResult]) -> Dict[str, Any]:
        """Aggregate exploration results for reporting."""
        total      = len(results)
        successes  = sum(1 for r in results if r.success)
        errored    = sum(1 for r in results if r.error)
        experiences = sum(len(r.experiences_discovered) for r in results)
        hypotheses  = sum(len(r.hypothesis_hashes) for r in results)
        total_steps = sum(r.steps_executed for r in results)

        by_site: Dict[str, Dict[str, Any]] = {}
        for r in results:
            k = r.spec.site_key
            if k not in by_site:
                by_site[k] = {"runs": 0, "success": 0, "experiences": 0, "hypotheses": 0}
            by_site[k]["runs"] += 1
            if r.success:
                by_site[k]["success"] += 1
            by_site[k]["experiences"] += len(r.experiences_discovered)
            by_site[k]["hypotheses"]  += len(r.hypothesis_hashes)

        return {
            "total": total,
            "success": successes,
            "error": errored,
            "total_experiences_discovered": experiences,
            "total_hypotheses_observed": hypotheses,
            "total_steps_executed": total_steps,
            "by_site": by_site,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _lookup_site(site_key: str):
    try:
        from browsermind_core.registry.site_registry import get as registry_get
        entry = registry_get(site_key)
        if entry is not None:
            return entry
    except Exception:
        pass
    # Fall back to mission.site_registry (500-site campaign registry)
    try:
        from browsermind_core.mission.site_registry import get_spec
        from browsermind_core.registry.site_registry import SiteEntry
        spec = get_spec(site_key)
        if spec is not None:
            return SiteEntry(
                key=spec.key,
                url=spec.start_url,
                category=spec.category,
                difficulty=spec.difficulty,
            )
    except Exception:
        pass
    # Fall back to EnvironmentEntry — harness only needs start_url
    try:
        from browsermind_core.runtime.environment_registry import _INDEX, _build_index
        if not _INDEX:
            _build_index()
        env = _INDEX.get(site_key)
        if env is not None:
            from browsermind_core.registry.site_registry import SiteEntry
            return SiteEntry(
                key=env.key,
                url=env.start_url,
                category="unknown_frontier",
                difficulty=2,
            )
    except Exception:
        pass
    return None


def _extract_completed_intents(attribution: list, normalizer_logger=None) -> set:
    """Return normalised intent strings from successful attribution entries."""
    completed: set = set()
    try:
        from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
        normalizer = PrimitiveNormalizer(collapse_level=1, logger=normalizer_logger)
        for attr in attribution:
            outcome = getattr(attr, "actual_outcome", None)
            if outcome in ("SUCCESS", "TRANSITION_SUCCESS"):
                try:
                    action_type = getattr(attr, "action_type", "click")
                    role        = getattr(attr, "role", "") or getattr(attr, "target_role", "")
                    name        = getattr(attr, "name", "") or getattr(attr, "target_name", "")
                    intent      = normalizer.normalize(action_type, role, name)
                    if intent:
                        completed.add(intent)
                except Exception:
                    pass
    except Exception:
        pass
    return completed


def _extract_unknown_intents(completed_intents: set, labels: list) -> set:
    """Return intents that were not matched by any known ExperiencePattern."""
    matched: set = set()
    for label in labels:
        if label.is_known:
            matched.update(getattr(label, "matched_intents", set()))
    return completed_intents - matched


# ── Synthetic template + proxy objects ───────────────────────────────────────

class _MinimalExplorationTemplate:
    """Synthetic single-step template: navigate to start URL and explore.

    The engine receives this as a normal template. The single navigation step
    puts the browser on the target page; recovery strategies and capability
    targets guide what happens next.
    """

    def __init__(
        self,
        site_key: str,
        start_url: str,
        budget: int = 200,
        capability_targets: Optional[List[str]] = None,
    ) -> None:
        self.site_key = site_key
        self.start_url = start_url
        self.budget = budget
        self.capability_targets: List[str] = list(capability_targets or [])
        self.id = _uuid_mod.uuid4()
        self.metadata: Optional[Dict[str, Any]] = None

    @property
    def name(self) -> str:
        return f"explore_{self.site_key}"

    @property
    def steps(self) -> List[Dict[str, Any]]:
        # Keys must match what ReplayEngine.replay() reads:
        #   action_type = step.get("action_type", "")
        #   role        = step.get("target_role",  "")
        #   name        = step.get("target_name",  "")
        step: Dict[str, Any] = {
            "action_type": "navigate",
            "target_role": "navigation",
            "target_name": "start_exploration",
            "url": self.start_url,
            "exploration_budget": self.budget,
            "seq": 0,
        }
        if self.capability_targets:
            step["capability_targets"] = list(self.capability_targets)
        return [step]


class _SiteProxy:
    """Minimal site proxy. Mirrors BatchRunner._SiteProxy interface."""

    def __init__(self, key: str, start_url: str = "") -> None:
        self.key = key
        self.start_url = start_url

    @property
    def auth_session(self):
        class _Entry:
            pass
        class _Auth:
            pass
        entry = _Entry()
        entry.key = self.key
        auth = _Auth()
        auth.entry = entry
        return auth


class _ExplorationInstance:
    """Minimal instance object for exploration runs."""

    def __init__(self, spec: ExplorationSpec) -> None:
        self.spec = spec
        self.site_key = spec.site_key
        self.id = _uuid_mod.uuid4()
