"""
Unit tests for MissionQueue v2 features (#96):
  - priority-aware next_pending()
  - backoff_until (consecutive failure → exponential backoff)
  - record_run() updates run_history + avg_quality_score
  - auto_skip_expired_pauses()
  - set_priority / schedule_reexplore
  - tag filtering in list_entries()
  - export_csv()
  - persistence round-trip
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pytest

from browsermind_core.mission.mission_queue import MissionQueue, MissionEntry


# ── Helper ────────────────────────────────────────────────────────────────────

def _find(q: MissionQueue, entry_id: str) -> MissionEntry | None:
    """Find entry by id without a dedicated get() method."""
    return next((e for e in q.list_entries() if e.id == entry_id), None)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def q(tmp_path):
    return MissionQueue(tmp_path)


# ── next_pending: priority ordering ──────────────────────────────────────────

def test_next_pending_respects_priority(q):
    """Higher-priority entry is returned first regardless of insertion order."""
    q.add("site_a", priority=0)
    entry_b = q.add("site_b", priority=5)
    q.add("site_c", priority=2)

    first = q.next_pending()
    assert first is not None
    assert first.site_key == "site_b", "Priority 5 should be first"

    q.update(first.id, status="done")
    second = q.next_pending()
    assert second is not None
    assert second.site_key == "site_c", "Priority 2 should be second"


def test_next_pending_returns_none_when_empty(q):
    assert q.next_pending() is None


def test_next_pending_skips_backoff(q):
    """Entry with backoff_until in the future must not be returned."""
    entry_blocked = q.add("blocked_site")
    entry_free = q.add("free_site")

    # Simulate 1 failure → sets backoff_until
    q.record_run(entry_blocked.id, status="failed", steps=0, hypotheses=0, duration=1.0)

    blocked = _find(q, entry_blocked.id)
    if blocked and blocked.backoff_until and blocked.backoff_until > time.time():
        nxt = q.next_pending()
        assert nxt is not None
        assert nxt.site_key == "free_site", "Backed-off entry must be skipped"


def test_next_pending_skips_future_explore_after(q):
    """Entry with next_explore_after in the future must not be returned."""
    entry = q.add("delayed_site")
    q.update(entry.id, next_explore_after=time.time() + 9999)

    result = q.next_pending()
    assert result is None


# ── record_run: run_history & avg_quality_score ───────────────────────────────

def test_record_run_appends_history(q):
    entry = q.add("history_site")
    q.record_run(entry.id, status="done", steps=20, hypotheses=3, duration=12.5, quality_score=0.75)
    q.record_run(entry.id, status="done", steps=30, hypotheses=5, duration=18.0, quality_score=0.85)

    e = _find(q, entry.id)
    assert e is not None
    assert len(e.run_history) == 2
    assert e.run_history[-1]["steps"] == 30
    assert e.run_history[-1]["hypotheses"] == 5


def test_record_run_updates_avg_quality(q):
    entry = q.add("quality_site")
    q.record_run(entry.id, status="done", steps=10, hypotheses=2, duration=5.0, quality_score=0.6)
    q.record_run(entry.id, status="done", steps=10, hypotheses=2, duration=5.0, quality_score=0.8)

    e = _find(q, entry.id)
    assert e is not None
    assert 0.55 < e.avg_quality_score < 0.85, (
        f"avg_quality_score {e.avg_quality_score} not in expected range"
    )


def test_record_run_failure_increments_consecutive_failures(q):
    entry = q.add("failing_site")
    q.record_run(entry.id, status="failed", steps=2, hypotheses=0, duration=3.0)
    e = _find(q, entry.id)
    assert e is not None
    assert e.consecutive_failures >= 1


def test_record_run_success_resets_consecutive_failures(q):
    entry = q.add("recovery_site")
    q.record_run(entry.id, status="failed", steps=1, hypotheses=0, duration=2.0)
    q.record_run(entry.id, status="done", steps=20, hypotheses=4, duration=10.0)
    e = _find(q, entry.id)
    assert e is not None
    assert e.consecutive_failures == 0, "Success should reset failure counter"


def test_record_run_failure_sets_backoff(q):
    entry = q.add("backoff_site")
    q.record_run(entry.id, status="failed", steps=0, hypotheses=0, duration=1.0)
    e = _find(q, entry.id)
    assert e is not None
    assert e.backoff_until is not None
    assert e.backoff_until > time.time()


def test_record_run_paused_sets_paused_since(q):
    entry = q.add("bot_wall_site")
    q.update(entry.id, status="paused")
    q.record_run(entry.id, status="paused", steps=2, hypotheses=0, duration=3.0)
    e = _find(q, entry.id)
    assert e is not None
    assert e.paused_since is not None


# ── auto_skip_expired_pauses ──────────────────────────────────────────────────

def test_auto_skip_expired_pauses(tmp_path):
    """Entries paused for longer than timeout should be auto-skipped."""
    q = MissionQueue(tmp_path, intervention_timeout_hours=0.001)  # 3.6 seconds
    entry = q.add("paused_site")
    q.update(entry.id, status="paused")

    # Manually backdate paused_since beyond the timeout
    entries = q.list_entries()
    for e in entries:
        if e.id == entry.id:
            e.paused_since = time.time() - (q._intervention_timeout_s + 60)
    q._save(entries)

    skipped = q.auto_skip_expired_pauses()
    assert "paused_site" in skipped

    e = _find(q, entry.id)
    assert e is not None
    assert e.status == "skipped"


def test_auto_skip_leaves_fresh_pauses_alone(q):
    entry = q.add("fresh_paused")
    q.update(entry.id, status="paused")
    # paused_since not set → shouldn't be skipped
    skipped = q.auto_skip_expired_pauses()
    assert "fresh_paused" not in skipped


def test_auto_skip_with_no_paused_entries(q):
    q.add("normal_site")
    skipped = q.auto_skip_expired_pauses()
    assert skipped == []


# ── set_priority ─────────────────────────────────────────────────────────────

def test_set_priority(q):
    entry = q.add("promote_me", priority=0)
    q.set_priority("promote_me", 9)
    e = _find(q, entry.id)
    assert e is not None
    assert e.priority == 9


def test_set_priority_returns_false_for_unknown_site(q):
    result = q.set_priority("nonexistent_site", 5)
    assert result is False


# ── schedule_reexplore ────────────────────────────────────────────────────────

def test_schedule_reexplore(q):
    entry = q.add("stale_site")
    q.update(entry.id, status="done")
    q.schedule_reexplore("stale_site", after_hours=0.001)

    e = _find(q, entry.id)
    assert e is not None
    assert e.next_explore_after is not None
    assert e.next_explore_after > time.time() - 1  # set to a near-future time


def test_schedule_reexplore_returns_false_if_not_done(q):
    q.add("pending_site")
    result = q.schedule_reexplore("pending_site", after_hours=1)
    assert result is False, "schedule_reexplore should return False if site is not done"


# ── list_entries with tag filter ─────────────────────────────────────────────

def test_list_entries_tag_filter(q):
    q.add("ecommerce_site", tags=["ecommerce"])
    q.add("social_site", tags=["social"])
    q.add("dev_site", tags=["dev"])

    ecomm = q.list_entries(tag="ecommerce")
    assert len(ecomm) == 1
    assert ecomm[0].site_key == "ecommerce_site"

    all_entries = q.list_entries()
    assert len(all_entries) == 3


def test_list_entries_status_and_tag_combined(q):
    entry1 = q.add("done_social", tags=["social"])
    q.add("pending_social", tags=["social"])
    q.update(entry1.id, status="done")

    results = q.list_entries(status="done", tag="social")
    assert len(results) == 1
    assert results[0].site_key == "done_social"


def test_list_entries_unknown_tag_returns_empty(q):
    q.add("some_site", tags=["known"])
    results = q.list_entries(tag="completely_unknown_tag")
    assert results == []


# ── export_csv ────────────────────────────────────────────────────────────────

def test_export_csv_creates_file(q, tmp_path):
    q.add("csv_site_a", priority=1, tags=["a"])
    q.add("csv_site_b", priority=2, tags=["b"])

    csv_path = tmp_path / "export.csv"
    count = q.export_csv(csv_path)

    assert csv_path.exists()
    assert count == 2
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 2
    site_keys = {r["site_key"] for r in rows}
    assert "csv_site_a" in site_keys
    assert "csv_site_b" in site_keys


def test_export_csv_empty_queue(q, tmp_path):
    csv_path = tmp_path / "empty.csv"
    count = q.export_csv(csv_path)
    assert count == 0


# ── persistence round-trip ────────────────────────────────────────────────────

def test_queue_persists_and_reloads(tmp_path):
    q1 = MissionQueue(tmp_path)
    entry = q1.add("persist_site", priority=3, tags=["reload"])
    q1.record_run(entry.id, status="done", steps=15, hypotheses=3, duration=8.0, quality_score=0.77)

    q2 = MissionQueue(tmp_path)
    e = _find(q2, entry.id)
    assert e is not None
    assert e.site_key == "persist_site"
    assert e.priority == 3
    assert e.tags == ["reload"]
    assert len(e.run_history) == 1
    assert abs(e.avg_quality_score - 0.77) < 0.01


# ── counts / total ────────────────────────────────────────────────────────────

def test_total_counts_all_entries(q):
    for i in range(5):
        q.add(f"site_{i}")
    assert q.total() == 5


def test_counts_by_status(q):
    e1 = q.add("done_1")
    e2 = q.add("done_2")
    e3 = q.add("failed_1")
    q.update(e1.id, status="done")
    q.update(e2.id, status="done")
    q.update(e3.id, status="failed")

    c = q.counts()
    assert c["done"] == 2
    assert c["failed"] == 1
    assert c["pending"] == 0


# ── resume ────────────────────────────────────────────────────────────────────

def test_resume_clears_paused_fields(q):
    entry = q.add("resumable_site")
    q.update(entry.id, status="paused", paused_since=time.time(), backoff_until=time.time() + 9999)
    q.resume("resumable_site")

    e = _find(q, entry.id)
    assert e is not None
    assert e.status == "pending"
    assert e.paused_since is None
    assert e.backoff_until is None
    assert e.consecutive_failures == 0


def test_resume_returns_false_for_non_paused(q):
    q.add("pending_site")
    result = q.resume("pending_site")
    assert result is False
