"""
BrowserMind -- Phase 3.1 Failure Dominance Runner
===============================================
Runs the V2 policy in pure-model mode (no heuristic overrides, no heuristic fallback)
across a task subset and aggregates telemetry failure categories.

Phase 4.1: writes reports/failure_dominance.json with the canonical failure taxonomy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# Evidence runs must not hang on optional model downloads (e.g. transformers image processor).
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
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


def _pick_tasks(total_tasks: int, site_count: int = 5, *, seed: int = 7) -> List[Dict[str, Any]]:
    from training.target_websites import ALL_WEBSITE_TASKS

    rng = random.Random(seed)
    tasks = [t for t in ALL_WEBSITE_TASKS if isinstance(t, dict) and t.get("url") and t.get("goal")]
    by_site: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        by_site[_base_domain(str(t["url"]))].append(t)

    # Pick diverse-ish sites by preferring larger pools.
    sites_sorted = sorted(by_site.items(), key=lambda kv: len(kv[1]), reverse=True)
    chosen_sites = [site for site, _items in sites_sorted[: max(1, site_count)]]

    per_site = max(1, total_tasks // max(1, len(chosen_sites)))
    picked: List[Dict[str, Any]] = []
    for site in chosen_sites:
        pool = list(by_site.get(site, []))
        rng.shuffle(pool)
        picked.extend(pool[:per_site])

    # Top up if integer division underfilled.
    if len(picked) < total_tasks:
        remainder = [t for t in tasks if t not in picked]
        rng.shuffle(remainder)
        picked.extend(remainder[: (total_tasks - len(picked))])

    return picked[:total_tasks]


def _ensure_reports_dir() -> Path:
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def _telemetry_path_for_today() -> Path:
    today = datetime.utcnow().strftime("%Y%m%d")
    return Path("logs") / f"telemetry_{today}.jsonl"


def _normalize_action(name: str) -> str:
    from scripts.audit_utils import normalize_action_name

    return normalize_action_name(name)


async def _run(args) -> Path:
    print("[phase4.1] starting failure dominance run", flush=True)
    import torch

    from core.executor import ActionExecutor
    from core.task_decomposer import TaskDecomposer
    from model.agent_policy import AgentPolicy

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[phase4.1] torch device={device}", flush=True)
    policy = AgentPolicy().to(device)
    print("[phase4.1] policy constructed", flush=True)

    ckpt_path = Path(args.checkpoint)
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=device)
        model_state = ckpt.get("model_state", ckpt)
        policy.load_state_dict(model_state, strict=False)
        print("[phase4.1] checkpoint loaded", flush=True)
    else:
        print(f"[WARN] checkpoint not found at {ckpt_path}; running untrained model.")

    policy.eval()

    # Build tasks
    task_specs = _pick_tasks(args.tasks, args.sites, seed=args.seed)
    print(f"[phase4.1] picked tasks={len(task_specs)}", flush=True)
    decomposer = TaskDecomposer()
    print("[phase4.1] decomposer ready", flush=True)

    # Execute + aggregate
    required = Counter(
        {
            "wrong_element": 0,
            "wrong_action": 0,
            "observation": 0,
            "execution": 0,
            "popup": 0,
            "environment": 0,
        }
    )
    total_tasks = 0
    successes = 0
    failures = 0
    total_steps = 0
    task_ids: List[str] = []

    for i, spec in enumerate(task_specs, start=1):
        goal = str(spec.get("goal", ""))
        url = str(spec.get("url", ""))
        site = _base_domain(url)
        try:
            print(f"[{i:02d}/{len(task_specs)}] {site} - {goal}", flush=True)
        except Exception:
            print(f"[{i:02d}/{len(task_specs)}] task", flush=True)

        if args.dry_run:
            continue

        executor = ActionExecutor(policy_v2=policy)
        executor.use_policy = True
        executor.use_heuristic_fallback = False
        executor.pure_model = True

        # Use decomposer to generate a small multi-step task
        task = decomposer.decompose(intent="generic", user_type="benchmark", query=goal, url=url)
        result = await executor.execute_task(task)
        task_id = str(getattr(executor, "_current_task_id", "") or "")
        if task_id:
            task_ids.append(task_id)

        total_tasks += 1
        if result.success:
            successes += 1
        else:
            failures += 1

        # Classify steps: use telemetry as primary evidence, ActionResult only to split wrong_action vs wrong_element.
        telemetry_rows = _read_jsonl(_telemetry_path_for_today())
        rows_for_task = [r for r in telemetry_rows if str(r.get("task_id", "")) == task_id] if task_id else []
        by_step = {int(r.get("step", -1)): r for r in rows_for_task if isinstance(r, dict)}

        for action, step_res in zip(task.actions, result.results):
            total_steps += 1
            if step_res.success:
                continue

            trow = by_step.get(int(action.step), {})
            failure_type = str(trow.get("failure_type", "") or "").strip().lower()
            planned = _normalize_action(action.action_type.value)

            if failure_type in {"popup"}:
                required["popup"] += 1
                continue
            if failure_type in {"environment"}:
                required["environment"] += 1
                continue
            if failure_type in {"observation", "sparse_graph"}:
                required["observation"] += 1
                continue
            if failure_type in {"execution"}:
                required["execution"] += 1
                continue

            # Policy failures: split into wrong_action vs wrong_element.
            if failure_type in {"policy"} or getattr(step_res, "used_model", False):
                model_action = _normalize_action(getattr(step_res, "model_action", "") or getattr(step_res, "action_type", ""))
                if model_action and model_action != planned:
                    required["wrong_action"] += 1
                else:
                    required["wrong_element"] += 1
                continue

            # Fallback bucket: assume execution if telemetry missing.
            required["execution"] += 1

    out_dir = _ensure_reports_dir()
    out_path = (out_dir / "failure_dominance.json").resolve()
    report = {
        "generated_at": _now_iso(),
        "pure_model": True,
        "use_heuristic_fallback": False,
        "checkpoint": str(ckpt_path),
        "total_tasks": total_tasks,
        "successes": successes,
        "failures": failures,
        "failure_distribution": dict(required),
    }

    if not args.dry_run:
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n[ok] wrote {out_path}")
    else:
        print("\n[dry-run] no output written")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=50)
    ap.add_argument("--sites", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--checkpoint", type=str, default="browsermind_policy_v2.pt")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

