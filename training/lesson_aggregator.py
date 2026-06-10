"""Lesson Aggregator — Phase 4 of the BC-readiness plan.

Reads OutcomeRecord rows of scope='step' produced by ReplayEngine and emits
durable Lessons. A Lesson is a (pattern → observation) tuple summarising what
the OutcomeLedger has learned. No model is trained; no runtime behaviour is
mutated. Lessons are knowledge artefacts a future learner can read.

Lesson schema (v1):
    {
      "schema_version": "browsermind.lesson.v1",
      "lesson_id": str,            # deterministic hash of (kind, key_tuple)
      "kind": str,                 # see LessonKind below
      "key": dict,                 # the pattern (e.g. {"failure_class": "TARGET_CHANGED"})
      "observations": int,         # how many step rows matched
      "outcomes": {                # success vs failure breakdown
          "success": int,
          "failure": int
      },
      "success_rate": float,
      "examples": [str, ...],      # up to 5 row_ids for traceability
      "first_seen": iso8601,
      "last_seen": iso8601
    }

Kinds emitted by this module:
    failure_class           — failure_class → frequency + recovery rate
    recovery_strategy       — (failure_class, recovered_by) → success rate
    resolution_strategy     — resolved_by → success rate
    action_failure_class    — (action, failure_class) → frequency
    environment_drift       — (environment_instance, failure_class) → frequency
    predicted_vs_actual     — (predicted_tier, actual_outcome) → calibration

Inputs come from either:
  - a list of OutcomeRecord (test path), or
  - a KernelSession store_dir (production path).

Outputs:
  - lessons.jsonl            — one Lesson per row
  - lesson_manifest.json     — counts and version
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from browsermind_core.ledger.outcome_ledger import OutcomeRecord


SCHEMA_VERSION = "browsermind.lesson.v1"


def _is_step(rec: OutcomeRecord) -> bool:
    return rec.scope == "step" and rec.outcome_type == "step_attempt"


def _key_to_str(kind: str, key: Tuple) -> str:
    payload = json.dumps([kind, list(key)], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class _Bucket:
    __slots__ = ("success", "failure", "examples", "first_seen", "last_seen")

    def __init__(self):
        self.success = 0
        self.failure = 0
        self.examples: List[str] = []
        self.first_seen: Optional[datetime] = None
        self.last_seen: Optional[datetime] = None

    def add(self, rec: OutcomeRecord):
        if rec.success:
            self.success += 1
        else:
            self.failure += 1
        if len(self.examples) < 5:
            self.examples.append(str(rec.id))
        if self.first_seen is None or rec.timestamp < self.first_seen:
            self.first_seen = rec.timestamp
        if self.last_seen is None or rec.timestamp > self.last_seen:
            self.last_seen = rec.timestamp

    @property
    def total(self) -> int:
        return self.success + self.failure

    @property
    def rate(self) -> float:
        return (self.success / self.total) if self.total else 0.0

    def to_lesson(self, kind: str, key: Dict[str, Any]) -> Dict[str, Any]:
        key_tuple = tuple(sorted(key.items()))
        return {
            "schema_version": SCHEMA_VERSION,
            "lesson_id": _key_to_str(kind, key_tuple),
            "kind": kind,
            "key": dict(key),
            "observations": self.total,
            "outcomes": {"success": self.success, "failure": self.failure},
            "success_rate": round(self.rate, 4),
            "examples": list(self.examples),
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


def extract_lessons(records: Iterable[OutcomeRecord]) -> List[Dict[str, Any]]:
    """Mine the OutcomeLedger for lessons. Pure function over records."""
    by_kind: Dict[str, Dict[Tuple, _Bucket]] = defaultdict(lambda: defaultdict(_Bucket))

    for rec in records:
        if not _is_step(rec):
            continue
        m = rec.metrics or {}

        action = m.get("action") or "unknown"
        failure_class = m.get("failure_class")
        resolved_by = m.get("resolved_by")
        recovered_by = m.get("recovered_by")
        predicted_tier = m.get("predicted_tier") or "UNKNOWN"
        actual_outcome = m.get("actual_outcome") or ("SUCCESS" if rec.success else "FAILED")

        if failure_class:
            by_kind["failure_class"][(("failure_class", failure_class),)].add(rec)
            if recovered_by:
                by_kind["recovery_strategy"][
                    (("failure_class", failure_class), ("recovered_by", recovered_by))
                ].add(rec)
            by_kind["action_failure_class"][
                (("action", action), ("failure_class", failure_class))
            ].add(rec)
            if rec.environment_instance:
                by_kind["environment_drift"][
                    (("environment_instance", rec.environment_instance),
                     ("failure_class", failure_class))
                ].add(rec)
            by_kind["step_failure_descriptor"][
                (("environment_instance", rec.environment_instance),
                 ("action", action),
                 ("role", m.get("role") or ""),
                 ("name", m.get("name") or ""),
                 ("failure_class", failure_class))
            ].add(rec)

        if resolved_by:
            by_kind["resolution_strategy"][(("resolved_by", resolved_by),)].add(rec)

        by_kind["predicted_vs_actual"][
            (("predicted_tier", predicted_tier), ("actual_outcome", actual_outcome))
        ].add(rec)

    lessons: List[Dict[str, Any]] = []
    for kind, buckets in by_kind.items():
        for key_tuple, bucket in buckets.items():
            lessons.append(bucket.to_lesson(kind, dict(key_tuple)))

    lessons.sort(key=lambda l: (l["kind"], -l["observations"], l["lesson_id"]))
    return lessons


def build_manifest(lessons: List[Dict[str, Any]], source_ledgers: List[str]) -> Dict[str, Any]:
    by_kind: Dict[str, int] = defaultdict(int)
    for l in lessons:
        by_kind[l["kind"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ledgers": source_ledgers,
        "lesson_count": len(lessons),
        "lessons_by_kind": dict(by_kind),
    }


def write_lessons(
    lessons: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    lessons_path = output_dir / "lessons.jsonl"
    manifest_path = output_dir / "lesson_manifest.json"
    with lessons_path.open("w", encoding="utf-8") as f:
        for l in lessons:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {"lessons": lessons_path, "manifest": manifest_path}


def build_from_store(store_dir: str, output_dir: str) -> Dict[str, Any]:
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
    from browsermind_core.ledger.outcome_repository import OutcomeRepository

    provider = LocalJSONPersistenceProvider(store_dir)
    repo = OutcomeRepository(provider)
    records = repo.load_all()
    lessons = extract_lessons(records)
    manifest = build_manifest(lessons, source_ledgers=[os.fspath(Path(store_dir).resolve())])
    paths = write_lessons(lessons, manifest, Path(output_dir))
    return {
        "lessons_written": len(lessons),
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
        default="training/lessons_v1",
        help="Output directory for lessons.jsonl and lesson_manifest.json",
    )
    args = parser.parse_args()
    result = build_from_store(args.store_dir, args.output)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
