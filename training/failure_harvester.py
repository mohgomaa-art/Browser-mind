from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ACTIONABLE_FAILURES = {"wrong_element", "wrong_action"}
IGNORED_FAILURES = {
    "environment",
    "sparse_graph",
    "observation",
    "popup",
    "timeout",
    "network",
}
# Bot-detection failures are not ignored — they map to BOT_DETECTED attribution
# and are used to identify which sites require anti_bot_tier > 0 in SiteRegistry.
BOT_FAILURES = {"cloudflare", "anti_bot"}


def _normalise_failure(value: str) -> str:
    text = (value or "").strip().lower()
    if text in ACTIONABLE_FAILURES:
        return text
    if text == "policy":
        return "wrong_element"
    if "wrong action" in text:
        return "wrong_action"
    if "wrong element" in text or "locator" in text or "target" in text:
        return "wrong_element"
    if "timeout" in text:
        return "timeout"
    if "cloudflare" in text or "captcha" in text or "anti_bot" in text or "bot_detected" in text:
        return "bot_detected"
    if "net::" in text or "network" in text or "navigation" in text:
        return "environment"
    if "popup" in text or "modal" in text:
        return "popup"
    if "sparse" in text or "empty_graph" in text:
        return "sparse_graph"
    if "observation" in text:
        return "observation"
    return text or "unknown"


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _iter_inputs(paths: List[str]) -> Iterator[tuple[Path, Dict[str, Any]]]:
    for item in paths:
        path = Path(item)
        if path.is_dir():
            for fp in sorted(path.rglob("*.json")) + sorted(path.rglob("*.jsonl")):
                yield from _iter_inputs([str(fp)])
            continue
        if not path.exists():
            continue
        if path.suffix.lower() == ".jsonl":
            for row in _iter_jsonl(path):
                yield path, row
        else:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            yield path, data


def _records_from_benchmark(path: Path, report: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    for mode_report in report.get("modes", []):
        mode = mode_report.get("mode", "")
        for task in mode_report.get("results", []):
            if task.get("success"):
                continue
            steps = task.get("steps") or []
            last = steps[-1] if steps else {}
            failure_type = _normalise_failure(str(last.get("failure_type") or task.get("failure_type", "")))
            yield {
                "source_file": str(path),
                "source_mode": mode,
                "task_id": task.get("task_id"),
                "goal": task.get("goal", ""),
                "url": task.get("url", ""),
                "failure_type": failure_type,
                "graph": last.get("graph") or task.get("graph") or {},
                "prediction": {
                    "action": last.get("action"),
                    "action_id": last.get("action_id"),
                    "element_idx": last.get("element_idx"),
                    "confidence": last.get("confidence"),
                },
                "correct_action": last.get("correct_action") or task.get("correct_action"),
                "correct_element": last.get("correct_element") or task.get("correct_element"),
                "raw": task,
            }


def _record_from_telemetry(path: Path, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if row.get("success"):
        return None
    failure_type = _normalise_failure(str(row.get("failure_type", "")))
    return {
        "source_file": str(path),
        "source_mode": "telemetry",
        "task_id": row.get("task_id"),
        "goal": row.get("goal", ""),
        "url": row.get("url", ""),
        "failure_type": failure_type,
        "graph": row.get("graph", {}),
        "prediction": {
            "action": row.get("action"),
            "target_idx": row.get("target_idx"),
            "target_name": row.get("target_name"),
            "confidence": row.get("confidence"),
        },
        "correct_action": row.get("correct_action"),
        "correct_element": row.get("correct_element"),
        "raw": row,
    }


def _has_correction(record: Dict[str, Any]) -> bool:
    return bool(record.get("correct_action")) and record.get("correct_element") is not None


def harvest_failures(paths: List[str], out_dir: str = "training/failure_buffer/harvested", max_examples: int = 25) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    accepted_path  = out / "policy_failures.jsonl"
    review_path    = out / "needs_review.jsonl"
    ignored_path   = out / "ignored.jsonl"
    bot_path       = out / "bot_detected.jsonl"

    counters = Counter()
    examples = []

    accepted_f = accepted_path.open("w", encoding="utf-8")
    review_f   = review_path.open("w", encoding="utf-8")
    ignored_f  = ignored_path.open("w", encoding="utf-8")
    bot_f      = bot_path.open("w", encoding="utf-8")
    try:
        for path, payload in _iter_inputs(paths):
            if isinstance(payload, dict) and "modes" in payload:
                records = list(_records_from_benchmark(path, payload))
            elif isinstance(payload, dict):
                rec = _record_from_telemetry(path, payload)
                records = [rec] if rec else []
            else:
                records = []

            for record in records:
                if not record:
                    continue
                counters["seen"] += 1
                failure_type = _normalise_failure(record.get("failure_type", ""))
                record["failure_type"] = failure_type
                record["harvested_at"] = datetime.utcnow().isoformat() + "Z"

                # Bot-detection failures get their own bucket for site tier analysis.
                if failure_type in BOT_FAILURES or failure_type == "bot_detected":
                    counters["bot_detected"] += 1
                    record["actual_outcome"] = "BOT_DETECTED"
                    bot_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    continue

                if failure_type in IGNORED_FAILURES or failure_type not in ACTIONABLE_FAILURES:
                    counters[f"ignored_{failure_type}"] += 1
                    ignored_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    continue

                if _has_correction(record):
                    counters["accepted"] += 1
                    accepted_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                else:
                    counters["needs_review"] += 1
                    record["review_reason"] = "missing_correct_action_or_correct_element"
                    review_f.write(json.dumps(record, ensure_ascii=False) + "\n")

                if len(examples) < max_examples:
                    examples.append(
                        {
                            "task_id": record.get("task_id"),
                            "failure_type": failure_type,
                            "goal": str(record.get("goal", ""))[:160],
                            "status": "accepted" if _has_correction(record) else "needs_review",
                        }
                    )
    finally:
        accepted_f.close()
        review_f.close()
        ignored_f.close()
        bot_f.close()

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.failure_harvest.v1",
        "source_paths": paths,
        "target": "1000 high-quality corrected wrong-action/wrong-element failures",
        "counts": dict(counters),
        "outputs": {
            "accepted": str(accepted_path),
            "needs_review": str(review_path),
            "ignored": str(ignored_path),
            "report": str(out / "harvest_report.json"),
        },
        "examples": examples,
        "rules": {
            "accepted_failure_types": sorted(ACTIONABLE_FAILURES),
            "ignored_failure_types": sorted(IGNORED_FAILURES),
            "requires_human_correction": True,
        },
    }
    (out / "harvest_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest actionable policy failures for human correction.")
    parser.add_argument("paths", nargs="+", help="Benchmark JSON, telemetry JSONL, or directories.")
    parser.add_argument("--out-dir", default="training/failure_buffer/harvested")
    parser.add_argument("--max-examples", type=int, default=25)
    args = parser.parse_args()

    report = harvest_failures(args.paths, out_dir=args.out_dir, max_examples=args.max_examples)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
