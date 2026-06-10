"""AutoPilot — Phase B1 wiring + behavior tests.

Validates:
  * notify_steps_recorded counter / threshold semantics
  * Cycle composition (mine + sweep + monitor present in last_results)
  * Best-effort failure swallowing — replay must never see an exception
  * Safety: AutoPilot NEVER auto-commits; ladder retains only seeded builtins
  * Source-level guards confirming the wiring edits actually landed
  * KernelSession constructs AutoPilot at the end of __init__

All tests use OutcomeLedger.record() directly with synthetic OutcomeRecord
rows — no Playwright, no AuthSession, no browser process.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.runtime.auto_pilot import AutoPilot


# ---------------------------------------------------------------------------
# Inline fixtures — copied from test_r6_cli_taps.py per the task constraints.
# ---------------------------------------------------------------------------


def _step(success, ts, *, recovered_by="", failure_class="TARGET_CHANGED",
          name="Submit", env="saucedemo", action="click"):
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=uuid4(),
        environment_family="testfam",
        environment_instance=env,
        outcome_type="step_attempt",
        success=success,
        evidence="x",
        timestamp=ts,
        metrics={
            "action": action, "role": "button", "name": name,
            "recovered_by": recovered_by,
            "failure_class": failure_class,
            "actual_outcome": "SUCCESS" if success else "FAILED",
        },
    )


def _seed_unrecovered_failures(ks: KernelSession, n: int):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(n):
        ks.outcome_ledger.record(
            _step(False, base + timedelta(seconds=i), recovered_by="")
        )


def _seed_recovered(ks: KernelSession, n: int, *, recovered_by="container_proximity"):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(n):
        ks.outcome_ledger.record(
            _step(True, base + timedelta(seconds=1000 + i),
                  recovered_by=recovered_by)
        )


# ---------------------------------------------------------------------------
# a) below-threshold no-op
# ---------------------------------------------------------------------------


def test_autopilot_no_op_below_threshold(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    ap = AutoPilot(ks, interval=10)
    ap.notify_steps_recorded(5)
    assert ap.cycles_run == 0
    assert ap._step_count == 5


# ---------------------------------------------------------------------------
# b) fires cycle when threshold crossed
# ---------------------------------------------------------------------------


def test_autopilot_fires_cycle_when_threshold_crossed(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    ap = AutoPilot(ks, interval=10)
    ap.notify_steps_recorded(15)
    assert ap.cycles_run == 1
    assert ap._step_count == 0
    last = ap.last_results
    assert set(last.keys()) == {"mine", "sweep", "monitor"}


# ---------------------------------------------------------------------------
# c) counter resets after fire
# ---------------------------------------------------------------------------


def test_autopilot_resets_counter_after_cycle(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    ap = AutoPilot(ks, interval=10)
    ap.notify_steps_recorded(15)        # → fire 1, counter -> 0
    assert ap.cycles_run == 1
    ap.notify_steps_recorded(5)         # → no fire (counter == 5)
    assert ap.cycles_run == 1
    ap.notify_steps_recorded(6)         # → fire 2 (counter == 11 >= 10)
    assert ap.cycles_run == 2


# ---------------------------------------------------------------------------
# d) mine phase persists candidates as 'pending'
# ---------------------------------------------------------------------------


def test_autopilot_mine_phase_persists_candidates(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    _seed_unrecovered_failures(ks, 25)
    _seed_recovered(ks, 5)
    ap = AutoPilot(ks, interval=10)
    ap.notify_steps_recorded(10)
    rows = ks.recovery_candidate_registry.list()
    assert len(rows) >= 1
    assert all(c.status == "pending" for c in rows)
    # And the mine sub-result reports the save.
    assert ap.last_results["mine"].get("saved", 0) >= 1


# ---------------------------------------------------------------------------
# e) swallow mine failure — sweep + monitor still run
# ---------------------------------------------------------------------------


def test_autopilot_swallows_mine_failure(tmp_path, monkeypatch):
    ks = KernelSession(store_dir=str(tmp_path))
    # Seed a few rows so _safe_mine gets past the empty-records short-circuit
    # and actually invokes mine_patterns (the patched target).
    _seed_unrecovered_failures(ks, 5)
    ap = AutoPilot(ks, interval=10)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    # AutoPilot imports mine_patterns inside _safe_mine, so monkeypatch
    # the module-level symbol.
    monkeypatch.setattr(
        "browsermind_core.training.failure_pattern_miner.mine_patterns",
        _boom,
    )

    # Must not raise.
    ap.notify_steps_recorded(10)

    last = ap.last_results
    assert "error" in last["mine"]
    assert "boom" in last["mine"]["error"]
    # Sweep + monitor still produced a result (no error key, or non-error key).
    assert "sweep" in last and "monitor" in last
    # Their results are dicts — confirm they ran past the import line.
    assert isinstance(last["sweep"], dict)
    assert isinstance(last["monitor"], dict)


# ---------------------------------------------------------------------------
# f) swallow notify failure entirely — outer try/except in notify
# ---------------------------------------------------------------------------


def test_autopilot_swallows_notify_failure(tmp_path, monkeypatch):
    ks = KernelSession(store_dir=str(tmp_path))
    ap = AutoPilot(ks, interval=10)

    def _crash(self):
        raise RuntimeError("crash")

    monkeypatch.setattr(AutoPilot, "_run_cycle", _crash)
    # Must not raise.
    ap.notify_steps_recorded(10)
    # _run_cycle blew up before incrementing _cycles_run.
    assert ap.cycles_run == 0


# ---------------------------------------------------------------------------
# g) no-op on empty ledger — mine reports zero patterns/saved
# ---------------------------------------------------------------------------


def test_autopilot_no_op_when_ledger_empty(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    ap = AutoPilot(ks, interval=10)
    ap.notify_steps_recorded(10)
    mine = ap.last_results["mine"]
    # No records → either explicit zero counters or no "error".
    assert "error" not in mine
    assert mine.get("saved", 0) == 0
    assert mine.get("patterns", 0) == 0


# ---------------------------------------------------------------------------
# h) safety: AutoPilot must never auto-commit
# ---------------------------------------------------------------------------


def test_autopilot_does_not_auto_commit(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    # Seed strong evidence — exactly the shape that would *eventually* let a
    # candidate become "ready" after sweep, if shadow data existed. Note we
    # deliberately do NOT seed shadow validation rows; sweep should not
    # promote, and even if it did, AutoPilot must not commit.
    _seed_unrecovered_failures(ks, 50)
    _seed_recovered(ks, 10)
    ap = AutoPilot(ks, interval=10)

    # Run many cycles.
    for _ in range(10):
        ap.notify_steps_recorded(10)

    # No candidate ever reaches "committed" without a human approve verb.
    for c in ks.recovery_candidate_registry.list():
        assert c.status != "committed", (
            f"AutoPilot auto-committed candidate {c.id} (status={c.status})"
        )

    # The ladder should contain ONLY the seeded R1-R5b builtins —
    # no "mined" rows can appear, because committing is the only path
    # that adds a mined RecoveryStrategy and that requires human approval.
    ladder = ks.recovery_registry.ladder()
    for s in ladder:
        assert s.source == "builtin", (
            f"AutoPilot appended a non-builtin ladder row: {s.name} ({s.source})"
        )


# ---------------------------------------------------------------------------
# i) wiring: KernelSession exposes .auto_pilot
# ---------------------------------------------------------------------------


def test_autopilot_wired_into_kernel_session(tmp_path):
    ks = KernelSession(store_dir=str(tmp_path))
    assert hasattr(ks, "auto_pilot")
    assert isinstance(ks.auto_pilot, AutoPilot)


# ---------------------------------------------------------------------------
# j) source-level guard: replay_engine fans notify into auto_pilot
# ---------------------------------------------------------------------------


def test_autopilot_called_from_replay_engine():
    src = (
        Path(__file__).resolve().parents[1]
        / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "auto_pilot.notify_steps_recorded" in src, (
        "ReplayEngine must call self.auto_pilot.notify_steps_recorded(...) "
        "alongside the lesson_reader notify in _record_step_outcomes."
    )


# ---------------------------------------------------------------------------
# k) source-level guard: cli passes ks.auto_pilot into ReplayEngine
# ---------------------------------------------------------------------------


def test_autopilot_wired_in_cli():
    src = (
        Path(__file__).resolve().parents[1]
        / "console" / "cli.py"
    ).read_text(encoding="utf-8")
    assert 'auto_pilot=getattr(s, "auto_pilot", None)' in src, (
        "CLI replay command must pass auto_pilot=getattr(s, 'auto_pilot', None) "
        "to ReplayEngine()."
    )
