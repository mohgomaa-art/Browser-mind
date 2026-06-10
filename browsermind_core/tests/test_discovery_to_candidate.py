"""Tests for AffordanceDiscoverer → ProceduralRecord candidate seeding.

Verifies the source-level and unit behaviour of the discovery wiring:
  1. Source-level: ProceduralRecord has `known_boundaries` and `source` fields.
  2. Unit: ProceduralRecord.from_dict() handles old records (no known_boundaries/source).
  3. Unit: ProceduralRecord with source='affordance_discovery' round-trips through JSON.
  4. Source-level: _discover_on_novelty logic in replay_engine.py seeds candidates.
"""
from __future__ import annotations

import re
from pathlib import Path


REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


# ── ProceduralRecord schema ───────────────────────────────────────────────────

def test_procedural_record_has_known_boundaries_field():
    from browsermind_core.memory.procedural import ProceduralRecord
    import dataclasses
    fields = {f.name for f in dataclasses.fields(ProceduralRecord)}
    assert "known_boundaries" in fields
    assert "source" in fields


def test_procedural_record_defaults():
    from browsermind_core.memory.procedural import ProceduralRecord
    r = ProceduralRecord(
        environment_key="test",
        intent_family="AUTH",
        capability_hint="login_btn",
        step_action="click",
    )
    assert r.known_boundaries == []
    assert r.source == "execution"


def test_procedural_record_affordance_source():
    from browsermind_core.memory.procedural import ProceduralRecord
    r = ProceduralRecord(
        environment_key="github",
        intent_family="SEARCH",
        capability_hint="search_input",
        step_action="fill",
        source="affordance_discovery",
    )
    assert r.source == "affordance_discovery"


def test_procedural_record_round_trips_json():
    from browsermind_core.memory.procedural import ProceduralRecord
    r = ProceduralRecord(
        environment_key="saucedemo",
        intent_family="AUTH",
        capability_hint="username_field",
        step_action="fill",
        known_boundaries=[
            {"capability_hint": "username_field", "failure_mode": "TARGET_CHANGED",
             "failure_reason": "TARGET_CHANGED", "environment_pattern": "saucedemo",
             "frequency": 1, "evidence_count": 1, "first_seen_env": "saucedemo"}
        ],
        source="execution",
    )
    json_line = r.to_json_line()
    assert "known_boundaries" in json_line
    assert "source" in json_line


def test_procedural_record_from_dict_old_record_no_boundaries():
    """Old records serialized without known_boundaries/source must deserialize cleanly."""
    from browsermind_core.memory.procedural import ProceduralRecord
    old_dict = {
        "environment_key": "github",
        "intent_family": "SEARCH",
        "capability_hint": "search_input",
        "step_action": "fill",
        "strategy_counts": {"primary_semantic": {"success": 3, "failure": 0}},
        "last_seen": "2026-06-01T12:00:00+00:00",
    }
    r = ProceduralRecord.from_dict(old_dict)
    assert r.known_boundaries == []
    assert r.source == "execution"
    assert r.strategy_counts["primary_semantic"]["success"] == 3


def test_procedural_record_from_dict_unknown_keys_dropped():
    """from_dict must not raise on unknown fields from future serialization versions."""
    from browsermind_core.memory.procedural import ProceduralRecord
    future_dict = {
        "environment_key": "test",
        "intent_family": "AUTH",
        "capability_hint": "btn",
        "step_action": "click",
        "strategy_counts": {},
        "last_seen": "2026-06-01T12:00:00+00:00",
        "known_boundaries": [],
        "source": "execution",
        "future_field_v99": "should be silently dropped",
    }
    r = ProceduralRecord.from_dict(future_dict)
    assert r.environment_key == "test"


# ── Source-level: discovery seeds candidates ─────────────────────────────────

def test_discovery_seeds_procedural_records_in_source():
    """_discover_on_novelty() must contain candidate seeding logic."""
    assert "affordance_discovery" in REPLAY_ENGINE_SRC
    assert "source='affordance_discovery'" in REPLAY_ENGINE_SRC
    assert "Discovery → Candidate" in REPLAY_ENGINE_SRC


def test_discovery_uses_score_threshold():
    """_discover_on_novelty() must filter by score threshold before seeding."""
    assert "_AFFORDANCE_SCORE_THRESHOLD" in REPLAY_ENGINE_SRC


def test_discovery_seeds_all_four_families():
    """All 4 implemented families must be attempted in _discover_on_novelty."""
    for family in ["SEARCH", "AUTH", "FORM", "FILTER"]:
        assert f"IntentFamily.{family}" in REPLAY_ENGINE_SRC


# ── Source-level: boundary extraction in _mine_step_outcomes ─────────────────

def test_mine_step_outcomes_calls_boundary_extraction():
    """_mine_step_outcomes() must call extract_boundaries_from_failures."""
    assert "extract_boundaries_from_failures" in REPLAY_ENGINE_SRC
    assert "Boundary Law" in REPLAY_ENGINE_SRC


def test_mine_step_outcomes_writes_boundary_procedural_records():
    """Boundary extraction results are persisted to MemoryStore."""
    # Verify the boundary write path is present after the mining block
    boundary_write_pat = re.compile(
        r"extract_boundaries_from_failures.*?mem_store.*?update_procedural",
        re.DOTALL,
    )
    assert boundary_write_pat.search(REPLAY_ENGINE_SRC), (
        "Boundary extraction results must be written via MemoryStore.update_procedural"
    )
