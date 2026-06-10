"""BatchRunner — execution harness for corpus generation.

Converts a list of (template, site_key) specs into OutcomeLedger records by
running each through a ReplayEngine. This is the "Do Stuff at scale" component
that the Transfer Arena, Reward Layers, and Capability Discovery all depend on.

Design
──────
- Sequential by default (avoids browser resource contention).
- engine_factory callable: (site_key) → ReplayEngine. The caller controls
  session setup, persona, outcome_ledger wiring, etc.
- Each run is isolated: engine_factory is called fresh per spec, so auth state
  and execution_id are independent.
- Failures are captured in BatchRunResult.error; the harness never aborts.
- No LLM. No Playwright dependency at import time (only at run time via factory).

Usage example
─────────────
    from browsermind_core.evaluation.batch_runner import BatchRunner, BatchRunSpec

    specs = [
        BatchRunSpec(template=tmpl, site_key="github", instance=instance),
        BatchRunSpec(template=tmpl, site_key="gitlab", instance=instance2),
    ]

    async def engine_factory(site_key):
        session = AuthSession(env_registry[site_key], persona, store_dir, headless=True)
        return ReplayEngine(session, outcome_ledger=ledger, persona_id=persona_id,
                            environment_instance=site_key)

    runner = BatchRunner()
    results = await runner.run(specs, engine_factory)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, List, Optional


@dataclass
class BatchRunSpec:
    """One (template, site) pair to execute."""
    template: Any           # WorkflowTemplate
    site_key: str
    instance: Any           # WorkflowInstance
    enable_recovery: bool = True
    start_step_index: int = 0
    label: str = ""         # optional human label for logging

    def __post_init__(self):
        if not self.label:
            tmpl_name = getattr(self.template, "name", "") or ""
            self.label = f"{tmpl_name}@{self.site_key}"


@dataclass
class BatchRunResult:
    """Outcome of one BatchRunSpec execution."""
    spec: BatchRunSpec
    report: Optional[Any] = None            # ReplayReport or None on error
    duration_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        if self.error:
            return False
        return getattr(self.report, "status", "") == "SUCCESS"

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        return getattr(self.report, "status", "UNKNOWN")


class BatchRunner:
    """Runs a list of BatchRunSpecs sequentially, collecting results.

    Args:
        max_concurrency: 1 = fully sequential (default). >1 = limited parallel.
            Use 1 until resource contention is understood; parallel browser
            contexts multiply memory usage.
        on_result: Optional callback(BatchRunResult) called after each run.
            Use for progress logging, early-stopping, etc. Never raises.
    """

    def __init__(
        self,
        max_concurrency: int = 1,
        on_result: Optional[Callable[["BatchRunResult"], None]] = None,
    ):
        self.max_concurrency = max(1, max_concurrency)
        self.on_result = on_result

    async def run(
        self,
        specs: List[BatchRunSpec],
        engine_factory: Callable[[str], Coroutine],
    ) -> List[BatchRunResult]:
        """Execute all specs and return results in input order.

        Args:
            specs:          List of BatchRunSpec to execute.
            engine_factory: async callable (site_key) → ReplayEngine.
                            Called fresh for each spec.
        """
        if self.max_concurrency == 1:
            return await self._run_sequential(specs, engine_factory)
        return await self._run_limited(specs, engine_factory)

    async def _run_one(
        self, spec: BatchRunSpec, engine_factory: Callable
    ) -> BatchRunResult:
        start = time.time()
        try:
            engine = await engine_factory(spec.site_key)
            # Resolve the site object — engine may have a site registry or the
            # caller may pass site via factory. We pass None and let ReplayEngine
            # handle it (site=None → env_key="unknown" fallback).
            site = getattr(engine, "_site", None)
            # Try to get the site from the auth_session entry as a SiteEntry mock
            try:
                entry = engine.auth_session.entry
                site = _SiteProxy(entry.key, entry.start_url)
            except Exception:
                site = None

            report = await engine.replay(
                site=site,
                template=spec.template,
                instance=spec.instance,
                enable_recovery=spec.enable_recovery,
                start_step_index=spec.start_step_index,
            )
            duration = time.time() - start
            result = BatchRunResult(spec=spec, report=report, duration_seconds=round(duration, 3))
            print(
                f"  [BatchRunner] {spec.label} → {result.status} "
                f"({duration:.1f}s)"
            )
        except Exception as exc:
            duration = time.time() - start
            result = BatchRunResult(
                spec=spec,
                duration_seconds=round(duration, 3),
                error=str(exc),
            )
            print(
                f"  [BatchRunner] {spec.label} → ERROR ({duration:.1f}s): {exc}"
            )
        if self.on_result is not None:
            try:
                self.on_result(result)
            except Exception:
                pass
        return result

    async def _run_sequential(
        self, specs: List[BatchRunSpec], engine_factory: Callable
    ) -> List[BatchRunResult]:
        results = []
        for i, spec in enumerate(specs):
            print(f"  [BatchRunner] Run {i + 1}/{len(specs)}: {spec.label}")
            results.append(await self._run_one(spec, engine_factory))
        return results

    async def _run_limited(
        self, specs: List[BatchRunSpec], engine_factory: Callable
    ) -> List[BatchRunResult]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(spec):
            async with semaphore:
                return await self._run_one(spec, engine_factory)

        return list(await asyncio.gather(*(bounded(s) for s in specs)))

    def summarise(self, results: List[BatchRunResult]) -> dict:
        """Return a summary dict for logging / Transfer Arena input."""
        total = len(results)
        successes = sum(1 for r in results if r.success)
        errors = sum(1 for r in results if r.error)
        by_env: dict = {}
        for r in results:
            env = r.spec.site_key
            if env not in by_env:
                by_env[env] = {"total": 0, "success": 0}
            by_env[env]["total"] += 1
            if r.success:
                by_env[env]["success"] += 1
        return {
            "total": total,
            "success": successes,
            "failed": total - successes - errors,
            "error": errors,
            "success_rate": round(successes / total, 4) if total else None,
            "by_env": by_env,
        }


class _SiteProxy:
    """Minimal duck-type replacement for EnvironmentEntry when used as 'site' arg."""
    def __init__(self, key: str, start_url: str = ""):
        self.key = key
        self.start_url = start_url
