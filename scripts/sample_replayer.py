from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import iter_dataset_samples, rel
from training.verification.browser_runtime import (
    NetworkCapture,
    capture_snapshot,
    execute_trace_action,
    urls_match,
)
from training.verification.registry import default_registry, infer_task_type


def _trace(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = sample.get("execution_trace") or sample.get("trace") or sample.get("action_trace") or []
    if isinstance(trace, list):
        return [event for event in trace if isinstance(event, dict)]
    if isinstance(trace, dict):
        actions = trace.get("actions") or trace.get("steps") or trace.get("events") or []
        return [event for event in actions if isinstance(event, dict)] if isinstance(actions, list) else []
    return []


def _expected_verification(sample: Dict[str, Any]) -> Dict[str, Any]:
    value = sample.get("verification")
    return value if isinstance(value, dict) else {}


async def replay_sample(sample: Dict[str, Any], headless: bool = True, include_graph: bool = True) -> Dict[str, Any]:
    from playwright.async_api import async_playwright

    registry = default_registry()
    goal = str(sample.get("goal", ""))
    task_type = str(sample.get("task_type") or infer_task_type(goal, sample))
    expected_after_url = str(sample.get("after_url") or "")
    expected_after_hash = str(sample.get("after_state_hash") or "")
    expected_verification = _expected_verification(sample)
    actions = _trace(sample)

    replay_actions: List[Dict[str, Any]] = []
    network_trace: List[Dict[str, Any]] = []
    before_snapshot: Dict[str, Any] = {}
    after_snapshot: Dict[str, Any] = {}
    replay_error = ""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            before_url = str(sample.get("before_url") or sample.get("url") or "")
            if before_url and before_url != "about:blank":
                await page.goto(before_url, wait_until="domcontentloaded", timeout=20000)

            before_snapshot = await capture_snapshot(page, include_graph=include_graph)
            async with NetworkCapture(page) as net:
                for action in actions:
                    replay_actions.append(await execute_trace_action(page, action, goal=goal))
                    if replay_actions[-1].get("success") is not True:
                        break
                network_trace = list(net.events)
            after_snapshot = await capture_snapshot(page, include_graph=include_graph)
        except Exception as exc:
            replay_error = str(exc)[:500]
        finally:
            await browser.close()

    replay_trace = {
        "actions": replay_actions,
        "network": network_trace,
        "before_snapshot": {
            "url": before_snapshot.get("url", ""),
            "state_hash": before_snapshot.get("state_hash", ""),
        },
        "after_snapshot": {
            "url": after_snapshot.get("url", ""),
            "state_hash": after_snapshot.get("state_hash", ""),
        },
        "error": replay_error,
    }
    verification = registry.verify(
        task_type,
        before_snapshot,
        after_snapshot,
        {"actions": replay_actions, "network": network_trace},
        goal=goal,
    ).to_dict()

    url_match = urls_match(expected_after_url, str(after_snapshot.get("url", "")))
    state_match = bool(expected_after_hash and expected_after_hash == after_snapshot.get("state_hash"))
    verification_match = (
        verification.get("gold_eligible") is True
        and verification.get("causality_strength") == expected_verification.get("causality_strength")
        and bool(expected_verification.get("gold_eligible") or expected_verification.get("goal_verified"))
    )
    actions_ok = bool(actions) and all(row.get("success") is True for row in replay_actions) and len(replay_actions) == len(actions)
    replay_passed = bool(actions_ok and url_match and state_match and verification_match and not replay_error)

    return {
        "sample_hash": sample.get("sample_hash", ""),
        "goal": goal,
        "task_type": task_type,
        "replay_passed": replay_passed,
        "actions_ok": actions_ok,
        "state_match": state_match,
        "url_match": url_match,
        "verification_match": verification_match,
        "expected": {
            "after_url": expected_after_url,
            "after_state_hash": expected_after_hash,
            "verification": {
                "causality_strength": expected_verification.get("causality_strength"),
                "gold_eligible": expected_verification.get("gold_eligible"),
                "goal_verified": expected_verification.get("goal_verified"),
            },
        },
        "actual": {
            "after_url": after_snapshot.get("url", ""),
            "after_state_hash": after_snapshot.get("state_hash", ""),
            "verification": verification,
        },
        "replay_trace": replay_trace,
    }


async def replay_paths(paths: List[str], limit: int, headless: bool, include_graph: bool) -> Dict[str, Any]:
    results = []
    for idx, (fp, loc, sample) in enumerate(iter_dataset_samples(paths), start=1):
        if limit and len(results) >= limit:
            break
        print(f"[replay] {len(results) + 1} {rel(fp)} {loc}")
        result = await replay_sample(sample, headless=headless, include_graph=include_graph)
        result["file"] = rel(fp)
        result["location"] = loc
        results.append(result)

    passed = sum(1 for row in results if row.get("replay_passed"))
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.sample_replay_report.v1",
        "total_replayed": len(results),
        "passed": passed,
        "replay_pass_rate": round(passed / max(len(results), 1), 4),
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay BrowserMind gold samples and re-run task verifiers.")
    parser.add_argument("paths", nargs="+", help="Sample files/directories to replay.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    parser.add_argument("--headed", dest="headless", action="store_false")
    parser.add_argument("--no-graph", dest="include_graph", action="store_false")
    parser.set_defaults(headless=True, include_graph=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(replay_paths(args.paths, args.limit, args.headless, args.include_graph))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True) if out.parent != Path(".") else None
        out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
