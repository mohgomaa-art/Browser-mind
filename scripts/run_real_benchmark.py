from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.attribution_metrics import benchmark_attribution


ACTION_ID_TO_TYPE = {
    0: "navigate",
    1: "click",
    2: "type",
    3: "scroll",
    4: "wait",
    5: "extract",
    6: "go_back",
    7: "done",
}


def _task_id(goal: str, url: str, idx: int) -> str:
    h = hashlib.md5(f"{idx}|{goal}|{url}".encode("utf-8")).hexdigest()[:10]
    return f"task_{idx:03d}_{h}"


def _load_tasks(path: str, limit: int, seed: int) -> List[Dict[str, str]]:
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        tasks = []
        for item in data:
            if isinstance(item, dict):
                tasks.append(
                    {
                        "goal": str(item.get("goal", "")),
                        "url": str(item.get("url") or item.get("start_url") or ""),
                        "family": str(item.get("family", "")),
                    }
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                tasks.append({"goal": str(item[0]), "url": str(item[1]), "family": ""})
    else:
        from training.dagger_tasks import DAGGER_TASKS
        tasks = [{"goal": goal, "url": url, "family": ""} for goal, url in DAGGER_TASKS]

    tasks = [t for t in tasks if t["goal"] and t["url"]]
    rng = random.Random(seed)
    rng.shuffle(tasks)
    selected = tasks[:limit]
    for idx, task in enumerate(selected, start=1):
        task["task_id"] = _task_id(task["goal"], task["url"], idx)
    return selected


def _infer_type_value(goal: str) -> str:
    goal_l = (goal or "").lower()
    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", goal)
    if email:
        return email.group(0)
    m = re.search(r"\b(?:search for|find|look up|query)\s+(.+)", goal, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bwith\s+['\"]?([^'\"\n]{2,120})['\"]?", goal, flags=re.I)
    if m:
        return m.group(1).strip()
    if "password" in goal_l:
        return "Password123!"
    if "email" in goal_l:
        return "test@example.com"
    if "username" in goal_l or "user" in goal_l:
        return "testuser"
    if "name" in goal_l:
        return "John Smith"
    return goal.strip()[:80] or "BrowserMind"


def _infer_target_url(goal: str, fallback: str) -> str:
    goal_l = (goal or "").lower()
    mapping = {
        "github": "https://github.com",
        "gitlab": "https://gitlab.com",
        "reddit": "https://www.reddit.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "twitter": "https://x.com",
        "x.com": "https://x.com",
        "wikipedia": "https://en.wikipedia.org",
        "python": "https://www.python.org",
        "google": "https://www.google.com",
        "bing": "https://www.bing.com",
        "duckduckgo": "https://duckduckgo.com",
        "huggingface": "https://huggingface.co",
        "arxiv": "https://arxiv.org",
        "pypi": "https://pypi.org",
    }
    for key, url in mapping.items():
        if key in goal_l:
            return url
    return fallback


def _node_locator(page, node: Dict[str, Any]):
    name = str(node.get("name", "")).strip()
    role = str(node.get("role", "")).strip()
    if role in {"button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem"} and name:
        return page.get_by_role(role, name=name, exact=False).first
    if name:
        return page.get_by_text(name, exact=False).first
    return None


async def _execute_selected_action(
    page,
    action: Dict[str, Any],
    nodes: List[Dict[str, Any]],
    goal: str,
    start_url: str,
) -> Tuple[bool, str, Any]:
    action_type = action.get("type") or ACTION_ID_TO_TYPE.get(int(action.get("action_id", 7)), "done")
    element_idx = action.get("element_idx")

    try:
        if action_type == "done":
            return True, "", None

        if action_type == "navigate":
            target = str(action.get("value") or _infer_target_url(goal, start_url))
            if not target.startswith(("http://", "https://")):
                return False, f"invalid_navigation_target:{target}", None
            await page.goto(target, wait_until="domcontentloaded", timeout=15000)
            return True, "", target

        if action_type == "wait":
            await asyncio.sleep(1.0)
            return True, "", None

        if action_type == "scroll":
            await page.evaluate("window.scrollBy(0, 600)")
            return True, "", None

        if action_type == "go_back":
            await page.go_back(wait_until="domcontentloaded", timeout=10000)
            return True, "", None

        if action_type == "extract":
            text = await page.locator("main, article, body").first.inner_text(timeout=5000)
            return bool(text.strip()), "empty_extract" if not text.strip() else "", text[:500]

        if element_idx is None or int(element_idx) < 0 or int(element_idx) >= len(nodes):
            return False, "target_element_missing", None

        node = nodes[int(element_idx)]
        locator = _node_locator(page, node)
        if locator is None:
            return False, "target_locator_missing", None

        if action_type == "click":
            await locator.click(timeout=5000)
            try:
                await page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass
            return True, "", str(node.get("name", ""))

        if action_type == "type":
            value = str(action.get("value") or _infer_type_value(goal))
            await locator.fill(value, timeout=5000)
            if any(k in goal.lower() for k in ("search", "find", "look up", "submit")):
                await page.keyboard.press("Enter")
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            return True, "", value

        return False, f"unsupported_action:{action_type}", None
    except Exception as exc:
        return False, str(exc)[:240], None


async def _decide(
    mode: str,
    policy,
    nodes: List[Dict[str, Any]],
    edges: List[Any],
    goal: str,
    page_url: str,
    threshold: float,
) -> Dict[str, Any]:
    from training.graph_builder import decide_expert_action

    heuristic_action = decide_expert_action({"nodes": nodes, "edges": edges}, goal, page_url)

    if mode == "heuristic_only":
        heuristic_action["decision_source"] = "fallback"
        heuristic_action["confidence"] = 0.0
        return heuristic_action

    if policy is None:
        raise RuntimeError("Policy mode requested without a loaded policy checkpoint.")

    pred = policy.predict(nodes, edges, goal, confidence_threshold=threshold)
    policy_action = {
        "type": pred["action_type"],
        "action_id": pred["action_id"],
        "element_idx": pred.get("element_idx"),
        "value": _infer_target_url(goal, page_url) if pred["action_type"] == "navigate" else "",
        "decision_source": "policy",
        "confidence": float(pred.get("confidence", 0.0)),
        "top3": pred.get("top3", []),
    }

    if mode == "policy_only":
        return policy_action

    if mode == "full_system" and float(pred.get("confidence", 0.0)) >= threshold:
        return policy_action

    heuristic_action["decision_source"] = "fallback"
    heuristic_action["confidence"] = float(pred.get("confidence", 0.0))
    heuristic_action["policy_candidate"] = {
        "type": pred["action_type"],
        "action_id": pred["action_id"],
        "element_idx": pred.get("element_idx"),
        "confidence": float(pred.get("confidence", 0.0)),
    }
    return heuristic_action


def _classify_step_failure(error: str, action_type: str, ax_nodes: int, nodes: List[Dict[str, Any]]) -> str:
    text = (error or "").lower()
    if "timeout" in text or "net::" in text or "navigation" in text:
        return "environment"
    if any(str(n.get("role")) == "dialog" for n in nodes):
        return "popup"
    if ax_nodes < 10:
        return "sparse_graph"
    if ax_nodes < 20 or "target_element_missing" in text or "locator_missing" in text:
        return "observation"
    if action_type in {"click", "type"}:
        return "wrong_element"
    if action_type in {"done", "scroll", "wait", "navigate"}:
        return "wrong_action"
    return "execution"


async def _run_one_task(
    mode: str,
    task: Dict[str, str],
    policy,
    max_steps: int,
    threshold: float,
    headless: bool,
) -> Dict:
    from playwright.async_api import async_playwright
    from core.validator import Validator
    from training.graph_builder import build_graph_from_page, prune_graph

    validator = Validator()
    steps = []
    start = time.time()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        start_url = task["url"]

        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            await browser.close()
            return {
                "task_id": task["task_id"],
                "goal": task["goal"],
                "url": start_url,
                "success": False,
                "failure_type": "environment",
                "error": str(exc)[:240],
                "steps": [],
                "latency_ms": int((time.time() - start) * 1000),
            }

        initial_url = page.url
        if policy is not None and hasattr(policy, "reset_task"):
            policy.reset_task(task["goal"])

        final_failure = "timeout"
        for step_idx in range(1, max_steps + 1):
            graph = await build_graph_from_page(page)
            nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
            ax_nodes = len(nodes)

            if ax_nodes == 0:
                final_failure = "sparse_graph"
                steps.append(
                    {
                        "step": step_idx,
                        "decision_source": "none",
                        "action": "none",
                        "success": False,
                        "confidence": 0.0,
                        "ax_nodes": ax_nodes,
                        "failure_type": "sparse_graph",
                        "error": "empty_graph",
                    }
                )
                break

            action = await _decide(mode, policy, nodes, edges, task["goal"], page.url, threshold)
            action_type = str(action.get("type") or ACTION_ID_TO_TYPE.get(int(action.get("action_id", 7)), "done"))
            step_ok, error, payload = await _execute_selected_action(page, action, nodes, task["goal"], start_url)

            val = await validator.check(page, task["goal"], initial_url)
            task_done = bool(val.success)
            failure_type = "" if step_ok else _classify_step_failure(error, action_type, ax_nodes, nodes)
            final_failure = failure_type or final_failure

            steps.append(
                {
                    "step": step_idx,
                    "decision_source": action.get("decision_source", "unknown"),
                    "action": action_type,
                    "action_id": action.get("action_id"),
                    "element_idx": action.get("element_idx"),
                    "confidence": round(float(action.get("confidence", 0.0)), 4),
                    "ax_nodes": ax_nodes,
                    "success": bool(step_ok),
                    "goal_verified": task_done,
                    "validation_signal": val.signal,
                    "failure_type": failure_type,
                    "error": error,
                    "url": page.url,
                }
            )

            if action_type == "done":
                await browser.close()
                return {
                    "task_id": task["task_id"],
                    "goal": task["goal"],
                    "url": start_url,
                    "success": task_done,
                    "failure_type": "" if task_done else "wrong_action",
                    "steps": steps,
                    "latency_ms": int((time.time() - start) * 1000),
                }

            if task_done:
                await browser.close()
                return {
                    "task_id": task["task_id"],
                    "goal": task["goal"],
                    "url": start_url,
                    "success": True,
                    "failure_type": "",
                    "steps": steps,
                    "latency_ms": int((time.time() - start) * 1000),
                }

            if not step_ok and mode == "policy_only":
                break

            await asyncio.sleep(0.4)

        await browser.close()
        return {
            "task_id": task["task_id"],
            "goal": task["goal"],
            "url": start_url,
            "success": False,
            "failure_type": final_failure or "timeout",
            "steps": steps,
            "latency_ms": int((time.time() - start) * 1000),
        }


async def _run_mode(
    mode: str,
    tasks: List[Dict[str, str]],
    policy,
    max_steps: int,
    threshold: float,
    headless: bool,
) -> Dict:
    results = []
    for idx, task in enumerate(tasks, start=1):
        print(f"[{mode}] {idx}/{len(tasks)} {task['goal'][:70]}")
        result = await _run_one_task(mode, task, policy, max_steps, threshold, headless)
        status = "OK" if result["success"] else "FAIL"
        print(f"  -> {status} {len(result.get('steps', []))} steps {result['latency_ms']}ms")
        results.append(result)

    successes = sum(1 for r in results if r.get("success"))
    completed_steps = [len(r.get("steps", [])) for r in results]
    latencies = [int(r.get("latency_ms", 0)) for r in results]
    return {
        "mode": mode,
        "tasks": len(results),
        "successes": successes,
        "success_rate": round(successes / max(len(results), 1), 4),
        "avg_steps": round(sum(completed_steps) / max(len(completed_steps), 1), 2),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
        "results": results,
    }


def _load_policy(path: str):
    from model.agent_policy import AgentPolicy

    ckpt = Path(path)
    if not ckpt.exists():
        raise FileNotFoundError(f"Policy checkpoint not found: {ckpt}")
    return AgentPolicy.load(str(ckpt), map_location="cpu")


async def run_benchmark(args) -> Dict:
    tasks = _load_tasks(args.task_file, args.tasks, args.seed)
    policy = None
    if args.mode in {"policy_only", "full_system", "all"}:
        policy = _load_policy(args.ckpt)

    modes = ["policy_only", "heuristic_only", "full_system"] if args.mode == "all" else [args.mode]
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.real_benchmark.v1",
        "task_count": len(tasks),
        "max_steps": args.max_steps,
        "threshold": args.threshold,
        "seed": args.seed,
        "task_file": args.task_file or "training.dagger_tasks",
        "modes": [],
    }

    for mode in modes:
        report["modes"].append(
            await _run_mode(mode, tasks, policy, args.max_steps, args.threshold, args.headless)
        )

    if args.mode == "all":
        report["attribution"] = benchmark_attribution(report)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"real_benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["output_path"] = str(out_path)
    print(json.dumps({k: v for k, v in report.items() if k != "modes"}, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}")
    return report


def parse_args():
    parser = argparse.ArgumentParser(description="Run real BrowserMind live benchmarks.")
    parser.add_argument("--mode", choices=["policy_only", "heuristic_only", "full_system", "all"], default="all")
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--task-file", default="scratch/strict500_tasks.json")
    parser.add_argument("--ckpt", default="browsermind_policy_v2.pt")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--threshold", type=float, default=0.42)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="benchmarks/real")
    parser.add_argument("--headed", dest="headless", action="store_false")
    parser.set_defaults(headless=True)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_benchmark(parse_args()))
