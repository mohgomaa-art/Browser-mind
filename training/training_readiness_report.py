"""Training Readiness Report — Phase 5 of the BC-readiness plan.

Reads the OutcomeLedger, the dataset emitted by `outcome_ledger_adapter`, the
lessons emitted by `lesson_aggregator`, and the ground-truth files to compute
six readiness metrics:

  - replay_success_rate     workflow-instance level success ratio
  - outcome_accuracy        share of step rows whose effect_verified is True
                            (None and False are not counted as positive)
  - failure_coverage        share of failed step rows that carry a non-UNKNOWN
                            failure_class — measures classification reach
  - dataset_yield           rows in the dataset / step records in ledger
  - lesson_yield            number of lessons / step records in ledger
  - ground_truth_coverage   sites with ground-truth file / sites in ledger

Emits training_readiness_report.json with these metrics, the source paths,
and a verdict block. The verdict thresholds are deliberately conservative:

    READY_FOR_BC requires:
      - >= 200 step records
      - replay_success_rate     >= 0.5
      - failure_coverage        >= 0.8
      - dataset_yield           >= 0.95
      - ground_truth_coverage   >= 0.5

    READY_FOR_LIMITED_LEARNING requires:
      - >= 50 step records
      - dataset_yield           >= 0.95

Anything below is NOT_READY.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from browsermind_core.ledger.outcome_ledger import OutcomeRecord


SCHEMA_VERSION = "browsermind.training_readiness.v1"

GROUND_TRUTH_DIR_DEFAULT = "ground_truth"
DATASET_PATH_DEFAULT = "training/bc_dataset_v1"
LESSONS_PATH_DEFAULT = "training/lessons_v1"


def _step_rows(records: List[OutcomeRecord]) -> List[OutcomeRecord]:
    return [r for r in records if r.scope == "step" and r.outcome_type == "step_attempt"]


def _run_rows(records: List[OutcomeRecord]) -> List[OutcomeRecord]:
    return [
        r for r in records
        if r.scope == "workflow_instance" and r.outcome_type == "replay_run"
    ]


def _replay_success_rate(records: List[OutcomeRecord]) -> Optional[float]:
    runs = _run_rows(records)
    if not runs:
        return None
    successes = sum(1 for r in runs if r.success)
    return round(successes / len(runs), 4)


def _outcome_accuracy(steps: List[OutcomeRecord]) -> Optional[float]:
    if not steps:
        return None
    verified_true = sum(
        1 for r in steps if (r.metrics or {}).get("effect_verified") is True
    )
    return round(verified_true / len(steps), 4)


def _failure_coverage(steps: List[OutcomeRecord]) -> Optional[float]:
    failed = [r for r in steps if not r.success]
    if not failed:
        return None
    classified = sum(
        1 for r in failed
        if (r.metrics or {}).get("failure_class")
        and (r.metrics or {}).get("failure_class") != "UNKNOWN"
    )
    return round(classified / len(failed), 4)


def _count_jsonl(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def _dataset_yield(steps_count: int, dataset_path: Path) -> Optional[float]:
    if not steps_count:
        return None
    rows = _count_jsonl(dataset_path / "dataset.jsonl")
    if rows is None:
        return None
    return round(rows / steps_count, 4)


def _lesson_yield(steps_count: int, lessons_path: Path) -> Optional[float]:
    if not steps_count:
        return None
    lessons = _count_jsonl(lessons_path / "lessons.jsonl")
    if lessons is None:
        return None
    return round(lessons / steps_count, 4)


def _ground_truth_coverage(
    steps: List[OutcomeRecord],
    gt_dir: Path,
) -> Optional[float]:
    if not steps:
        return None
    sites_in_ledger = {
        (r.metrics or {}).get("environment_key") or r.environment_instance
        for r in steps
        if (r.metrics or {}).get("environment_key") or r.environment_instance
    }
    sites_in_ledger.discard(None)
    sites_in_ledger.discard("")
    sites_in_ledger.discard("unknown")
    if not sites_in_ledger:
        return None
    if not gt_dir.exists():
        return 0.0
    available = {p.stem for p in gt_dir.glob("*.json")}
    matched = sites_in_ledger & available
    return round(len(matched) / len(sites_in_ledger), 4)


def _verdict(metrics: Dict[str, Any], steps_count: int) -> Dict[str, Any]:
    rsr = metrics.get("replay_success_rate") or 0.0
    fc = metrics.get("failure_coverage") or 0.0
    dy = metrics.get("dataset_yield") or 0.0
    gtc = metrics.get("ground_truth_coverage") or 0.0

    if (
        steps_count >= 200
        and rsr >= 0.5
        and fc >= 0.8
        and dy >= 0.95
        and gtc >= 0.5
    ):
        verdict = "READY_FOR_BC"
    elif steps_count >= 50 and dy >= 0.95:
        verdict = "READY_FOR_LIMITED_LEARNING"
    else:
        verdict = "NOT_READY"

    return {
        "verdict": verdict,
        "reasons": {
            "step_records": steps_count,
            "replay_success_rate": rsr,
            "failure_coverage": fc,
            "dataset_yield": dy,
            "ground_truth_coverage": gtc,
        },
        "thresholds": {
            "READY_FOR_BC": {
                "step_records": 200,
                "replay_success_rate": 0.5,
                "failure_coverage": 0.8,
                "dataset_yield": 0.95,
                "ground_truth_coverage": 0.5,
            },
            "READY_FOR_LIMITED_LEARNING": {
                "step_records": 50,
                "dataset_yield": 0.95,
            },
        },
    }


def build_readiness_report(
    records: List[OutcomeRecord],
    *,
    dataset_path: Path,
    lessons_path: Path,
    ground_truth_dir: Path,
    source_store: str,
) -> Dict[str, Any]:
    steps = _step_rows(records)
    steps_count = len(steps)
    runs = _run_rows(records)

    sites_in_ledger = sorted({
        (r.metrics or {}).get("environment_key") or r.environment_instance
        for r in steps
        if (r.metrics or {}).get("environment_key") or r.environment_instance
    })

    metrics = {
        "replay_success_rate": _replay_success_rate(records),
        "outcome_accuracy": _outcome_accuracy(steps),
        "failure_coverage": _failure_coverage(steps),
        "dataset_yield": _dataset_yield(steps_count, dataset_path),
        "lesson_yield": _lesson_yield(steps_count, lessons_path),
        "ground_truth_coverage": _ground_truth_coverage(steps, ground_truth_dir),
    }

    failure_class_dist = Counter(
        (r.metrics or {}).get("failure_class") or "NONE" for r in steps
    )
    action_dist = Counter((r.metrics or {}).get("action") or "unknown" for r in steps)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_store": source_store,
        "sources": {
            "dataset_path": os.fspath(dataset_path),
            "lessons_path": os.fspath(lessons_path),
            "ground_truth_dir": os.fspath(ground_truth_dir),
        },
        "counts": {
            "step_records": steps_count,
            "run_records": len(runs),
            "sites_in_ledger": sites_in_ledger,
        },
        "metrics": metrics,
        "distributions": {
            "failure_class": dict(failure_class_dist),
            "action": dict(action_dist),
        },
        "verdict": _verdict(metrics, steps_count),
    }


def write_report(report: Dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_path


def build_from_store(
    store_dir: str,
    *,
    dataset_dir: str = DATASET_PATH_DEFAULT,
    lessons_dir: str = LESSONS_PATH_DEFAULT,
    ground_truth_dir: str = GROUND_TRUTH_DIR_DEFAULT,
    output_path: str = "reports/training_readiness_report.json",
) -> Dict[str, Any]:
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
    from browsermind_core.ledger.outcome_repository import OutcomeRepository

    provider = LocalJSONPersistenceProvider(store_dir)
    repo = OutcomeRepository(provider)
    records = repo.load_all()
    report = build_readiness_report(
        records,
        dataset_path=Path(dataset_dir),
        lessons_path=Path(lessons_dir),
        ground_truth_dir=Path(ground_truth_dir),
        source_store=os.fspath(Path(store_dir).resolve()),
    )
    out = write_report(report, Path(output_path))
    return {"path": os.fspath(out), "report": report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-dir", default=str(Path.home() / ".browsermind"))
    parser.add_argument("--dataset-dir", default=DATASET_PATH_DEFAULT)
    parser.add_argument("--lessons-dir", default=LESSONS_PATH_DEFAULT)
    parser.add_argument("--ground-truth-dir", default=GROUND_TRUTH_DIR_DEFAULT)
    parser.add_argument(
        "--output", default="reports/training_readiness_report.json"
    )
    args = parser.parse_args()
    result = build_from_store(
        args.store_dir,
        dataset_dir=args.dataset_dir,
        lessons_dir=args.lessons_dir,
        ground_truth_dir=args.ground_truth_dir,
        output_path=args.output,
    )
    print(json.dumps(result["report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
