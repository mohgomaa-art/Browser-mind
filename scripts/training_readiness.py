from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evidence_audit import evidence_audit
from scripts.provenance_report import provenance_report
from scripts.replay_pass_report import replay_pass_report
from scripts.gold_coverage_report import coverage_report


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _gold_samples_count(samples_path: Path) -> int:
    data = _load_json(samples_path, default=[])
    return len(data) if isinstance(data, list) else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Training readiness gate (Phase 4.6).")
    ap.add_argument("--samples", default="training/gold/samples.json")
    ap.add_argument("--human-audit", default="reports/human_audit.json")
    ap.add_argument("--out", default="reports/training_readiness.json")
    args = ap.parse_args()

    samples_path = Path(args.samples)
    gold_samples = _gold_samples_count(samples_path)

    evidence = evidence_audit([str(samples_path)])
    provenance = provenance_report([str(samples_path)])
    replay = replay_pass_report([str(samples_path)])
    coverage = coverage_report(samples_path)

    human_audit = _load_json(Path(args.human_audit), default={})
    human_approval = float(human_audit.get("approval_rate") or 0.0) if isinstance(human_audit, dict) else 0.0

    replay_rate = float(replay.get("replay_pass_rate") or 0.0) if isinstance(replay, dict) else 0.0
    evidence_coverage = float(1.0 - (evidence.get("incomplete_evidence_rate") or 1.0)) if isinstance(evidence, dict) else 0.0

    state_families = len((coverage.get("state_families") or {}) if isinstance(coverage, dict) else {})
    domains = len((coverage.get("domains") or {}) if isinstance(coverage, dict) else {})

    ready = (
        gold_samples >= 150
        and replay_rate >= 0.90
        and evidence_coverage >= 0.95
        and human_approval >= 0.95
        and state_families >= 20
        and domains >= 20
    )

    report = {
        "generated_at": _now_iso(),
        "schema": "browsermind.training_readiness.v1",
        "gold_samples": gold_samples,
        "replay_rate": round(replay_rate, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "human_approval": round(human_approval, 4),
        "state_families": state_families,
        "domains": domains,
        "ready_for_training": bool(ready),
        "inputs": {
            "evidence_audit": evidence,
            "provenance_report": provenance,
            "replay_pass_report": replay,
            "coverage_report": coverage,
            "human_audit": human_audit,
        },
        "criteria": {
            "gold_samples_min": 150,
            "replay_rate_min": 0.90,
            "evidence_coverage_min": 0.95,
            "human_approval_min": 0.95,
            "state_families_min": 20,
            "domains_min": 20,
        },
    }

    _write_json(Path(args.out), report)
    print(f"[ok] wrote {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()

