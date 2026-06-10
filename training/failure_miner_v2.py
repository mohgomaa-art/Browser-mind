from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List


FAILURE_CATEGORIES = [
    "observation",
    "wrong_action",
    "wrong_element",
    "execution",
    "popup",
    "environment",
    "sparse_graph",
    "timeout",
    "other",
]


def _normalise_failure(value: str) -> str:
    text = (value or "").strip().lower()
    aliases = {
        "policy": "wrong_element",
        "target_element_missing": "observation",
        "empty_graph": "sparse_graph",
        "no_signal_matched": "wrong_action",
        "": "other",
        "unknown": "other",
    }
    text = aliases.get(text, text)
    if text not in FAILURE_CATEGORIES:
        if "timeout" in text:
            return "timeout"
        if "sparse" in text:
            return "sparse_graph"
        if "target" in text or "locator" in text or "element" in text:
            return "wrong_element"
        if "net::" in text or "navigation" in text:
            return "environment"
        return "other"
    return text


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


def _failures_from_benchmark(report: Dict, mode: str = "policy_only") -> List[Dict]:
    failures = []
    for mode_report in report.get("modes", []):
        if mode and mode_report.get("mode") != mode:
            continue
        for task in mode_report.get("results", []):
            if task.get("success"):
                continue
            failure_type = _normalise_failure(str(task.get("failure_type", "")))
            if failure_type == "timeout":
                steps = task.get("steps", [])
                if steps:
                    failure_type = _normalise_failure(str(steps[-1].get("failure_type", "timeout")))
            failures.append(
                {
                    "task_id": task.get("task_id"),
                    "goal": task.get("goal", ""),
                    "mode": mode_report.get("mode"),
                    "failure_type": failure_type,
                    "steps": len(task.get("steps", [])),
                    "last_step": (task.get("steps") or [{}])[-1],
                }
            )
    return failures


def _failures_from_telemetry(records: Iterable[Dict]) -> List[Dict]:
    failures = []
    for row in records:
        if row.get("success"):
            continue
        failures.append(
            {
                "task_id": row.get("task_id"),
                "goal": row.get("goal", ""),
                "mode": "telemetry",
                "failure_type": _normalise_failure(str(row.get("failure_type", ""))),
                "steps": row.get("step", 0),
                "last_step": row,
            }
        )
    return failures


def mine_failures(path: Path, mode: str = "policy_only", max_examples: int = 25) -> Dict:
    if path.suffix.lower() == ".jsonl":
        failures = _failures_from_telemetry(_load_jsonl(path))
        source = "telemetry"
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
        failures = _failures_from_benchmark(report, mode=mode)
        source = "benchmark"

    counts = Counter(f["failure_type"] for f in failures)
    total = sum(counts.values())
    distribution = {
        category: round(counts.get(category, 0) / max(total, 1), 4)
        for category in FAILURE_CATEGORIES
        if counts.get(category, 0)
    }

    wrong_element = counts.get("wrong_element", 0)
    sparse = counts.get("sparse_graph", 0)
    gates = {
        "contrastive_loss_eligible": total > 0 and wrong_element / max(total, 1) > 0.50,
        "vision_eligible": total > 0 and sparse / max(total, 1) > 0.50,
        "wrong_element_rate": round(wrong_element / max(total, 1), 4),
        "sparse_graph_failure_rate": round(sparse / max(total, 1), 4),
    }

    return {
        "source": source,
        "path": str(path),
        "mode": mode if source == "benchmark" else "telemetry",
        "total_failures": total,
        "failure_counts": dict(counts),
        "failure_distribution": distribution,
        "largest_failure_category": counts.most_common(1)[0][0] if counts else "",
        "decision_gates": gates,
        "examples": failures[:max_examples],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine BrowserMind failures into a taxonomy dashboard.")
    parser.add_argument("path", help="Real benchmark JSON or telemetry JSONL file.")
    parser.add_argument("--mode", default="policy_only", help="Benchmark mode to mine.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = mine_failures(Path(args.path), mode=args.mode, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
