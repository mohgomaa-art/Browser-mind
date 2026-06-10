from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import ACTION_TO_ID, domain_from_url, stable_json_hash
from scripts.sample_replayer import replay_sample
from training.state_family_extractor import extract_state_family
from training.verification.browser_runtime import (
    ACTION_TYPE_TO_ID,
    NetworkCapture,
    capture_snapshot,
    execute_trace_action,
    normalize_action_type,
)
from training.verification.registry import default_registry, infer_task_type


COLLECTOR_VERSION = "collector_v2.0"


def _load_tasks(path: str, limit: int) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Collector V2 task file must be a JSON list.")
    tasks = [item for item in data if isinstance(item, dict)]
    return tasks[:limit] if limit else tasks


def _default_actions(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = task.get("actions")
    if isinstance(actions, list) and actions:
        return [action for action in actions if isinstance(action, dict)]

    target_url = str(task.get("target_url") or task.get("after_url") or task.get("url") or "").strip()
    if not target_url:
        return []
    return [{"type": "navigate", "action_id": ACTION_TYPE_TO_ID["navigate"], "url": target_url, "target": target_url, "value": target_url}]


def _target_element(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return ""
    first = actions[0]
    return str(first.get("target") or first.get("selector") or first.get("url") or first.get("value") or "")


def _expert_action(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    first = actions[0] if actions else {"type": "done"}
    action_type = normalize_action_type(first)
    return {
        "type": action_type,
        "action_id": int(first.get("action_id") or ACTION_TYPE_TO_ID.get(action_type, ACTION_TO_ID.get(action_type, 7))),
        "element_idx": first.get("element_idx"),
        "value": first.get("value") or first.get("url") or "",
    }


def _sample_hash(sample: Dict[str, Any]) -> str:
    return stable_json_hash(
        {
            "goal": sample.get("goal"),
            "before_url": sample.get("before_url"),
            "after_url": sample.get("after_url"),
            "before_state_hash": sample.get("before_state_hash"),
            "after_state_hash": sample.get("after_state_hash"),
            "execution_trace": sample.get("execution_trace"),
            "verification": sample.get("verification"),
        },
        size=24,
    )


async def collect_one(task: Dict[str, Any], headless: bool = True, include_graph: bool = True) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    from playwright.async_api import async_playwright

    registry = default_registry()
    goal = str(task.get("goal") or "").strip()
    task_id = str(task.get("task_id") or stable_json_hash(task, size=10))
    task_type = str(task.get("task_type") or infer_task_type(goal, task))
    start_url = str(task.get("start_url") or task.get("before_url") or "about:blank").strip()
    actions = _default_actions(task)
    if not goal or not actions:
        return None, {"task_id": task_id, "goal": goal, "reason": "missing_goal_or_actions"}

    action_results: List[Dict[str, Any]] = []
    network_trace: List[Dict[str, Any]] = []
    before_snapshot: Dict[str, Any] = {}
    after_snapshot: Dict[str, Any] = {}
    error = ""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            if start_url and start_url != "about:blank":
                await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
            before_snapshot = await capture_snapshot(page, include_graph=include_graph)

            async with NetworkCapture(page) as net:
                for action in actions:
                    result = await execute_trace_action(page, action, goal=goal)
                    action_results.append(result)
                    if result.get("success") is not True:
                        break
                network_trace = list(net.events)
            after_snapshot = await capture_snapshot(page, include_graph=include_graph)
        except Exception as exc:
            error = str(exc)[:500]
        finally:
            await browser.close()

    trace = {"actions": action_results, "network": network_trace}
    verification = registry.verify(task_type, before_snapshot, after_snapshot, trace, goal=goal).to_dict()
    state_info = extract_state_family(after_snapshot.get("graph", {}).get("nodes", []))
    expert_action = _expert_action(actions)
    sample = {
        "schema": "browsermind.gold_sample.v2",
        "task_id": task_id,
        "task_type": task_type,
        "goal": goal,
        "url": before_snapshot.get("url") or start_url,
        "domain": domain_from_url(str(after_snapshot.get("url") or before_snapshot.get("url") or "")),
        "before_url": before_snapshot.get("url", ""),
        "after_url": after_snapshot.get("url", ""),
        "before_state_hash": before_snapshot.get("state_hash", ""),
        "after_state_hash": after_snapshot.get("state_hash", ""),
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
        "graph": after_snapshot.get("graph", {"nodes": [], "edges": []}),
        "state_family": state_info["state_family"],
        "state_family_hash": state_info["state_family_hash"],
        "execution_trace": action_results,
        "network_trace": network_trace,
        "verification": verification,
        "goal_verified": verification.get("goal_verified") is True,
        "causality_strength": verification.get("causality_strength", ""),
        "verification_signal": verification.get("verifier_name", ""),
        "evidence": {
            "process": verification.get("process_evidence", {}),
            "transition": verification.get("transition_evidence", {}),
            "outcome": verification.get("outcome_evidence", {}),
        },
        "provenance": {
            "source": str(task.get("provenance_source") or "human_curated"),
            "method": str(task.get("provenance_method") or "collector_v2_explicit_trace"),
            "task_file": str(task.get("_task_file") or ""),
        },
        "collector_version": COLLECTOR_VERSION,
        "verifier_version": verification.get("verifier_version", "unknown"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "target_element": _target_element(actions),
        "action": expert_action["type"],
        "expert_action": expert_action,
        "success": False,
        "collection_error": error,
    }
    sample["sample_hash"] = _sample_hash(sample)

    replay = await replay_sample(sample, headless=headless, include_graph=include_graph)
    sample["replay_trace"] = replay.get("replay_trace", {})
    sample["replay_passed"] = replay.get("replay_passed") is True
    sample["replay_result"] = {
        "replay_passed": replay.get("replay_passed") is True,
        "state_match": replay.get("state_match") is True,
        "url_match": replay.get("url_match") is True,
        "verification_match": replay.get("verification_match") is True,
        "actions_ok": replay.get("actions_ok") is True,
    }
    sample["success"] = bool(verification.get("gold_eligible") is True and sample["replay_passed"])

    reasons = []
    if error:
        reasons.append("collection_error")
    if not all(row.get("success") is True for row in action_results):
        reasons.append("execution_trace_failed")
    if verification.get("gold_eligible") is not True:
        reasons.append("verification_not_gold_eligible")
    if sample["replay_passed"] is not True:
        reasons.append("replay_failed")
    if not sample["success"]:
        return None, {
            "task_id": task_id,
            "goal": goal,
            "reasons": reasons,
            "verification": verification,
            "replay_result": sample["replay_result"],
            "after_url": sample["after_url"],
        }
    return sample, None


async def collect_tasks(args: argparse.Namespace) -> Dict[str, Any]:
    tasks = _load_tasks(args.task_file, args.limit)
    for task in tasks:
        task["_task_file"] = args.task_file

    out_dir = Path(args.out_dir)
    quarantine_dir = out_dir / "quarantine"
    out_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    reason_counts = Counter()
    started = time.time()

    for idx, task in enumerate(tasks, start=1):
        print(f"[collector_v2] {idx}/{len(tasks)} {str(task.get('goal', ''))[:100]}")
        sample, reject = await collect_one(task, headless=args.headless, include_graph=not args.no_graph)
        if sample:
            accepted.append(sample)
            print("  -> GOLD")
        else:
            rejected.append(reject or {"task_id": task.get("task_id"), "reason": "unknown_reject"})
            for reason in (reject or {}).get("reasons", ["unknown_reject"]):
                reason_counts[reason] += 1
            print(f"  -> REJECT {(reject or {}).get('reasons', [])}")

    (out_dir / "samples.json").write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (quarantine_dir / "rejected.jsonl").open("w", encoding="utf-8") as f:
        for row in rejected:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.collector_v2_report.v1",
        "collector_version": COLLECTOR_VERSION,
        "task_file": args.task_file,
        "tasks_seen": len(tasks),
        "accepted_samples": len(accepted),
        "rejected_samples": len(rejected),
        "first_airtight_gold_sample": bool(accepted),
        "gold_sample_targets": {
            "first": len(accepted) >= 1,
            "ten": len(accepted) >= 10,
            "hundred": len(accepted) >= 100,
        },
        "reason_counts": dict(reason_counts.most_common()),
        "duration_s": round(time.time() - started, 2),
        "outputs": {
            "samples": str(out_dir / "samples.json"),
            "quarantine": str(quarantine_dir / "rejected.jsonl"),
            "report": str(out_dir / "collector_v2_report.json"),
        },
    }
    gold_report = {
        "generated_at": report["generated_at"],
        "schema": "browsermind.gold_report.v2.collector",
        "source_paths": [args.task_file],
        "collector_version": COLLECTOR_VERSION,
        "total_seen": len(tasks),
        "accepted_samples": len(accepted),
        "rejected_samples": len(rejected),
        "evidence_coverage": round(len(accepted) / max(len(tasks), 1), 4),
        "airtight_samples": len(accepted),
        "causality_distribution": {"airtight": len(accepted)} if accepted else {},
        "provenance_distribution": {"human_curated": len(accepted)} if accepted else {},
        "reason_counts": dict(reason_counts.most_common()),
        "gold_gate": {
            "passes": bool(accepted) and not rejected,
            "rule": "Collector V2 accepts only Execute -> Verify -> Replay samples with causality_strength=airtight.",
        },
        "outputs": report["outputs"],
    }
    (out_dir / "collector_v2_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "gold_report.json").write_text(json.dumps(gold_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collector V2: execute, verify, replay, then write airtight gold samples.")
    parser.add_argument("--task-file", default="training/collector_v2_seed_tasks.json")
    parser.add_argument("--out-dir", default="training/gold_v2")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--headed", dest="headless", action="store_false")
    parser.add_argument("--no-graph", action="store_true", help="Skip AX graph capture for faster smoke runs.")
    parser.set_defaults(headless=True)
    return parser.parse_args()


def main() -> None:
    report = asyncio.run(collect_tasks(parse_args()))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
