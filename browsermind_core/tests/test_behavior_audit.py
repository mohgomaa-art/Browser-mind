"""Self-Learning v1 — BehaviorAuditLog tests."""
from __future__ import annotations

import json
from pathlib import Path

from browsermind_core.runtime.behavior_audit import BehaviorAuditLog


def _read(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_audit_creates_dir_on_first_write(tmp_path):
    path = tmp_path / "deep" / "nest" / "audit.jsonl"
    log = BehaviorAuditLog(path=path)
    log.memory_prior(persona="alpha", env="saucedemo", picked="capability_intent")
    rows = _read(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["decision_point"] == "target_resolver.memory_prior"
    assert row["prior_source"] == "procedural_memory"
    assert row["picked"] == "capability_intent"
    assert row["fallback_used"] is False


def test_lesson_prior_has_correct_decision_point(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = BehaviorAuditLog(path=path)
    log.lesson_prior(persona="alpha", env="saucedemo", picked="container_proximity")
    rows = _read(path)
    assert rows[0]["decision_point"] == "target_resolver.lesson_prior"
    assert rows[0]["prior_source"] == "lessons.jsonl"


def test_audit_appends_multiple_rows(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = BehaviorAuditLog(path=path)
    for i in range(5):
        log.memory_prior(persona="alpha", env="saucedemo", picked=f"strat-{i}")
    rows = _read(path)
    assert len(rows) == 5
    assert [r["picked"] for r in rows] == [f"strat-{i}" for i in range(5)]


def test_audit_record_swallows_unwritable_path():
    """Unwritable path must not crash the runtime."""
    bad_path = Path("/nonexistent_root_dir_xyz/audit/x.jsonl")
    log = BehaviorAuditLog(path=bad_path)
    log.memory_prior(persona="alpha", env="saucedemo", picked="x")


def test_audit_tail_returns_last_n(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = BehaviorAuditLog(path=path)
    for i in range(20):
        log.memory_prior(persona="p", env="e", picked=f"s-{i}")
    last = log.tail(3)
    assert [r["picked"] for r in last] == ["s-17", "s-18", "s-19"]


def test_audit_tail_on_missing_file_returns_empty(tmp_path):
    log = BehaviorAuditLog(path=tmp_path / "absent.jsonl")
    assert log.tail() == []


def test_audit_extra_payload_is_recorded(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = BehaviorAuditLog(path=path)
    log.lesson_prior(
        persona="alpha", env="saucedemo", picked="container_proximity",
        extra={"rate": 0.85},
    )
    rows = _read(path)
    assert rows[0]["extra"] == {"rate": 0.85}
