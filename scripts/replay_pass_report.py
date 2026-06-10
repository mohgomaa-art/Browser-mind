from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import iter_dataset_samples, rel


def _truth(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "pass", "passed", "ok", "success", "1"}:
            return True
        if text in {"false", "no", "fail", "failed", "0"}:
            return False
    return None


def _replay_passed(sample: Dict[str, Any]) -> Optional[bool]:
    for key in ("replay_passed", "replay_success", "replay_verified"):
        value = _truth(sample.get(key))
        if value is not None:
            return value
    for key in ("replay", "replay_result"):
        replay = sample.get(key)
        if isinstance(replay, dict):
            for inner in ("passed", "success", "goal_verified"):
                value = _truth(replay.get(inner))
                if value is not None:
                    return value
    verification = sample.get("verification")
    if isinstance(verification, dict):
        return _truth(verification.get("replay_passed"))
    return None


def replay_pass_report(paths: List[str] | None = None, max_examples: int = 25) -> Dict[str, Any]:
    total = 0
    with_replay = 0
    replay_passes = 0
    missing_examples = []
    failed_examples = []

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        replay = _replay_passed(sample)
        if replay is None:
            if len(missing_examples) < max_examples:
                missing_examples.append({"file": rel(fp), "location": loc, "goal": str(sample.get("goal", ""))[:120]})
            continue
        with_replay += 1
        if replay:
            replay_passes += 1
        elif len(failed_examples) < max_examples:
            failed_examples.append({"file": rel(fp), "location": loc, "goal": str(sample.get("goal", ""))[:120]})

    replay_pass_rate = replay_passes / max(with_replay, 1)
    coverage = with_replay / max(total, 1)
    failures = []
    if total <= 0:
        failures.append("total_samples=0")
    if coverage < 1.0:
        failures.append(f"replay_coverage={coverage:.2%}")
    if replay_pass_rate < 0.90:
        failures.append(f"replay_pass_rate={replay_pass_rate:.2%}")

    return {
        "total_samples": total,
        "samples_with_replay_result": with_replay,
        "replay_passes": replay_passes,
        "replay_coverage": round(coverage, 4),
        "replay_pass_rate": round(replay_pass_rate, 4),
        "gate": {
            "passes": not failures,
            "failures": failures,
            "target": "Replay coverage = 100%, Replay Pass Rate > 90%",
            "rule": "A sample that cannot be replayed is not Gold.",
        },
        "missing_examples": missing_examples,
        "failed_examples": failed_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Replay Pass Rate for BrowserMind gold samples.")
    parser.add_argument("paths", nargs="*", help="Gold sample files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = replay_pass_report(args.paths or ["training/gold/samples.json"], max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True) if out.parent != Path(".") else None
        out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
