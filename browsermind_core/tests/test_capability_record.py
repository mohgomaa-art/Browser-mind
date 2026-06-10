"""Tests for CapabilityRecord — first-class capability object.

Verifies:
  - Schema fields and defaults
  - Lifecycle tier transitions
  - transfer_envs tracking
  - JSON round-trip and from_dict forward-compat
  - invariant_hash property on InvariantGraph
"""
from __future__ import annotations

import json


# ── InvariantGraph.invariant_hash ────────────────────────────────────────────

def test_invariant_hash_is_deterministic():
    from browsermind_core.representation.p5_schemas import InvariantGraph
    g1 = InvariantGraph(goal_id="a", demonstrations_count=1, invariants=["AUTHENTICATE", "LOCATE"])
    g2 = InvariantGraph(goal_id="b", demonstrations_count=5, invariants=["LOCATE", "AUTHENTICATE"])
    assert g1.invariant_hash == g2.invariant_hash, "Same invariant set must hash identically regardless of order"


def test_invariant_hash_different_sets_differ():
    from browsermind_core.representation.p5_schemas import InvariantGraph
    g1 = InvariantGraph(goal_id="a", demonstrations_count=1, invariants=["AUTHENTICATE"])
    g2 = InvariantGraph(goal_id="a", demonstrations_count=1, invariants=["LOCATE"])
    assert g1.invariant_hash != g2.invariant_hash


def test_invariant_hash_length():
    from browsermind_core.representation.p5_schemas import InvariantGraph
    g = InvariantGraph(goal_id="x", demonstrations_count=1, invariants=["AUTHENTICATE", "ACT"])
    assert len(g.invariant_hash) == 16


def test_invariant_hash_empty_invariants():
    from browsermind_core.representation.p5_schemas import InvariantGraph
    g = InvariantGraph(goal_id="x", demonstrations_count=0)
    assert isinstance(g.invariant_hash, str)
    assert len(g.invariant_hash) == 16


def test_invariant_hash_goal_id_ignored():
    from browsermind_core.representation.p5_schemas import InvariantGraph
    g1 = InvariantGraph(goal_id="goal-1", demonstrations_count=1, invariants=["ACT"])
    g2 = InvariantGraph(goal_id="goal-99", demonstrations_count=1, invariants=["ACT"])
    assert g1.invariant_hash == g2.invariant_hash, "goal_id must not influence structural hash"


# ── CapabilityRecord schema ───────────────────────────────────────────────────

def test_capability_record_defaults():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="abcd1234abcd1234", invariants=["AUTHENTICATE"])
    assert r.promotion_tier == "CANDIDATE"
    assert r.transfer_envs == []
    assert r.known_boundaries == []
    assert r.source == "compilation"
    assert r.human_name is None
    assert r.contract_verified_ratio is None


def test_capability_record_record_transfer_upgrades_tier():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["AUTHENTICATE"])
    r.record_transfer("github")
    assert r.promotion_tier == "CANDIDATE"   # still CANDIDATE after 1 env
    r.record_transfer("saucedemo")
    assert r.promotion_tier == "STRONG"       # ≥2 envs → STRONG


def test_capability_record_record_transfer_deduplicates():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["ACT"])
    r.record_transfer("github")
    r.record_transfer("github")
    assert r.transfer_envs == ["github"]


def test_capability_record_validation():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["AUTHENTICATE"])
    r.record_validation(0.90)
    assert r.promotion_tier == "VALIDATED"
    assert r.contract_verified_ratio == 0.90


def test_capability_record_validation_below_threshold_no_upgrade():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(invariant_hash="x" * 16, invariants=["AUTHENTICATE"])
    r.record_validation(0.50)
    assert r.promotion_tier == "CANDIDATE"
    assert r.contract_verified_ratio == 0.50


def test_capability_record_json_round_trip():
    from browsermind_core.learning.capability_record import CapabilityRecord
    r = CapabilityRecord(
        invariant_hash="abcd1234abcd1234",
        invariants=["AUTHENTICATE", "LOCATE"],
        promotion_tier="STRONG",
        transfer_envs=["github", "saucedemo"],
        source_templates=["template-uuid-1"],
        human_name="auth_flow",
    )
    d = json.loads(r.to_json())
    r2 = CapabilityRecord.from_dict(d)
    assert r2.invariant_hash == r.invariant_hash
    assert r2.invariants == r.invariants
    assert r2.promotion_tier == r.promotion_tier
    assert r2.transfer_envs == r.transfer_envs
    assert r2.human_name == r.human_name


def test_capability_record_from_dict_old_record_missing_fields():
    from browsermind_core.learning.capability_record import CapabilityRecord
    old = {
        "invariant_hash": "abcd1234abcd1234",
        "invariants": ["AUTHENTICATE"],
        "first_seen": "2026-06-01T00:00:00+00:00",
        "last_seen": "2026-06-01T00:00:00+00:00",
    }
    r = CapabilityRecord.from_dict(old)
    assert r.promotion_tier == "CANDIDATE"
    assert r.transfer_envs == []


def test_capability_record_from_dict_unknown_keys_dropped():
    from browsermind_core.learning.capability_record import CapabilityRecord
    future = {
        "invariant_hash": "abcd1234abcd1234",
        "invariants": ["AUTHENTICATE"],
        "first_seen": "2026-06-01T00:00:00+00:00",
        "last_seen": "2026-06-01T00:00:00+00:00",
        "future_field_v100": "should be dropped",
    }
    r = CapabilityRecord.from_dict(future)
    assert r.invariant_hash == "abcd1234abcd1234"
