"""BrowserMind frozen benchmark runner.

Runs each benchmark workflow N times and writes a single JSON report under
`reports/benchmark/`. Designed to be re-run after every meaningful change so
metrics drift is visible.

Usage:
  python run_benchmark.py
  python run_benchmark.py --runs 10 --headless
  python run_benchmark.py --compare reports/benchmark/benchmark_PREV.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
from pathlib import Path
from uuid import uuid4

# (template_name, env_key, description)
BENCHMARK_WORKFLOWS = [
    ("exp_static_wikipedia_search", "static_baseline", "Wikipedia search (engine health gate)"),
    ("saucedemo",                   "saucedemo",        "SauceDemo login + checkout"),
    ("exp_saucedemo_checkout",      "saucedemo",        "SauceDemo checkout flow"),
    ("exp_demoqa_form",             "demoqa",           "DemoQA practice form"),
    ("exp_aria_login",              "aria_internet",    "the-internet form auth"),
]

METRIC_KEYS = ["resolution_rate", "effect_verified_rate", "recovery_rate"]


async def run_single(template_name: str, env_key: str, headless: bool, store_dir: str) -> dict:
    """Run one workflow once and return per-run metrics."""
    from browsermind_core.runtime.environment_registry import resolve
    from browsermind_core.runtime.auth_session import AuthSession
    from browsermind_core.ontology.workflow_store import WorkflowStore
    from browsermind_core.ontology.p1_schemas import WorkflowInstance
    from browsermind_core.runtime.replay_engine import ReplayEngine
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
    from browsermind_core.ledger.outcome_ledger import OutcomeLedger
    from browsermind_core.ledger.outcome_repository import OutcomeRepository

    provider = LocalJSONPersistenceProvider(store_dir)
    ws = WorkflowStore(store_dir)
    entry = resolve(env_key)
    if not entry:
        return {"success": False, "error": f"Environment '{env_key}' not registered"}
    repo = OutcomeRepository(provider)
    ledger = OutcomeLedger(repository=repo)

    te = ws.lookup_template(template_name)
    if not te:
        return {"success": False, "error": f"Template '{template_name}' not found"}

    template = ws.get_template(te["id"])
    if template is None:
        return {"success": False, "error": f"Template '{template_name}' could not be loaded"}

    instance = WorkflowInstance(
        persona_id=uuid4(),
        template_id=template.id,
        bound_resources={},
        bound_identities={},
    )

    session = AuthSession(
        entry=entry,
        persona_name="pilot",
        store_dir=Path(store_dir),
        headless=headless,
    )
    engine = ReplayEngine(
        session,
        outcome_ledger=ledger,
        persona_id=instance.persona_id,
        environment_family=entry.family,
        environment_instance=env_key,
    )

    try:
        report = await engine.replay(entry, template, instance)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    attrs = report.failure_attribution or []
    ev_count = sum(1 for a in attrs if a.effect_verified is True)
    total = max(1, len(attrs))
    return {
        "success":                    report.status == "SUCCESS",
        "status":                     report.status,
        "resolution_rate":            report.resolution_rate,
        "effect_verified_rate":       ev_count / total,
        "recovery_rate":              getattr(report, "recovery_rate", None),
        "steps":                      report.total_steps,
        "resolved":                   report.resolved_steps,
        "failed":                     report.failed_steps,
        "duration_seconds":           report.duration_seconds,
        "failure_reason":             getattr(report, "failure_reason", None),
        "missing_resource":           getattr(report, "missing_resource", None),
        "ambiguous_steps":            getattr(report, "ambiguous_steps", 0),
        "resource_resolution_rate":   getattr(report, "resource_resolution_rate", None),
    }


async def run_benchmark(args) -> dict:
    store_dir = str(Path.home() / ".browsermind")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    workflows: dict[str, dict] = {}
    for template_name, env_key, description in BENCHMARK_WORKFLOWS:
        print(f"\n[Benchmark] {description} ({template_name} @ {env_key})")
        runs: list[dict] = []
        for i in range(args.runs):
            print(f"  Run {i+1}/{args.runs} ...", end=" ", flush=True)
            r = await run_single(template_name, env_key, args.headless, store_dir)
            runs.append(r)
            print("SUCCESS" if r.get("success") else f"FAIL ({r.get('status') or r.get('error')})")

        successes = [r for r in runs if r.get("success")]
        metrics = {}
        for m in METRIC_KEYS:
            vals = [r[m] for r in runs if isinstance(r.get(m), (int, float))]
            metrics[m] = sum(vals) / len(vals) if vals else 0.0

        workflows[template_name] = {
            "description":  description,
            "env_key":      env_key,
            "runs":         args.runs,
            "successes":    len(successes),
            "success_rate": (len(successes) / args.runs) if args.runs else 0.0,
            "metrics":      metrics,
            "raw":          runs,
        }
        rr = metrics.get("resolution_rate")
        print(f"  -> success_rate={workflows[template_name]['success_rate']:.0%}"
              f" | resolution_rate={rr:.2%}" if rr is not None else
              f"  -> success_rate={workflows[template_name]['success_rate']:.0%}")

    aggregate = (
        sum(w["success_rate"] for w in workflows.values()) / len(workflows)
        if workflows else 0.0
    )

    report = {
        "timestamp":              timestamp,
        "runs_per_workflow":      args.runs,
        "headless":               args.headless,
        "workflows":              workflows,
        "aggregate_success_rate": aggregate,
    }

    out_dir = Path("reports/benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"benchmark_{timestamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETE")
    print("=" * 60)
    print(f"Aggregate success rate : {aggregate:.1%}")
    print(f"Report                 : {out_path}")

    if args.compare and Path(args.compare).exists():
        prev = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        prev_agg = prev.get("aggregate_success_rate", 0.0)
        delta = aggregate - prev_agg
        print(f"\nVs previous            : {prev_agg:.1%} -> {aggregate:.1%} ({delta:+.1%})")

    return report


def main():
    p = argparse.ArgumentParser(description="BrowserMind benchmark runner")
    p.add_argument("--runs",     type=int, default=5)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--compare",  default=None,
                   help="Path to a prior benchmark JSON for delta reporting.")
    args = p.parse_args()
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()
