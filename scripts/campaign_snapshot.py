"""Campaign snapshot -- append-only JSONL trend log for replay campaigns.

Runs in a loop in the background while mass-replay executes. Every INTERVAL
seconds it scans ~/.browsermind/outcome_ledger/ and unknown_fields.jsonl, then
appends one row to ~/.browsermind/campaign_snapshots.jsonl.

Rows are designed to be replayable as a time series -- same shape every row,
no nested aggregation. Plot with pandas/the Timeline Viewer or grep by hand.

Usage:
    python scripts/campaign_snapshot.py                  # 60s interval, runs forever
    python scripts/campaign_snapshot.py --interval 30    # 30s interval
    python scripts/campaign_snapshot.py --once           # snapshot once and exit

Stop with Ctrl-C.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEDGER_DIR = Path.home() / ".browsermind" / "outcome_ledger"
UNKNOWN_QUEUE = Path.home() / ".browsermind" / "unknown_fields.jsonl"
SNAPSHOT_OUT = Path.home() / ".browsermind" / "campaign_snapshots.jsonl"


def _load_ledger_records() -> list[dict]:
    """Read every OutcomeRecord JSON file, return list of inner _data dicts."""
    if not LEDGER_DIR.exists():
        return []
    records = []
    for path in LEDGER_DIR.glob("*.json"):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            data = blob.get("_data", blob)
            records.append(data)
        except Exception:
            continue
    return records


def _count_unknown_fields() -> int:
    if not UNKNOWN_QUEUE.exists():
        return 0
    try:
        with UNKNOWN_QUEUE.open(encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def snapshot() -> dict:
    """Produce one snapshot dict -- pure function, no I/O side effects."""
    records = _load_ledger_records()
    step_records = [r for r in records if r.get("scope") == "step"]
    execution_records = [r for r in records if r.get("scope") == "execution"]

    total_steps = len(step_records)
    successful_steps = sum(1 for r in step_records if r.get("success"))
    effect_verified_true = sum(
        1 for r in step_records if r.get("metrics", {}).get("effect_verified") is True
    )

    total_executions = len(execution_records)
    successful_executions = sum(1 for r in execution_records if r.get("success"))

    resolver_wins: Counter[str] = Counter()
    for r in step_records:
        if not r.get("success"):
            continue
        strategy = r.get("metrics", {}).get("resolved_by") or "unknown"
        resolver_wins[strategy] += 1

    failure_classes: Counter[str] = Counter()
    for r in step_records:
        if r.get("success"):
            continue
        cls = r.get("metrics", {}).get("failure_class") or "unclassified"
        failure_classes[cls] += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_steps": total_steps,
        "successful_steps": successful_steps,
        "step_success_rate": (successful_steps / total_steps) if total_steps else 0.0,
        "effect_verified_true": effect_verified_true,
        "effect_verified_rate": (effect_verified_true / successful_steps) if successful_steps else 0.0,
        "total_executions": total_executions,
        "successful_executions": successful_executions,
        "execution_success_rate": (successful_executions / total_executions) if total_executions else 0.0,
        "unknown_field_count": _count_unknown_fields(),
        "resolver_wins": dict(resolver_wins),
        "failure_classes": dict(failure_classes),
    }


def append_snapshot(row: dict) -> None:
    SNAPSHOT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _format_row_for_console(row: dict) -> str:
    return (
        f"[{row['timestamp']}] "
        f"steps={row['total_steps']} ({row['step_success_rate']:.0%}) "
        f"effect_verified={row['effect_verified_rate']:.0%} "
        f"executions={row['total_executions']} ({row['execution_success_rate']:.0%}) "
        f"unknown_fields={row['unknown_field_count']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Campaign snapshot trend logger")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between snapshots (default 60)")
    parser.add_argument("--once", action="store_true", help="Snapshot once and exit")
    args = parser.parse_args()

    print(f"[snapshot] writing -> {SNAPSHOT_OUT}")
    print(f"[snapshot] interval = {args.interval}s (Ctrl-C to stop)" if not args.once else "[snapshot] one-shot mode")

    try:
        while True:
            row = snapshot()
            append_snapshot(row)
            print(_format_row_for_console(row), flush=True)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[snapshot] stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
