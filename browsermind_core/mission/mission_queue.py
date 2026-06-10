"""
MissionQueue — persistent JSON-backed queue for autonomous exploration missions.

Enhanced with:
  - Priority queue (#26): priority field, next_pending() returns highest priority first
  - Per-site run history (#29): run_history list with per-run metrics
  - Site health / backoff (#28): backoff_until field, consecutive_failures counter
  - Intervention timeout / auto-skip (#82): paused_since field, auto_skip_after_hours
  - Re-exploration scheduling (#35): next_explore_after field
  - Evidence quality scoring (#77): avg_quality_score tracked per entry

Status lifecycle:
  pending  →  running  →  done
                       →  failed   (re-queued if attempts < max_retries)
                       →  paused   (bot wall / human required)
                       →  skipped  (permanently excluded or intervention timed out)
"""
from __future__ import annotations

import json
import time
import uuid as _uuid_mod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


VALID_STATUSES = frozenset(["pending", "running", "done", "failed", "paused", "skipped"])

# Default intervention timeout: auto-skip paused entries after this many hours
DEFAULT_INTERVENTION_TIMEOUT_HOURS = 48.0


@dataclass
class RunRecord:
    """Metrics from a single exploration run on one site."""
    ts: float
    status: str         # done | failed | paused
    steps: int
    hypotheses: int
    duration: float
    error: Optional[str] = None
    quality_score: float = 0.0


@dataclass
class MissionEntry:
    id: str
    site_key: str
    persona: str
    budget: int
    status: str
    attempts: int
    max_retries: int
    tags: List[str]
    added_at: float
    priority: int = 0               # higher = runs first (#26)
    last_run_ts: Optional[float] = None
    last_error:  Optional[str]  = None
    last_steps:  Optional[int]  = None
    last_hypotheses: Optional[int] = None
    last_experiences: Optional[List[str]] = field(default=None)
    last_duration: Optional[float] = None

    # Health / backoff (#28)
    consecutive_failures: int = 0
    backoff_until: Optional[float] = None  # unix timestamp — don't pick until this time

    # Intervention timeout (#82)
    paused_since: Optional[float] = None   # unix timestamp when entry was paused

    # Re-exploration scheduling (#35)
    next_explore_after: Optional[float] = None  # unix timestamp

    # Quality tracking (#77)
    avg_quality_score: float = 0.0
    run_history: List[dict] = field(default_factory=list)  # serialized RunRecord list

    @classmethod
    def create(
        cls,
        site_key: str,
        persona: str = "validator",
        budget: int = 200,
        tags: Optional[List[str]] = None,
        max_retries: int = 2,
        priority: int = 0,
    ) -> "MissionEntry":
        return cls(
            id=str(_uuid_mod.uuid4()),
            site_key=site_key,
            persona=persona,
            budget=budget,
            status="pending",
            attempts=0,
            max_retries=max_retries,
            tags=list(tags or []),
            added_at=time.time(),
            priority=priority,
        )

    def add_run_record(
        self,
        status: str,
        steps: int,
        hypotheses: int,
        duration: float,
        error: Optional[str] = None,
        quality_score: float = 0.0,
    ) -> None:
        record = {
            "ts": time.time(),
            "status": status,
            "steps": steps,
            "hypotheses": hypotheses,
            "duration": duration,
            "error": error,
            "quality_score": quality_score,
        }
        self.run_history = (self.run_history or [])[-49:] + [record]
        # Recompute average quality score
        scores = [r["quality_score"] for r in self.run_history if r.get("quality_score", 0) > 0]
        self.avg_quality_score = sum(scores) / len(scores) if scores else 0.0


class MissionQueue:
    """
    Persistent queue stored as a single JSON file.

    Priority: entries with higher `priority` value are popped first.
    Backoff: entries with `backoff_until > now` are skipped.
    Intervention timeout: paused entries older than threshold are auto-skipped.
    """

    def __init__(
        self,
        store_dir: Path,
        intervention_timeout_hours: float = DEFAULT_INTERVENTION_TIMEOUT_HOURS,
    ) -> None:
        self._dir = Path(store_dir) / "missions"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "queue.json"
        self._intervention_timeout_s = intervention_timeout_hours * 3600

    # ── Persistence ──────────────────────────────────────────────────────

    def _load(self) -> List[MissionEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            entries = []
            for raw in data.get("entries", []):
                try:
                    # run_history is a list of dicts — safe to pass as-is
                    entries.append(MissionEntry(**raw))
                except Exception:
                    pass
            return entries
        except Exception:
            return []

    def _save(self, entries: List[MissionEntry]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"entries": [asdict(e) for e in entries]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)  # atomic rename (#77)

    # ── Write operations ─────────────────────────────────────────────────

    def add(
        self,
        site_key: str,
        persona: str = "validator",
        budget: int = 200,
        tags: Optional[List[str]] = None,
        max_retries: int = 2,
        priority: int = 0,
        allow_duplicate: bool = False,
    ) -> MissionEntry:
        entries = self._load()
        if not allow_duplicate:
            for e in entries:
                if e.site_key == site_key and e.persona == persona \
                        and e.status in ("pending", "paused", "running"):
                    return e
        entry = MissionEntry.create(site_key, persona, budget, tags, max_retries, priority)
        entries.append(entry)
        self._save(entries)
        return entry

    def add_bulk(
        self,
        site_keys: List[str],
        persona: str = "validator",
        budget: int = 200,
        tags: Optional[List[str]] = None,
        max_retries: int = 2,
        priority: int = 0,
    ) -> int:
        added = 0
        for key in site_keys:
            entries = self._load()
            already = any(
                e.site_key == key and e.persona == persona
                and e.status in ("pending", "paused", "running")
                for e in entries
            )
            if not already:
                entry = MissionEntry.create(key, persona, budget, tags, max_retries, priority)
                entries.append(entry)
                self._save(entries)
                added += 1
        return added

    def update(self, entry_id: str, **kwargs) -> None:
        entries = self._load()
        for e in entries:
            if e.id == entry_id:
                for k, v in kwargs.items():
                    if hasattr(e, k):
                        setattr(e, k, v)
                break
        self._save(entries)

    def record_run(
        self,
        entry_id: str,
        status: str,
        steps: int,
        hypotheses: int,
        duration: float,
        error: Optional[str] = None,
        quality_score: float = 0.0,
    ) -> None:
        """Record a completed run into the entry's run_history (#29)."""
        entries = self._load()
        for e in entries:
            if e.id == entry_id:
                e.add_run_record(status, steps, hypotheses, duration, error, quality_score)
                e.last_run_ts = time.time()
                e.last_steps = steps
                e.last_hypotheses = hypotheses
                e.last_duration = duration
                e.last_error = error
                # Update health tracking (#28)
                if status == "failed":
                    e.consecutive_failures = (e.consecutive_failures or 0) + 1
                    # Exponential backoff: 15min * 2^failures, max 12h
                    backoff_s = min(900 * (2 ** e.consecutive_failures), 43200)
                    e.backoff_until = time.time() + backoff_s
                else:
                    e.consecutive_failures = 0
                    e.backoff_until = None
                # Re-exploration scheduling: revisit done sites after 30 days (#35)
                if status == "done":
                    e.next_explore_after = time.time() + 30 * 86400
                # Intervention tracking
                if status == "paused":
                    e.paused_since = time.time()
                break
        self._save(entries)

    def remove(self, entry_id: str) -> bool:
        entries = self._load()
        before = len(entries)
        entries = [e for e in entries if e.id != entry_id]
        self._save(entries)
        return len(entries) < before

    def clear(self, status: str) -> int:
        entries = self._load()
        before = len(entries)
        entries = [e for e in entries if e.status != status]
        self._save(entries)
        return before - len(entries)

    def reset_running(self) -> int:
        entries = self._load()
        count = 0
        for e in entries:
            if e.status == "running":
                e.status = "pending"
                count += 1
        if count:
            self._save(entries)
        return count

    def resume(self, site_key: str) -> bool:
        entries = self._load()
        found = False
        for e in entries:
            if e.site_key == site_key and e.status == "paused":
                e.status = "pending"
                e.paused_since = None
                e.backoff_until = None
                e.consecutive_failures = 0
                found = True
        if found:
            self._save(entries)
        return found

    def auto_skip_expired_pauses(self) -> List[str]:
        """
        Auto-skip paused entries whose intervention timeout has elapsed (#82).
        Returns list of site_keys that were skipped.
        """
        if self._intervention_timeout_s <= 0:
            return []
        now = time.time()
        entries = self._load()
        skipped = []
        for e in entries:
            if e.status == "paused" and e.paused_since:
                if now - e.paused_since > self._intervention_timeout_s:
                    e.status = "skipped"
                    e.last_error = f"intervention_timeout: paused for >{self._intervention_timeout_s/3600:.0f}h"
                    skipped.append(e.site_key)
        if skipped:
            self._save(entries)
        return skipped

    def set_priority(self, site_key: str, priority: int) -> bool:
        """Change priority of all pending/paused entries for a site (#26)."""
        entries = self._load()
        found = False
        for e in entries:
            if e.site_key == site_key and e.status in ("pending", "paused"):
                e.priority = priority
                found = True
        if found:
            self._save(entries)
        return found

    def schedule_reexplore(self, site_key: str, after_hours: float = 24.0) -> bool:
        """Re-queue a done entry for re-exploration after N hours (#35)."""
        entries = self._load()
        found = False
        for e in entries:
            if e.site_key == site_key and e.status == "done":
                e.status = "pending"
                e.next_explore_after = time.time() + after_hours * 3600
                found = True
        if found:
            self._save(entries)
        return found

    # ── Read operations ──────────────────────────────────────────────────

    def next_pending(self) -> Optional[MissionEntry]:
        """
        Return next pending entry respecting priority and backoff (#26, #28).
        Highest priority wins; among equal priority, FIFO.
        """
        now = time.time()
        candidates = [
            e for e in self._load()
            if e.status == "pending"
            and (e.backoff_until is None or e.backoff_until <= now)
            and (e.next_explore_after is None or e.next_explore_after <= now)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: (e.priority, -e.added_at))

    def list_entries(
        self,
        status: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[MissionEntry]:
        entries = self._load()
        if status:
            entries = [e for e in entries if e.status == status]
        if tag:
            entries = [e for e in entries if tag in (e.tags or [])]
        return entries

    def get_run_history(self, site_key: str) -> List[dict]:
        """Return full run history for a site (#29)."""
        for e in self._load():
            if e.site_key == site_key:
                return e.run_history or []
        return []

    def counts(self) -> Dict[str, int]:
        result: Dict[str, int] = {s: 0 for s in VALID_STATUSES}
        for e in self._load():
            result[e.status] = result.get(e.status, 0) + 1
        return result

    def total(self) -> int:
        return len(self._load())

    def export_csv(self, path: Path) -> int:
        """Export queue to CSV for offline analysis (#93)."""
        import csv
        entries = self._load()
        if not entries:
            return 0
        fields = [
            "id", "site_key", "persona", "budget", "status", "priority",
            "attempts", "max_retries", "tags", "added_at", "last_run_ts",
            "last_error", "last_steps", "last_hypotheses", "last_duration",
            "consecutive_failures", "avg_quality_score",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for e in entries:
                row = asdict(e)
                row["tags"] = "|".join(row.get("tags", []))
                row.pop("run_history", None)
                row.pop("last_experiences", None)
                w.writerow(row)
        return len(entries)
