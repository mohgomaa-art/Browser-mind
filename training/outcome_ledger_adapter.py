"""OutcomeLedger -> training-dataset adapter.

Phase 3 of the BC-readiness plan. Reads OutcomeRecord rows of scope='step'
out of a persisted OutcomeLedger and emits:
    - dataset.jsonl       (one training row per step attempt)
    - dataset_manifest.json (schema_version, source_ledgers, sample_count,
                             label_distribution)

Scope is deliberately small: no model schema, no element graph, no embedding.
This adapter only converts ledger rows into rows a downstream trainer can
read without manual intervention.

Schema v1 (training row):
    {
      "schema_version": "browsermind.bc_dataset.v1",
      "row_id": str,
      "step_id": str,           # deterministic 32-char hash
      "workflow_id": str,       # scope_id (UUID)
      "execution_id": str|null,
      "persona_id": str,
      "environment_family": str,
      "environment_instance": str,
      "action": str,            # click/fill/press/...
      "role": str,
      "name": str,
      "success": bool,
      "label": str,             # "SUCCESS" | "FAILED" | "TRANSITION_SUCCESS" |
                                # "AMBIGUOUS_IDENTITY" | "ASK"
      "failure_class": str|null,
      "root_cause": str|null,
      "effect_type": str|null,
      "effect_verified": bool|null,
      "resolved_by": str|null,
      "recovered_by": str|null,
      "predicted_tier": str,
      "predicted_score": float,
      "resolution_time_ms": int|null,
      "weight": float,          # 1.0 success, 0.1 failure (matches train_bc.py)
      "timestamp": iso8601
    }

Usage:
    python -m training.outcome_ledger_adapter \
        --store-dir ~/.browsermind \
        --output    training/bc_dataset_v1
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from browsermind_core.ledger.outcome_ledger import OutcomeRecord


SCHEMA_VERSION = "browsermind.bc_dataset.v1"

SUCCESS_LABELS = ("SUCCESS", "TRANSITION_SUCCESS")


def _row_from_record(rec: OutcomeRecord) -> Optional[Dict[str, Any]]:
    """Convert one step-scope OutcomeRecord into a training row.

    Returns None when the record is not a step attempt or lacks the
    required metrics fields.
    """
    if rec.scope != "step":
        return None
    if rec.outcome_type != "step_attempt":
        return None

    m = rec.metrics or {}
    actual = m.get("actual_outcome") or ("SUCCESS" if rec.success else "FAILED")
    weight = 1.0 if actual in SUCCESS_LABELS else 0.1

    return {
        "schema_version": SCHEMA_VERSION,
        "row_id": str(rec.id),
        "step_id": m.get("step_id"),
        "workflow_id": str(rec.scope_id),
        "execution_id": str(rec.execution_id) if rec.execution_id else None,
        "persona_id": str(rec.persona_id),
        "environment_family": rec.environment_family,
        "environment_instance": rec.environment_instance,
        "action": m.get("action"),
        "role": m.get("role", ""),
        "name": m.get("name", ""),
        "success": bool(rec.success),
        "label": actual,
        "failure_class": m.get("failure_class"),
        "root_cause": m.get("root_cause"),
        "effect_type": m.get("effect_type"),
        "effect_verified": m.get("effect_verified"),
        "resolved_by": m.get("resolved_by"),
        "recovered_by": m.get("recovered_by"),
        "predicted_tier": m.get("predicted_tier", ""),
        "predicted_score": float(m.get("predicted_score") or 0.0),
        "resolution_time_ms": m.get("resolution_time_ms"),
        "weight": weight,
        "timestamp": rec.timestamp.isoformat(),
    }


def build_rows(records: Iterable[OutcomeRecord]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in records:
        row = _row_from_record(rec)
        if row is not None:
            rows.append(row)
    return rows


def build_manifest(
    rows: List[Dict[str, Any]],
    source_ledgers: List[str],
) -> Dict[str, Any]:
    label_dist: Counter[str] = Counter(row["label"] for row in rows)
    failure_class_dist: Counter[str] = Counter(
        (row.get("failure_class") or "NONE") for row in rows
    )
    action_dist: Counter[str] = Counter(
        (row.get("action") or "unknown") for row in rows
    )
    success_count = sum(1 for r in rows if r["success"])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ledgers": source_ledgers,
        "sample_count": len(rows),
        "success_count": success_count,
        "failure_count": len(rows) - success_count,
        "success_rate": (success_count / len(rows)) if rows else 0.0,
        "label_distribution": dict(label_dist),
        "failure_class_distribution": dict(failure_class_dist),
        "action_distribution": dict(action_dist),
    }


def write_dataset(
    rows: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "dataset.jsonl"
    manifest_path = output_dir / "dataset_manifest.json"

    with dataset_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return {"dataset": dataset_path, "manifest": manifest_path}


def load_records_from_store(store_dir: str) -> List[OutcomeRecord]:
    """Load OutcomeRecords from a store_dir managed by KernelSession."""
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
    from browsermind_core.ledger.outcome_repository import OutcomeRepository

    provider = LocalJSONPersistenceProvider(store_dir)
    repo = OutcomeRepository(provider)
    return repo.load_all()


def build_from_store(store_dir: str, output_dir: str) -> Dict[str, Any]:
    records = load_records_from_store(store_dir)
    rows = build_rows(records)
    manifest = build_manifest(rows, source_ledgers=[os.fspath(Path(store_dir).resolve())])
    paths = write_dataset(rows, manifest, Path(output_dir))
    return {
        "rows_written": len(rows),
        "manifest": manifest,
        "paths": {k: os.fspath(v) for k, v in paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store-dir",
        default=str(Path.home() / ".browsermind"),
        help="KernelSession store directory containing the OutcomeRepository",
    )
    parser.add_argument(
        "--output",
        default="training/bc_dataset_v1",
        help="Output directory for dataset.jsonl and dataset_manifest.json",
    )
    args = parser.parse_args()

    result = build_from_store(args.store_dir, args.output)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
