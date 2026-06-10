"""LessonReader — runtime consumer of training/lessons_v1/lessons.jsonl.

Mirrors the design of `browsermind_core.memory.memory_reader.MemoryReader`:
  - Cold-start safe (returns {} on missing data).
  - Confidence-gated (MIN_OBSERVATIONS before priors are trusted).
  - Lazy: lessons.jsonl is read on first access. When marked stale via
    notify_steps_recorded(), the next read re-extracts lessons from an
    in-memory OutcomeLedger (when wired) and atomically rewrites the file.

This is the runtime end of the Adaptive Learning v1 loop:

    OutcomeLedger.records  →  lesson_aggregator.extract_lessons
                           →  lessons.jsonl
                           →  LessonReader  ←  TargetResolver, DemonstrationCompiler
"""
from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


class LessonReader:
    """Reads `lessons.jsonl` to surface recovery and action priors.

    Designed as a drop-in alongside MemoryReader. Each public read method
    returns an empty dict (or 0 count) on cold start so callers can use a
    truthy check to gate adaptation.
    """

    MIN_OBSERVATIONS = 3                     # mirrors MemoryReader threshold
    MIN_PRIOR_RATE = 0.5                     # discard buckets that lose more than they win
    REFRESH_AT_STEPS = 50                    # lazy-refresh trigger
    LESSONS_PATH_DEFAULT = Path("training/lessons_v1/lessons.jsonl")

    def __init__(
        self,
        lessons_path: Optional[Path] = None,
        outcome_ledger=None,
    ):
        self._path = Path(lessons_path) if lessons_path else self.LESSONS_PATH_DEFAULT
        self._outcome_ledger = outcome_ledger
        self._lessons: Optional[List[Dict[str, Any]]] = None
        self._stale = False
        self._steps_since_refresh = 0

    # ------------------------------------------------------------------
    # Refresh signal
    # ------------------------------------------------------------------

    def notify_steps_recorded(self, n: int) -> None:
        """Called after each replay's step OutcomeRecords land. When the
        total since the last refresh crosses REFRESH_AT_STEPS, mark stale.
        Refresh itself happens lazily on the next read.
        """
        if n <= 0:
            return
        self._steps_since_refresh += n
        if self._steps_since_refresh >= self.REFRESH_AT_STEPS:
            self._stale = True

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_recovery_priors(self, failure_class: str) -> Dict[str, float]:
        """{recovered_by: success_rate} for the given failure_class.

        Returns {} when:
          - lessons.jsonl is absent or empty
          - no recovery_strategy lesson matches this failure_class
          - the matching bucket has < MIN_OBSERVATIONS
        """
        if not failure_class:
            return {}
        priors: Dict[str, float] = {}
        for l in self._iter_lessons("recovery_strategy"):
            key = l.get("key", {})
            if key.get("failure_class") != failure_class:
                continue
            if l.get("observations", 0) < self.MIN_OBSERVATIONS:
                continue
            recovered_by = key.get("recovered_by")
            if not recovered_by:
                continue
            priors[recovered_by] = float(l.get("success_rate", 0.0))
        return priors

    def get_action_priors(self, action: str, env: str) -> Dict[str, float]:
        """{recovered_by: success_rate} cross-filtered by action + environment.

        Built from the union of `environment_drift` (failure history per env)
        and `recovery_strategy` (which strategies recovered which failure class).
        On cold start or thin data returns {}.
        """
        if not action:
            return {}

        # Failure classes seen in this environment with enough observations.
        env_classes: Dict[str, int] = {}
        if env:
            for l in self._iter_lessons("environment_drift"):
                key = l.get("key", {})
                if key.get("environment_instance") != env:
                    continue
                if l.get("observations", 0) < self.MIN_OBSERVATIONS:
                    continue
                fc = key.get("failure_class")
                if fc:
                    env_classes[fc] = max(env_classes.get(fc, 0), l["observations"])

        # Failure classes that have at least co-occurred with this action.
        action_classes: Dict[str, int] = {}
        for l in self._iter_lessons("action_failure_class"):
            key = l.get("key", {})
            if key.get("action") != action:
                continue
            if l.get("observations", 0) < self.MIN_OBSERVATIONS:
                continue
            fc = key.get("failure_class")
            if fc:
                action_classes[fc] = max(action_classes.get(fc, 0), l["observations"])

        # If we have no env signal, fall back to action-only classes.
        candidate_classes = (
            set(env_classes) & set(action_classes)
            if env_classes and action_classes
            else (set(env_classes) or set(action_classes))
        )
        if not candidate_classes:
            return {}

        # For each candidate class, accumulate recovery success rates.
        sums: Dict[str, float] = defaultdict(float)
        counts: Dict[str, int] = defaultdict(int)
        for l in self._iter_lessons("recovery_strategy"):
            key = l.get("key", {})
            fc = key.get("failure_class")
            if fc not in candidate_classes:
                continue
            if l.get("observations", 0) < self.MIN_OBSERVATIONS:
                continue
            recovered_by = key.get("recovered_by")
            if not recovered_by:
                continue
            sums[recovered_by] += float(l.get("success_rate", 0.0))
            counts[recovered_by] += 1

        return {rb: round(sums[rb] / counts[rb], 4) for rb in sums if counts[rb]}

    def get_step_failure_count(
        self,
        *,
        env: str,
        action: str,
        role: str,
        name: str,
        failure_class: str,
    ) -> int:
        """Observation count for the (env, action, role, name, failure_class)
        descriptor signature. Returns 0 on cold start. Used by the compiler
        approval-layer hook to decide whether to flag a step as AMBIGUOUS.
        """
        for l in self._iter_lessons("step_failure_descriptor"):
            k = l.get("key", {})
            if (
                k.get("environment_instance") == env
                and k.get("action") == action
                and k.get("role") == role
                and k.get("name") == name
                and k.get("failure_class") == failure_class
            ):
                return int(l.get("observations", 0))
        return 0

    # ------------------------------------------------------------------
    # Loading + lazy refresh
    # ------------------------------------------------------------------

    def _iter_lessons(self, kind: str):
        self._ensure_loaded()
        if not self._lessons:
            return
        for l in self._lessons:
            if l.get("kind") == kind:
                if l.get("quarantined"):
                    continue
                yield l

    def _ensure_loaded(self) -> None:
        if self._lessons is None:
            self._lessons = self._read_jsonl()
            self._stale = False
            return
        if self._stale:
            if self._outcome_ledger is not None:
                self._refresh_from_ledger()
            self._lessons = self._read_jsonl()
            self._stale = False
            self._steps_since_refresh = 0

    def _read_jsonl(self) -> List[Dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            out: List[Dict[str, Any]] = []
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            if self._outcome_ledger is not None and out:
                from training.effectiveness_tracker import (
                    compute_effectiveness,
                    apply_effectiveness,
                )
                try:
                    eff = compute_effectiveness(
                        list(self._outcome_ledger.records), out
                    )
                    apply_effectiveness(out, eff)
                except Exception:
                    pass
            return out
        except Exception:
            return []

    def _refresh_from_ledger(self) -> None:
        """Re-extract lessons from the in-memory OutcomeLedger and atomically
        replace lessons.jsonl. Must never raise — refresh failures are not
        worth crashing a replay over. Errors are printed for forensics.
        """
        try:
            from training.lesson_aggregator import extract_lessons

            records = list(getattr(self._outcome_ledger, "records", []))
            lessons = extract_lessons(records)

            from training.effectiveness_tracker import (
                validate_for_promotion,
                stamp_promotion,
                compute_effectiveness,
                apply_effectiveness,
            )
            for l in lessons:
                # Only consider promoting recovery_strategy lessons; the other
                # kinds are observational and not consumed at runtime as priors.
                if l.get("kind") != "recovery_strategy":
                    continue
                if l.get("promoted_at"):  # already promoted in a prior cycle
                    continue
                ok, _reason = validate_for_promotion(l, records)
                if ok:
                    stamp_promotion(l)
            eff = compute_effectiveness(records, lessons)
            apply_effectiveness(lessons, eff)

            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=".lessons_", suffix=".jsonl", dir=str(self._path.parent)
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    for l in lessons:
                        f.write(json.dumps(l, ensure_ascii=False) + "\n")
                os.replace(tmp_name, self._path)
            except Exception:
                if os.path.exists(tmp_name):
                    try:
                        os.remove(tmp_name)
                    except OSError:
                        pass
                raise
        except Exception as e:
            print(f"  [LessonReader] refresh failed: {e}")
