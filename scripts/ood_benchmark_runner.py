"""
BrowserMind -- Phase 3.8 OOD Benchmark Runner (pure_model)
=========================================================
Runs a multi-domain OOD benchmark with:
  - use_heuristic_fallback = False
  - pure_model = True (skip heuristic overrides inside policy)

Writes: benchmarks/ood_benchmark_v1/results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _base_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return (url or "").split("://")[-1].split("/")[0].replace("www.", "").lower()


def _default_domains() -> List[str]:
    return [
        "books.toscrape.com",
        "quotes.toscrape.com",
        "developer.mozilla.org",
        "docs.python.org",
        "en.wikipedia.org",
        "news.ycombinator.com",
        "github.com",
        "stackoverflow.com",
        "openweathermap.org",
        "reddit.com",
    ]


def _pick_tasks(domains: List[str], per_domain: int, *, seed: int = 11) -> List[Dict[str, Any]]:
    import random

    from training.target_websites import ALL_WEBSITE_TASKS

    rng = random.Random(seed)
    domset = {d.replace("www.", "").lower() for d in domains}
    pool = [t for t in ALL_WEBSITE_TASKS if _base_domain(str(t.get("url", ""))) in domset]
    by_dom: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in pool:
        by_dom[_base_domain(str(t["url"]))].append(t)
    picked = []
    for d in domset:
        items = list(by_dom.get(d, []))
        rng.shuffle(items)
        picked.extend(items[:per_domain])
    return picked


async def _run(args) -> Path:
    import torch

    from core.executor import ActionExecutor
    from core.task_decomposer import TaskDecomposer
    from model.agent_policy import AgentPolicy

    domains = args.domains or _default_domains()
    task_specs = _pick_tasks(domains, args.per_domain, seed=args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    policy = AgentPolicy().to(device)
    ckpt_path = Path(args.checkpoint)
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=device)
        model_state = ckpt.get("model_state", ckpt)
        policy.load_state_dict(model_state, strict=False)
    else:
        print(f"[WARN] checkpoint not found at {ckpt_path}; running untrained model.")
    policy.eval()

    decomposer = TaskDecomposer()

    per_domain_stats: Dict[str, Dict[str, Any]] = {}
    totals = {"tasks": 0, "success": 0, "steps": 0, "step_success": 0}

    for spec in task_specs:
        goal = str(spec.get("goal", ""))
        url = str(spec.get("url", ""))
        dom = _base_domain(url)
        per_domain_stats.setdefault(dom, {"tasks": 0, "success": 0, "steps": 0, "step_success": 0})

        if args.dry_run:
            per_domain_stats[dom]["tasks"] += 1
            totals["tasks"] += 1
            continue

        executor = ActionExecutor(policy_v2=policy)
        executor.use_policy = True
        executor.use_heuristic_fallback = False
        executor.pure_model = True

        task = decomposer.decompose(intent="generic", user_type="benchmark", query=goal, url=url)
        result = await executor.execute_task(task)

        per_domain_stats[dom]["tasks"] += 1
        totals["tasks"] += 1
        if result.success:
            per_domain_stats[dom]["success"] += 1
            totals["success"] += 1

        steps = len(result.results)
        per_domain_stats[dom]["steps"] += steps
        totals["steps"] += steps
        per_domain_stats[dom]["step_success"] += sum(1 for r in result.results if r.success)
        totals["step_success"] += sum(1 for r in result.results if r.success)

    # Finalize rates
    for dom, stats in per_domain_stats.items():
        stats["task_success_rate"] = (stats["success"] / max(1, stats["tasks"])) if not args.dry_run else 0.0
        stats["step_success_rate"] = (stats["step_success"] / max(1, stats["steps"])) if not args.dry_run else 0.0

    results = {
        "generated_at": _now_iso(),
        "pure_model": True,
        "use_heuristic_fallback": False,
        "checkpoint": str(ckpt_path),
        "domains": domains,
        "per_domain": per_domain_stats,
        "overall": {
            "tasks": totals["tasks"],
            "task_success_rate": (totals["success"] / max(1, totals["tasks"])) if not args.dry_run else 0.0,
            "steps": totals["steps"],
            "step_success_rate": (totals["step_success"] / max(1, totals["steps"])) if not args.dry_run else 0.0,
        },
    }

    out_dir = Path(args.out_dir or "benchmarks/ood_benchmark_v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.json"
    if not args.dry_run:
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"[ok] wrote {out_path}")
    else:
        print("[dry-run] no output written")
    return out_path.resolve()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-domain", type=int, default=50)
    ap.add_argument("--domains", type=str, nargs="*", default=[])
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--checkpoint", type=str, default="browsermind_policy_v2.pt")
    ap.add_argument("--out-dir", type=str, default="benchmarks/ood_benchmark_v1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

