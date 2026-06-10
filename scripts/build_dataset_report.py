from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_actions import audit_actions
from scripts.audit_success_labels import audit_success_labels
from scripts.action_coverage_report import action_coverage
from scripts.dataset_integrity import dataset_integrity
from scripts.evidence_audit import evidence_audit
from scripts.observation_audit import observation_audit
from scripts.provenance_report import provenance_report
from scripts.replay_pass_report import replay_pass_report
from training.state_family_extractor import analyze_state_families


def _duplicate_status(rate: float) -> str:
    if rate < 0.10:
        return "pass"
    if rate <= 0.20:
        return "warning"
    return "critical"


def _training_gate(report: Dict) -> Dict:
    integrity = report["integrity"]
    actions = report["actions"]
    success = report["success_labels"]
    evidence = report.get("evidence", {})
    provenance = report.get("provenance", {})
    replay = report.get("replay", {})
    state_families = report.get("state_families", {})

    duplicate_rate = float(integrity.get("duplicate_rate", 0.0))
    total_samples = int(integrity.get("total_samples", 0))
    invalid_actions = int(actions.get("invalid_actions", 0))
    suspicious_success = int(success.get("suspicious", 0))
    incomplete_evidence = int(evidence.get("incomplete_evidence_samples", 0))
    synthetic_suspect = int(evidence.get("synthetic_suspect_samples", 0))
    heuristic_like_rate = float(provenance.get("heuristic_like_rate", 0.0))
    unknown_rate = float(provenance.get("unknown_rate", 0.0))
    replay_total = int(replay.get("total_samples", 0))
    replay_coverage = float(replay.get("replay_coverage", 0.0))
    replay_pass_rate = float(replay.get("replay_pass_rate", 0.0))
    families_over_cap = len(state_families.get("families_over_cap", {}))
    domains_over_cap = len(state_families.get("domains_over_cap", {}))

    failures = []
    warnings = []

    if invalid_actions:
        failures.append(f"invalid_actions={invalid_actions}")
    if total_samples <= 0:
        failures.append("total_samples=0")
    if duplicate_rate > 0.20:
        failures.append(f"duplicate_rate={duplicate_rate:.2%}")
    elif duplicate_rate >= 0.10:
        warnings.append(f"duplicate_rate={duplicate_rate:.2%}")
    if suspicious_success:
        failures.append(f"suspicious_success_labels={suspicious_success}")
    if incomplete_evidence:
        failures.append(f"incomplete_evidence_samples={incomplete_evidence}")
    if synthetic_suspect:
        failures.append(f"synthetic_suspect_samples={synthetic_suspect}")
    if heuristic_like_rate >= 0.95:
        failures.append(f"heuristic_like_rate={heuristic_like_rate:.2%}")
    elif heuristic_like_rate >= 0.80:
        warnings.append(f"heuristic_like_rate={heuristic_like_rate:.2%}")
    if unknown_rate > 0:
        failures.append(f"unknown_provenance_rate={unknown_rate:.2%}")
    if replay_total > 0 and replay_coverage < 1.0:
        failures.append(f"replay_coverage={replay_coverage:.2%}")
    if replay_total > 0 and replay_pass_rate < 0.90:
        failures.append(f"replay_pass_rate={replay_pass_rate:.2%}")
    if families_over_cap:
        failures.append(f"state_families_over_cap={families_over_cap}")
    if domains_over_cap:
        failures.append(f"domains_over_cap={domains_over_cap}")

    return {
        "training_allowed": not failures,
        "duplicate_status": _duplicate_status(duplicate_rate),
        "failures": failures,
        "warnings": warnings,
        "rule": "No training without an audit report and passing data gates.",
    }


def build_dataset_report(paths: List[str] | None, max_examples: int = 25) -> Dict:
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.dataset_report.v1",
        "paths": paths or ["default_audit_roots"],
        "actions": audit_actions(paths, max_examples=max_examples),
        "success_labels": audit_success_labels(paths, max_examples=max_examples),
        "integrity": dataset_integrity(paths, max_examples=max_examples),
        "coverage": action_coverage(paths),
        "observation": observation_audit(paths, max_examples=max_examples),
        "evidence": evidence_audit(paths, max_examples=max_examples),
        "provenance": provenance_report(paths, max_examples=max_examples),
        "replay": replay_pass_report(paths, max_examples=max_examples),
        "state_families": analyze_state_families(paths, max_examples=max_examples),
    }
    report["training_gate"] = _training_gate(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BrowserMind dataset_report.json.")
    parser.add_argument("paths", nargs="*", help="Dataset files/directories to audit.")
    parser.add_argument("--out", default="dataset_report.json")
    parser.add_argument("--max-examples", type=int, default=25)
    args = parser.parse_args()

    report = build_dataset_report(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True) if out_path.parent != Path(".") else None
    out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
