from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


def _load_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def telemetry_attribution(records: Iterable[Dict]) -> Dict:
    rows = list(records)
    source_counts = Counter(r.get("decision_source") or ("fallback" if r.get("fallback_used") else "unknown") for r in rows)
    total_steps = sum(source_counts.values())
    task_sources = defaultdict(Counter)
    task_success = defaultdict(list)

    for r in rows:
        task_id = r.get("task_id") or "unknown"
        src = r.get("decision_source") or ("fallback" if r.get("fallback_used") else "unknown")
        task_sources[task_id][src] += 1
        task_success[task_id].append(bool(r.get("success")))

    policy_step_success = sum(1 for r in rows if r.get("decision_source") == "policy" and r.get("success"))
    policy_steps = source_counts.get("policy", 0)
    fallback_step_success = sum(1 for r in rows if r.get("decision_source") == "fallback" and r.get("success"))
    fallback_steps = source_counts.get("fallback", 0)

    inferred_task_successes = {
        task_id: all(vals) for task_id, vals in task_success.items()
    }
    policy_independent = sum(
        1
        for task_id, ok in inferred_task_successes.items()
        if ok and task_sources[task_id].get("fallback", 0) == 0
    )
    fallback_rescue = sum(
        1
        for task_id, ok in inferred_task_successes.items()
        if ok and task_sources[task_id].get("fallback", 0) > 0
    )

    return {
        "total_steps": total_steps,
        "policy_steps": policy_steps,
        "fallback_steps": fallback_steps,
        "planner_steps": source_counts.get("planner", 0),
        "policy_steps_pct": round(policy_steps / max(total_steps, 1), 4),
        "fallback_steps_pct": round(fallback_steps / max(total_steps, 1), 4),
        "policy_step_success_pct": round(policy_step_success / max(policy_steps, 1), 4),
        "fallback_step_success_pct": round(fallback_step_success / max(fallback_steps, 1), 4),
        "policy_independent_success": policy_independent,
        "fallback_rescue": fallback_rescue,
        "source_counts": dict(source_counts),
    }


def benchmark_attribution(report: Dict) -> Dict:
    modes = {m.get("mode"): m for m in report.get("modes", [])}
    policy = modes.get("policy_only", {})
    heuristic = modes.get("heuristic_only", {})
    full = modes.get("full_system", {})

    policy_rate = float(policy.get("success_rate", 0.0))
    heuristic_rate = float(heuristic.get("success_rate", 0.0))
    full_rate = float(full.get("success_rate", 0.0))

    full_tasks = {r.get("task_id"): r for r in full.get("results", [])}
    policy_tasks = {r.get("task_id"): r for r in policy.get("results", [])}
    heuristic_tasks = {r.get("task_id"): r for r in heuristic.get("results", [])}

    paired_rescues = 0
    paired_policy_only_wins = 0
    paired_heuristic_only_wins = 0
    policy_independent = 0
    fallback_rescue = 0
    decision_sources = Counter()

    for task_id, full_result in full_tasks.items():
        steps = full_result.get("steps", [])
        for step in steps:
            decision_sources[step.get("decision_source", "unknown")] += 1

        full_ok = bool(full_result.get("success"))
        policy_ok = bool(policy_tasks.get(task_id, {}).get("success"))
        heuristic_ok = bool(heuristic_tasks.get(task_id, {}).get("success"))
        used_fallback = any(step.get("decision_source") == "fallback" for step in steps)

        if full_ok and not policy_ok:
            paired_rescues += 1
        if full_ok and not used_fallback:
            policy_independent += 1
        if full_ok and used_fallback:
            fallback_rescue += 1
        if policy_ok and not heuristic_ok:
            paired_policy_only_wins += 1
        if heuristic_ok and not policy_ok:
            paired_heuristic_only_wins += 1

    total_decisions = sum(decision_sources.values())
    return {
        "policy_success_rate": policy_rate,
        "heuristic_success_rate": heuristic_rate,
        "full_success_rate": full_rate,
        "policy_contribution_vs_heuristic": round(full_rate - heuristic_rate, 4),
        "full_gain_vs_policy": round(full_rate - policy_rate, 4),
        "paired_fallback_rescues": paired_rescues,
        "paired_policy_only_wins": paired_policy_only_wins,
        "paired_heuristic_only_wins": paired_heuristic_only_wins,
        "policy_independent_success": policy_independent,
        "fallback_rescue": fallback_rescue,
        "policy_steps": decision_sources.get("policy", 0),
        "fallback_steps": decision_sources.get("fallback", 0),
        "policy_steps_pct": round(decision_sources.get("policy", 0) / max(total_decisions, 1), 4),
        "fallback_steps_pct": round(decision_sources.get("fallback", 0) / max(total_decisions, 1), 4),
        "decision_source_counts": dict(decision_sources),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute BrowserMind attribution metrics.")
    parser.add_argument("path", help="Benchmark JSON report or telemetry JSONL file.")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    path = Path(args.path)
    if path.suffix.lower() == ".jsonl":
        report = telemetry_attribution(_load_jsonl(path))
    else:
        report = benchmark_attribution(json.loads(path.read_text(encoding="utf-8")))

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
