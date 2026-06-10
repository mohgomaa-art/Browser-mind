"""Tests for MemoryStore capability persistence.

Verifies:
  - update_capability() creates a new file for a new hash
  - update_capability() merges transfer_envs on second write
  - update_capability() merges strategy_counts incrementally
  - update_capability() promotes tier when record reports higher tier
  - get_capability_by_hash() returns None for unknown hash
  - get_capability_by_hash() returns stored record
  - load_capabilities() returns all stored records
  - update_procedural() now merges known_boundaries via merge_boundaries
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def _make_store(tmp_dir):
    from browsermind_core.memory.memory_store import MemoryStore
    return MemoryStore(root=Path(tmp_dir), persona_id="test")


# ── CapabilityRecord persistence ──────────────────────────────────────────────

def test_update_capability_creates_file():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            transfer_envs=["github"],
        )
        store.update_capability(r)
        path = Path(tmp) / "capabilities" / "abcd1234abcd1234.json"
        assert path.exists()


def test_get_capability_by_hash_returns_none_for_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        result = store.get_capability_by_hash("0000000000000000")
        assert result is None


def test_get_capability_by_hash_returns_stored():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
        )
        store.update_capability(r)
        loaded = store.get_capability_by_hash("abcd1234abcd1234")
        assert loaded is not None
        assert loaded.invariant_hash == "abcd1234abcd1234"
        assert loaded.invariants == ["AUTHENTICATE"]


def test_update_capability_merges_transfer_envs():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r1 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            transfer_envs=["github"],
        )
        store.update_capability(r1)
        r2 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            transfer_envs=["saucedemo"],
        )
        store.update_capability(r2)
        loaded = store.get_capability_by_hash("abcd1234abcd1234")
        assert "github" in loaded.transfer_envs
        assert "saucedemo" in loaded.transfer_envs


def test_update_capability_merges_strategy_counts():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r1 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            strategy_counts={"capability_intent": {"success": 3, "failure": 0}},
        )
        store.update_capability(r1)
        r2 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            strategy_counts={"capability_intent": {"success": 2, "failure": 1}},
        )
        store.update_capability(r2)
        loaded = store.get_capability_by_hash("abcd1234abcd1234")
        counts = loaded.strategy_counts["capability_intent"]
        assert counts["success"] == 5
        assert counts["failure"] == 1


def test_update_capability_takes_higher_tier():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r1 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            promotion_tier="CANDIDATE",
        )
        store.update_capability(r1)
        r2 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            promotion_tier="VALIDATED",
        )
        store.update_capability(r2)
        loaded = store.get_capability_by_hash("abcd1234abcd1234")
        assert loaded.promotion_tier == "VALIDATED"


def test_update_capability_does_not_downgrade_tier():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r1 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            promotion_tier="VALIDATED",
        )
        store.update_capability(r1)
        r2 = CapabilityRecord(
            invariant_hash="abcd1234abcd1234",
            invariants=["AUTHENTICATE"],
            promotion_tier="CANDIDATE",
        )
        store.update_capability(r2)
        loaded = store.get_capability_by_hash("abcd1234abcd1234")
        assert loaded.promotion_tier == "VALIDATED"


def test_load_capabilities_returns_all():
    from browsermind_core.learning.capability_record import CapabilityRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        for h in ["aaaa111122223333", "bbbb444455556666"]:
            store.update_capability(
                CapabilityRecord(invariant_hash=h, invariants=["ACT"])
            )
        result = store.load_capabilities()
        assert len(result) == 2
        assert "aaaa111122223333" in result
        assert "bbbb444455556666" in result


# ── update_procedural merges known_boundaries ─────────────────────────────────

def test_update_procedural_merges_boundaries():
    from browsermind_core.memory.procedural import ProceduralRecord
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        r1 = ProceduralRecord(
            environment_key="github",
            intent_family="AUTH",
            capability_hint="login_btn",
            step_action="click",
            known_boundaries=[{
                "capability_hint": "login_btn",
                "failure_mode": "TARGET_CHANGED",
                "failure_reason": "TARGET_CHANGED",
                "environment_pattern": "github",
                "frequency": 2,
                "evidence_count": 1,
            }],
        )
        store.update_procedural(r1)
        r2 = ProceduralRecord(
            environment_key="github",
            intent_family="AUTH",
            capability_hint="login_btn",
            step_action="click",
            known_boundaries=[{
                "capability_hint": "login_btn",
                "failure_mode": "TARGET_CHANGED",
                "failure_reason": "TARGET_CHANGED",
                "environment_pattern": "github",
                "frequency": 3,
                "evidence_count": 2,
            }],
        )
        store.update_procedural(r2)
        loaded = store.get_procedural("github", "AUTH", "login_btn", "click")
        assert loaded is not None
        assert len(loaded.known_boundaries) == 1
        assert loaded.known_boundaries[0]["frequency"] == 5
        assert loaded.known_boundaries[0]["evidence_count"] == 3
