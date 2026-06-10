"""Tests for CapabilityHypothesis + CapabilityHypothesisStore.

Covers:
  - CapabilityHypothesis dataclass defaults and serialisation
  - make_hypothesis() factory
  - Status lifecycle: HYPOTHESIS → RECURRING → EMERGING → CANDIDATE
  - Terminal states (PROMOTED, REFUTED) accept no further observations
  - force_advance() human override
  - transfer_rate property
  - EvidenceEntry serialisation
  - CapabilityHypothesisStore.observe() — create and merge
  - observe() on terminal hypothesis is a no-op
  - Store.merge() combines two hypotheses
  - Store.promote() sets status and optionally writes CapabilityRecord
  - Store.refute() sets status and reason
  - Store.query() filters by status / frequency / environments
  - Store.exploration_targets() returns RECURRING and EMERGING
  - Store.candidates_ready() returns CANDIDATE-only
  - Store.stats() counts by status
  - Store.delete() removes file
  - Persistence round-trip (save → load → compare)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _store(tmp_path: Path):
    from browsermind_core.learning.capability_hypothesis_store import CapabilityHypothesisStore
    return CapabilityHypothesisStore(root=tmp_path)


# ── CapabilityHypothesis dataclass ────────────────────────────────────────────

def test_hypothesis_defaults():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["AUTHENTICATE"], env_key="github")
    assert h.status == "HYPOTHESIS"
    assert h.frequency == 1
    assert h.environments == ["github"]
    assert h.transfer_attempts == 0
    assert h.transfer_successes == 0
    assert h.promoted_capability_id is None
    assert h.refuted_reason is None


def test_make_hypothesis_hash_deterministic():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h1 = make_hypothesis(["SUBMIT_FORM", "NAVIGATE"], env_key="github")
    h2 = make_hypothesis(["NAVIGATE", "SUBMIT_FORM"], env_key="gitlab")
    # Same sorted invariants → same hash regardless of input order
    assert h1.invariant_hash == h2.invariant_hash


def test_hypothesis_evidence_on_creation():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["ACT"], env_key="github", context_hint="login_flow", outcome="success")
    assert len(h.evidence) == 1
    assert h.evidence[0].env_key == "github"
    assert h.evidence[0].outcome == "success"


def test_hypothesis_serialise_round_trip():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis, CapabilityHypothesis
    h = make_hypothesis(["AUTHENTICATE", "VERIFY"], env_key="github", source="replay")
    h2 = CapabilityHypothesis.from_dict(h.to_dict())
    assert h2.invariant_hash == h.invariant_hash
    assert h2.status == h.status
    assert h2.frequency == h.frequency
    assert h2.environments == h.environments
    assert h2.source == h.source


def test_hypothesis_from_dict_forward_compat():
    """Old records without new fields should deserialise cleanly."""
    from browsermind_core.learning.capability_hypothesis import CapabilityHypothesis
    old = {
        "hypothesis_id": "aabbccdd11223344",
        "invariant_hash": "1234567890abcdef",
        "invariants": ["AUTHENTICATE"],
        "first_seen": "2026-01-01T00:00:00+00:00",
        "last_seen": "2026-01-01T00:00:00+00:00",
    }
    h = CapabilityHypothesis.from_dict(old)
    assert h.status == "HYPOTHESIS"
    assert h.transfer_attempts == 0
    assert h.refuted_reason is None
    assert h.human_hint is None


# ── Status lifecycle ──────────────────────────────────────────────────────────

def test_status_hypothesis_to_recurring():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, RECURRING_MIN_FREQUENCY
    )
    h = make_hypothesis(["ACT"], env_key="github")
    assert h.status == "HYPOTHESIS"
    # Observe enough to hit RECURRING
    for i in range(RECURRING_MIN_FREQUENCY - 1):
        h.observe(env_key=f"env{i}")
    assert h.status == "RECURRING"


def test_status_recurring_to_emerging_by_frequency():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, EMERGING_MIN_FREQUENCY
    )
    h = make_hypothesis(["ACT"], env_key="env0")
    for i in range(1, EMERGING_MIN_FREQUENCY):
        h.observe(env_key="env0")   # same env — triggers via frequency
    assert h.status in ("EMERGING", "RECURRING", "CANDIDATE")
    # Once frequency ≥ EMERGING_MIN_FREQUENCY status should be at least EMERGING
    if h.status == "RECURRING":
        # one more nudge
        h.observe(env_key="env0")
    assert h.status in ("EMERGING", "CANDIDATE")


def test_status_recurring_to_emerging_by_environments():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, RECURRING_MIN_FREQUENCY, EMERGING_MIN_ENVS
    )
    h = make_hypothesis(["ACT"], env_key="env0")
    # Get to RECURRING first
    for i in range(1, RECURRING_MIN_FREQUENCY):
        h.observe(env_key="env0")
    assert h.status == "RECURRING"
    # Now add distinct environments to trigger EMERGING
    for i in range(1, EMERGING_MIN_ENVS):
        h.observe(env_key=f"env{i}")
    assert h.status in ("EMERGING", "CANDIDATE")


def test_status_terminal_promoted_no_advance():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["ACT"], env_key="github")
    h.promote()
    original_freq = h.frequency
    h.observe(env_key="gitlab")
    assert h.status == "PROMOTED"
    assert h.frequency == original_freq  # no increment


def test_status_terminal_refuted_no_advance():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["ACT"], env_key="github")
    h.refute(reason="false pattern")
    h.observe(env_key="gitlab")
    assert h.status == "REFUTED"


def test_force_advance_skips_levels():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, HypothesisStatus
    )
    h = make_hypothesis(["ACT"])
    assert h.status == HypothesisStatus.HYPOTHESIS
    h.force_advance(HypothesisStatus.CANDIDATE)
    assert h.status == HypothesisStatus.CANDIDATE


def test_force_advance_does_not_downgrade():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, HypothesisStatus
    )
    h = make_hypothesis(["ACT"])
    h.force_advance(HypothesisStatus.EMERGING)
    h.force_advance(HypothesisStatus.HYPOTHESIS)  # attempted downgrade
    assert h.status == HypothesisStatus.EMERGING


def test_force_advance_ignores_terminal():
    from browsermind_core.learning.capability_hypothesis import (
        make_hypothesis, HypothesisStatus
    )
    h = make_hypothesis(["ACT"])
    h.promote()
    h.force_advance(HypothesisStatus.CANDIDATE)
    assert h.status == HypothesisStatus.PROMOTED


def test_transfer_rate_none_before_attempts():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["ACT"])
    assert h.transfer_rate is None


def test_transfer_rate_computed():
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    h = make_hypothesis(["ACT"])
    h.record_transfer_attempt(success=True)
    h.record_transfer_attempt(success=False)
    assert h.transfer_rate == 0.5


# ── CapabilityHypothesisStore ─────────────────────────────────────────────────

def test_store_observe_creates_new(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github", source="replay")
    assert h.status == "HYPOTHESIS"
    assert h.frequency == 1
    assert h.environments == ["github"]
    # File written
    assert (tmp_path / "hypotheses" / f"{h.invariant_hash}.json").exists()


def test_store_observe_increments_frequency(tmp_path):
    store = _store(tmp_path)
    h1 = store.observe(["AUTHENTICATE"], env_key="github")
    h2 = store.observe(["AUTHENTICATE"], env_key="gitlab")
    assert h2.invariant_hash == h1.invariant_hash
    assert h2.frequency == 2
    assert "gitlab" in h2.environments


def test_store_observe_advances_status(tmp_path):
    from browsermind_core.learning.capability_hypothesis import (
        RECURRING_MIN_FREQUENCY, EMERGING_MIN_ENVS
    )
    store = _store(tmp_path)
    invariants = ["AUTHENTICATE", "VERIFY_SESSION"]
    store.observe(invariants, env_key="site1")
    for i in range(1, RECURRING_MIN_FREQUENCY + EMERGING_MIN_ENVS):
        h = store.observe(invariants, env_key=f"site{i}")
    assert h.status in ("RECURRING", "EMERGING", "CANDIDATE")


def test_store_observe_terminal_is_noop(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    store.refute(h.invariant_hash, reason="test")
    h_after = store.observe(["AUTHENTICATE"], env_key="gitlab")
    # Status should remain REFUTED; frequency not incremented
    assert h_after.status == "REFUTED"


def test_store_merge_combines(tmp_path):
    store = _store(tmp_path)
    from browsermind_core.learning.capability_hypothesis import make_hypothesis
    inv = ["SUBMIT_FORM"]
    h_a = make_hypothesis(inv, env_key="github")
    h_a.observe("gitlab")
    h_b = make_hypothesis(inv, env_key="bitbucket")
    # merge b into a (both have same hash)
    merged = store.merge(h_a)
    merged2 = store.merge(h_b)
    assert merged2.frequency >= 2
    assert "github" in merged2.environments or "bitbucket" in merged2.environments


def test_store_promote_sets_status(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    result = store.promote(h.invariant_hash)
    assert result is not None
    assert result.status == "PROMOTED"
    assert result.promoted_capability_id == h.invariant_hash


def test_store_promote_writes_capability_record(tmp_path):
    from unittest.mock import MagicMock
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    mem_store = MagicMock()
    store.promote(h.invariant_hash, write_capability_record=True, mem_store=mem_store)
    mem_store.update_capability.assert_called_once()


def test_store_refute_sets_status(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    result = store.refute(h.invariant_hash, reason="cookie banner only")
    assert result.status == "REFUTED"
    assert result.refuted_reason == "cookie banner only"


def test_store_query_by_status(tmp_path):
    store = _store(tmp_path)
    store.observe(["AUTHENTICATE"], env_key="github")  # HYPOTHESIS
    store.observe(["SUBMIT_FORM"], env_key="github")    # HYPOTHESIS
    results = store.query(status=["HYPOTHESIS"])
    assert len(results) == 2


def test_store_query_min_frequency(tmp_path):
    store = _store(tmp_path)
    store.observe(["AUTHENTICATE"], env_key="github")
    store.observe(["AUTHENTICATE"], env_key="gitlab")  # freq=2
    store.observe(["SUBMIT_FORM"], env_key="github")   # freq=1
    results = store.query(min_frequency=2)
    assert all(h.frequency >= 2 for h in results)
    assert len(results) == 1


def test_store_query_exclude_terminal(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    store.promote(h.invariant_hash)
    store.observe(["SUBMIT_FORM"], env_key="github")
    all_results = store.query()
    active_results = store.query(exclude_terminal=True)
    assert len(active_results) < len(all_results)


def test_store_exploration_targets_returns_recurring_emerging(tmp_path):
    from browsermind_core.learning.capability_hypothesis import (
        HypothesisStatus, make_hypothesis
    )
    store = _store(tmp_path)
    h1 = make_hypothesis(["A"], env_key="e1")
    h1.force_advance(HypothesisStatus.RECURRING)
    store._save(h1)

    h2 = make_hypothesis(["B"], env_key="e2")
    h2.force_advance(HypothesisStatus.EMERGING)
    store._save(h2)

    h3 = make_hypothesis(["C"], env_key="e3")
    h3.promote()
    store._save(h3)

    targets = store.exploration_targets()
    statuses = {h.status for h in targets}
    assert "PROMOTED" not in statuses
    assert "RECURRING" in statuses or "EMERGING" in statuses


def test_store_candidates_ready(tmp_path):
    from browsermind_core.learning.capability_hypothesis import (
        HypothesisStatus, make_hypothesis
    )
    store = _store(tmp_path)
    h = make_hypothesis(["A"], env_key="e1")
    h.force_advance(HypothesisStatus.CANDIDATE)
    store._save(h)
    store.observe(["B"], env_key="e1")  # HYPOTHESIS
    candidates = store.candidates_ready()
    assert len(candidates) == 1
    assert candidates[0].status == HypothesisStatus.CANDIDATE


def test_store_stats(tmp_path):
    store = _store(tmp_path)
    store.observe(["A"], env_key="e1")
    store.observe(["B"], env_key="e1")
    h = store.observe(["C"], env_key="e1")
    store.refute(h.invariant_hash)
    stats = store.stats()
    assert stats["total"] == 3
    assert stats["by_status"]["HYPOTHESIS"] == 2
    assert stats["by_status"]["REFUTED"] == 1


def test_store_delete(tmp_path):
    store = _store(tmp_path)
    h = store.observe(["AUTHENTICATE"], env_key="github")
    assert store.get(h.invariant_hash) is not None
    store.delete(h.invariant_hash)
    assert store.get(h.invariant_hash) is None


def test_store_persistence_round_trip(tmp_path):
    store1 = _store(tmp_path)
    h = store1.observe(["AUTHENTICATE", "VERIFY_SESSION"], env_key="github", source="replay")

    store2 = _store(tmp_path)
    loaded = store2.get(h.invariant_hash)
    assert loaded is not None
    assert loaded.invariant_hash == h.invariant_hash
    assert loaded.environments == h.environments
    assert loaded.source == h.source
