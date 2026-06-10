"""AutoPilot — Phase B1 of the Autonomous Self-Learning roadmap.

Drives the three R6 cycle taps (mine, sweep, monitor) automatically at
fixed step intervals so the loop runs without operator intervention.

This module orchestrates ONLY. It does NOT auto-approve or auto-commit.
Human approval remains required for any structural mutation:

    mine     → produces RecoveryCandidate(status=pending)        [auto]
    sweep    → flips pending → shadow → ready                    [auto]
    monitor  → quarantines harmful committed mined strategies    [auto]
    approve  → commits ready → committed                         [HUMAN ONLY]
    rollback → restores from previous_state                      [HUMAN ONLY]

Best-effort throughout: cycle errors NEVER raise into replay.
Defaults are conservative: AUTOPILOT_INTERVAL=200 step rows means a
typical 10-50 step replay does not trigger a cycle by itself, but a
multi-replay session naturally does.
"""
from __future__ import annotations

import json
from typing import Any, Dict


# Default cadence — a cycle runs once every N step OutcomeRecords land.
# Conservative on purpose: mining rescans the whole OutcomeLedger and we'd
# rather under-mine than thrash on tight replays.
AUTOPILOT_INTERVAL = 200


class AutoPilot:
    """Orchestrates mine/sweep/monitor at fixed step intervals.

    Owned by KernelSession. Notified after each replay's step OutcomeRecords
    land via notify_steps_recorded(n). When the running counter crosses
    self.interval, runs one cycle and resets.

    The cycle is best-effort end-to-end. Each phase is wrapped in its own
    try/except so one phase's failure doesn't block the next, and the whole
    thing is wrapped again so even a catastrophic auto-pilot bug cannot
    crash replay.
    """

    def __init__(self, kernel_session, *, interval: int = AUTOPILOT_INTERVAL):
        self.ks = kernel_session
        self.interval = max(1, int(interval))
        self._step_count = 0
        self._cycles_run = 0
        self._last_results: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_steps_recorded(self, n: int) -> None:
        """Called from ReplayEngine after each replay's step rows land.
        Best-effort: never raises into replay."""
        if n <= 0:
            return
        try:
            self._step_count += int(n)
            if self._step_count >= self.interval:
                self._step_count = 0
                self._run_cycle()
        except Exception as e:
            print(f"  [AutoPilot] notify failed: {e}")

    @property
    def cycles_run(self) -> int:
        return self._cycles_run

    @property
    def last_results(self) -> Dict[str, Any]:
        return dict(self._last_results)

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    def _run_cycle(self) -> None:
        """One pass of mine → sweep → monitor. Each phase isolated."""
        self._cycles_run += 1
        self._last_results = {
            "mine":    self._safe_mine(),
            "sweep":   self._safe_sweep(),
            "monitor": self._safe_monitor(),
        }

    def _safe_mine(self) -> Dict[str, Any]:
        """Mine new RecoveryCandidates from OutcomeLedger.

        Dedups against existing candidates by (predicate, primitive) signature
        and rejects unknown primitives. Saves new candidates as status=pending.
        Never auto-commits.
        """
        try:
            from browsermind_core.runtime.primitive_library import get_primitive
            from browsermind_core.training.failure_pattern_miner import (
                mine_patterns, to_recovery_candidate,
            )

            records = list(self.ks.outcome_ledger.records)
            if not records:
                return {"saved": 0, "patterns": 0, "skipped": 0}

            patterns = mine_patterns(records)
            existing = self.ks.recovery_candidate_registry.list()
            existing_sigs = {
                (json.dumps(c.predicate, sort_keys=True), c.primitive)
                for c in existing
            }

            saved = 0
            skipped = 0
            for p in patterns:
                sig = (
                    json.dumps(p.predicate, sort_keys=True),
                    p.suggested_primitive,
                )
                if sig in existing_sigs:
                    skipped += 1
                    continue
                if get_primitive(p.suggested_primitive) is None:
                    skipped += 1
                    continue
                cand = to_recovery_candidate(p)
                self.ks.recovery_candidate_registry.save(cand)
                existing_sigs.add(sig)
                saved += 1
            return {"saved": saved, "patterns": len(patterns), "skipped": skipped}
        except Exception as e:
            return {"error": str(e)[:200]}

    def _safe_sweep(self) -> Dict[str, Any]:
        """Run the promotion gate over pending/shadow candidates.
        Flips status to 'ready' on positive lift. Then runs the auto-commit
        gate which commits only candidates whose shadow evidence is 3x
        stronger than the human-ready threshold AND whose primitive is
        whitelisted. Anything ambiguous remains at 'ready' for human review."""
        try:
            from browsermind_core.runtime.recovery_promotion_gate import refresh_registry
            from browsermind_core.runtime.shadow_validator import ShadowValidator

            validator = ShadowValidator(self.ks.store_dir)
            results = refresh_registry(
                self.ks.recovery_candidate_registry,
                validator=validator,
            )
            promoted = sum(1 for _, allow, _ in results if allow)

            # Phase B2: bounded auto-commit for routine candidates.
            auto_commits = 0
            try:
                from browsermind_core.runtime.auto_commit_gate import (
                    commit_eligible_candidates,
                )
                ac_results = commit_eligible_candidates(
                    self.ks.recovery_candidate_registry,
                    self.ks.recovery_registry,
                    validator=validator,
                    behavior_audit=getattr(self.ks, "behavior_audit", None),
                )
                auto_commits = sum(1 for _, ok, _ in ac_results if ok)
            except Exception as e:
                # Auto-commit failure must not block the sweep result.
                print(f"  [AutoPilot] auto_commit_gate failed: {e}")

            return {
                "evaluated": len(results),
                "promoted_to_ready": promoted,
                "auto_committed": auto_commits,
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    def _safe_monitor(self) -> Dict[str, Any]:
        """Post-commit measurement: quarantine mined strategies whose
        real-traffic lift has gone negative. Never modifies committed
        templates; only flips status + hides from ladder."""
        try:
            from browsermind_core.runtime.recovery_post_commit_monitor import sweep

            records = list(self.ks.outcome_ledger.records)
            results = sweep(
                records,
                self.ks.recovery_candidate_registry,
                self.ks.recovery_registry,
            )
            quarantined = sum(1 for _, _, flagged in results if flagged)
            return {"evaluated": len(results), "quarantined": quarantined}
        except Exception as e:
            return {"error": str(e)[:200]}
