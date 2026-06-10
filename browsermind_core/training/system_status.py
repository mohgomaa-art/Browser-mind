"""SystemStatus — one-glance honesty surface for BrowserMind.

Aggregates the actual state of the learning loop from durable data:
  - OutcomeLedger (was anything ever recorded? how recently?)
  - behavior_audit.jsonl (have any prior-driven decisions been logged?)
  - RecoveryCandidateRegistry (any candidates mined? auto-committed? quarantined?)
  - RecoveryRegistry (does the live ladder contain mined rows?)
  - shadow_results.jsonl (has the shadow loop ever fired?)

The `is_learning_actualized` field is the bottom-line answer to:
  "Has BrowserMind ever closed a real-traffic learning loop?"

True only when:
  step_records >= 1
  AND (auto_committed_observed >= 1 OR human_committed_mined_observed >= 1)
  AND last_real_replay_at is not None

Otherwise the architecture is plumbed but the pipe is dry.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
    except Exception:
        return 0


def _audit_count_by_source(path: Path, prior_source: str) -> int:
    if not path.exists():
        return 0
    n = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("prior_source") == prior_source:
                    n += 1
    except Exception:
        return 0
    return n


def compute_status(kernel_session) -> Dict[str, Any]:
    """Pure aggregation over an existing KernelSession's durable state.

    Returns a dict suitable for JSON dump or CLI tabulation.
    """
    ks = kernel_session
    store_dir = Path(ks.store_dir)

    # --- OutcomeLedger evidence -------------------------------------------
    records = list(getattr(ks.outcome_ledger, "records", []))
    step_records = [r for r in records
                    if r.scope == "step" and r.outcome_type == "step_attempt"]
    run_records = [r for r in records
                   if r.scope == "workflow_instance"
                   and r.outcome_type == "replay_run"]
    last_replay_ts: Optional[datetime] = None
    for r in run_records:
        if last_replay_ts is None or r.timestamp > last_replay_ts:
            last_replay_ts = r.timestamp

    # --- Audit log evidence -----------------------------------------------
    audit_path = store_dir / "audit" / "behavior_audit.jsonl"
    audit_total = _safe_count_jsonl(audit_path)
    audit_auto_commits = _audit_count_by_source(audit_path, "auto_commit")
    audit_lesson_priors = _audit_count_by_source(audit_path, "lessons.jsonl")
    audit_memory_priors = _audit_count_by_source(audit_path, "procedural_memory")

    # --- Shadow trial evidence --------------------------------------------
    shadow_path = store_dir / "shadow_results.jsonl"
    shadow_trials = _safe_count_jsonl(shadow_path)

    # --- Candidate registry evidence --------------------------------------
    cand_by_status: Dict[str, int] = {}
    committed_mined: List[str] = []
    quarantined_mined: List[str] = []
    try:
        for c in ks.recovery_candidate_registry.list():
            cand_by_status[c.status] = cand_by_status.get(c.status, 0) + 1
            if c.status == "committed":
                committed_mined.append(c.name)
            if c.status == "quarantined":
                quarantined_mined.append(c.name)
    except Exception:
        pass

    # --- Live ladder content ----------------------------------------------
    builtin_strategies = 0
    mined_strategies = 0
    quarantined_strategies = 0
    try:
        for s in ks.recovery_registry.ladder(include_quarantined=True):
            if s.source == "builtin":
                builtin_strategies += 1
            elif s.source == "mined":
                if s.quarantined:
                    quarantined_strategies += 1
                else:
                    mined_strategies += 1
    except Exception:
        pass

    # --- Bottom-line ------------------------------------------------------
    auto_committed_observed = audit_auto_commits
    human_committed_mined_observed = max(
        0, len(committed_mined) - auto_committed_observed
    )
    is_learning_actualized = (
        len(step_records) >= 1
        and (auto_committed_observed >= 1 or human_committed_mined_observed >= 1)
        and last_replay_ts is not None
    )

    return {
        "schema_version": "browsermind.system_status.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "store_dir": str(store_dir),
        "evidence": {
            "step_records": len(step_records),
            "run_records": len(run_records),
            "last_real_replay_at":
                last_replay_ts.isoformat() if last_replay_ts else None,
            "shadow_trials": shadow_trials,
            "audit_rows_total": audit_total,
            "audit_lesson_prior_decisions": audit_lesson_priors,
            "audit_memory_prior_decisions": audit_memory_priors,
            "audit_auto_commits": audit_auto_commits,
        },
        "candidates": {
            "by_status": cand_by_status,
            "committed_mined_strategies": committed_mined,
            "quarantined_mined_strategies": quarantined_mined,
        },
        "ladder": {
            "builtin_strategies": builtin_strategies,
            "mined_strategies_active": mined_strategies,
            "mined_strategies_quarantined": quarantined_strategies,
        },
        "actualization": {
            "is_learning_actualized": is_learning_actualized,
            "auto_committed_observed": auto_committed_observed,
            "human_committed_mined_observed": human_committed_mined_observed,
            "quarantines_observed": len(quarantined_mined),
        },
    }


def render_status_lines(status: Dict[str, Any]) -> List[str]:
    """Format compute_status() output as printable lines for the CLI."""
    e = status["evidence"]
    c = status["candidates"]
    L = status["ladder"]
    a = status["actualization"]

    last = e.get("last_real_replay_at") or "never"
    bottom_line = (
        "LEARNING ACTUALIZED" if a["is_learning_actualized"]
        else "PLUMBED BUT DRY — no real-traffic loop has closed"
    )

    by_status = c.get("by_status") or {}
    by_status_str = (
        ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
        if by_status else "(empty)"
    )

    return [
        f"Bottom line:                 {bottom_line}",
        "",
        f"Store:                       {status['store_dir']}",
        "",
        "EVIDENCE",
        f"  step_records:              {e['step_records']}",
        f"  run_records:               {e['run_records']}",
        f"  last_real_replay_at:       {last}",
        f"  shadow_trials:             {e['shadow_trials']}",
        f"  audit_rows_total:          {e['audit_rows_total']}",
        f"    memory_prior_decisions:  {e['audit_memory_prior_decisions']}",
        f"    lesson_prior_decisions:  {e['audit_lesson_prior_decisions']}",
        f"    auto_commits:            {e['audit_auto_commits']}",
        "",
        "CANDIDATES",
        f"  by_status:                 {by_status_str}",
        f"  committed (mined):         {len(c['committed_mined_strategies'])}",
        f"  quarantined (mined):       {len(c['quarantined_mined_strategies'])}",
        "",
        "LIVE RECOVERY LADDER",
        f"  builtin_strategies:        {L['builtin_strategies']}",
        f"  mined_active:              {L['mined_strategies_active']}",
        f"  mined_quarantined:         {L['mined_strategies_quarantined']}",
        "",
        "ACTUALIZATION",
        f"  auto_committed observed:   {a['auto_committed_observed']}",
        f"  human-committed observed:  {a['human_committed_mined_observed']}",
        f"  quarantines observed:      {a['quarantines_observed']}",
    ]
