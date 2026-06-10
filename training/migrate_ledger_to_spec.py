"""Convert OutcomeLedger episode JSONL into the legacy `spec_sessions` layout.

Bridge only. New code should consume the JSONL directly via
`train_bc_v2.py`. This script exists so the legacy `train_bc.py` can run
against modern data without rewriting the legacy GraphDataset path.

Usage:
  python training/migrate_ledger_to_spec.py training/dataset_v1.jsonl training/spec_sessions
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate(jsonl_path: str, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    episodes = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            episodes.append(json.loads(line))

    by_template: dict[str, list[dict]] = {}
    for ep in episodes:
        tid = ep.get("template_id") or "unknown"
        by_template.setdefault(tid, []).append(ep)

    for tid, eps in by_template.items():
        eps_sorted = sorted(eps, key=lambda e: e.get("step_seq", 0))
        payload = {
            "session_id": tid,
            "source": "outcome_ledger",
            "site": eps_sorted[0].get("site") if eps_sorted else "",
            "steps": eps_sorted,
        }
        (out / f"{tid}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Migrated {len(episodes)} episodes across {len(by_template)} templates -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: migrate_ledger_to_spec.py <jsonl> <out_dir>", file=sys.stderr)
        sys.exit(2)
    migrate(sys.argv[1], sys.argv[2])
