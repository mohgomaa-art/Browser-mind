"""Candidate yield aggregator.

Reads OutcomeRecords from a BrowserMind store and produces a candidate-yield
report:

  - applications_attempted        (count of replay runs scoped at workflow_instance)
  - applications_submitted         (count of contract_verification records with success=True)
  - submission_rate                applications_submitted / applications_attempted
  - per_template / per_environment_instance breakdowns
  - per_step false_positive_rate   (effect_verified=True on a step that was followed by
                                    contract_verification=False on the same execution)

Designed to run after Path 8 — the operator-driven recording session against real
ATS sites — produces OutcomeLedger rows.

Usage:
  python -m browsermind_core.training.candidate_yield --store ~/.browsermind --out reports/candidate_yield.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from browsermind_core.ledger.outcome_ledger import OutcomeLedger
from browsermind_core.ledger.outcome_repository import OutcomeRepository
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


def aggregate(records: List[Any]) -> Dict[str, Any]:
    runs = [r for r in records if r.scope == "workflow_instance"]
    contract_records = [r for r in records if r.outcome_type == "contract_verification"]
    step_records = [r for r in records if r.scope == "step"]

    applications_attempted = len(runs)
    applications_submitted = sum(1 for r in contract_records if r.success)

    by_env: Dict[str, Dict[str, int]] = defaultdict(lambda: {"attempted": 0, "submitted": 0})
    for r in runs:
        by_env[r.environment_instance or "unknown"]["attempted"] += 1
    for r in contract_records:
        key = r.environment_instance or "unknown"
        if r.success:
            by_env[key]["submitted"] += 1

    by_template: Dict[str, Dict[str, int]] = defaultdict(lambda: {"attempted": 0, "submitted": 0})
    for r in runs:
        tname = (r.metrics or {}).get("template_name") or str(r.metrics.get("template_id", "unknown"))
        by_template[tname]["attempted"] += 1
    for r in contract_records:
        tname = (r.metrics or {}).get("template_name") or (r.metrics or {}).get("contract_id", "unknown")
        if r.success:
            by_template[tname]["submitted"] += 1

    failed_executions = {
        r.execution_id for r in contract_records if not r.success and r.execution_id
    }
    step_fp_total = 0
    step_fp_effect_verified_true = 0
    for s in step_records:
        if s.execution_id in failed_executions:
            step_fp_total += 1
            if (s.metrics or {}).get("effect_verified") is True:
                step_fp_effect_verified_true += 1
    step_fpr = (step_fp_effect_verified_true / step_fp_total) if step_fp_total else 0.0

    failure_classes = Counter(
        (s.metrics or {}).get("failure_class") for s in step_records
        if (s.metrics or {}).get("failure_class")
    )

    return {
        "totals": {
            "applications_attempted": applications_attempted,
            "applications_submitted": applications_submitted,
            "submission_rate": (applications_submitted / applications_attempted) if applications_attempted else 0.0,
            "step_records": len(step_records),
            "contract_records": len(contract_records),
            "step_false_positive_rate_in_failed_runs": round(step_fpr, 4),
        },
        "by_environment_instance": dict(by_env),
        "by_template": dict(by_template),
        "step_failure_classes": dict(failure_classes),
        "decision": _decision(applications_attempted, applications_submitted),
    }


def _decision(attempted: int, submitted: int) -> Dict[str, Any]:
    if attempted == 0:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "reason": "no workflow_instance OutcomeRecords found; run an operator session first",
        }
    rate = submitted / attempted
    if rate >= 0.5:
        return {"verdict": "PROMOTE", "reason": f"submission_rate={rate:.2f} ≥ 0.50"}
    if rate >= 0.2:
        return {"verdict": "ITERATE", "reason": f"submission_rate={rate:.2f} in (0.20, 0.50)"}
    return {"verdict": "DEBUG", "reason": f"submission_rate={rate:.2f} < 0.20 — investigate dominant failure_class"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--store", default=str(Path.home() / ".browsermind"))
    p.add_argument("--out", default="reports/candidate_yield.json")
    args = p.parse_args()

    provider = LocalJSONPersistenceProvider(args.store)
    repo = OutcomeRepository(provider)
    ledger = OutcomeLedger(repository=repo)

    report = aggregate(ledger.records)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
