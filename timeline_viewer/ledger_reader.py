"""Read-only loader for the OutcomeLedger. Pure functions, no caching beyond a TTL.

The ledger writes one JSON file per OutcomeRecord under
~/.browsermind/outcome_ledger/. Each file is a checksum envelope:
    {"_checksum": "...", "_data": { ...OutcomeRecord... }}
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

LEDGER_DIR = Path.home() / ".browsermind" / "outcome_ledger"
SNAPSHOT_LOG = Path.home() / ".browsermind" / "campaign_snapshots.jsonl"
UNKNOWN_QUEUE = Path.home() / ".browsermind" / "unknown_fields.jsonl"

_CACHE: dict[str, Any] = {"records": [], "loaded_at": 0.0}
_TTL_SECONDS = 5.0


def _load_all_records(force: bool = False) -> list[dict]:
    """Read every JSON file in the ledger dir; return inner _data dicts.
    Cached for _TTL_SECONDS so list-page refresh during a campaign isn't expensive.
    """
    now = time.time()
    if not force and (now - _CACHE["loaded_at"]) < _TTL_SECONDS:
        return _CACHE["records"]

    records: list[dict] = []
    if not LEDGER_DIR.exists():
        _CACHE["records"], _CACHE["loaded_at"] = records, now
        return records

    for path in LEDGER_DIR.glob("*.json"):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            data = blob.get("_data", blob)
            if isinstance(data, dict):
                records.append(data)
        except Exception:
            continue

    _CACHE["records"], _CACHE["loaded_at"] = records, now
    return records


def list_executions() -> list[dict]:
    """Group step records by execution_id and return one summary row per execution.

    Each row contains: execution_id, environment, template_name, started_at,
    ended_at, total_steps, successful_steps, success_rate, effect_verified_rate,
    overall_success.
    """
    records = _load_all_records()
    by_exec: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        eid = r.get("execution_id")
        if eid:
            by_exec[str(eid)].append(r)

    summaries: list[dict] = []
    for eid, recs in by_exec.items():
        steps = [r for r in recs if r.get("scope") == "step"]
        exec_scope = next((r for r in recs if r.get("scope") == "execution"), None)

        timestamps = sorted(r.get("timestamp", "") for r in recs if r.get("timestamp"))
        env_instance = next(
            (r.get("environment_instance") for r in recs if r.get("environment_instance")),
            "",
        )
        template_name = next(
            (
                r.get("metrics", {}).get("template_name")
                for r in steps
                if r.get("metrics", {}).get("template_name")
            ),
            "",
        )

        successful = sum(1 for s in steps if s.get("success"))
        ev_true = sum(
            1 for s in steps if s.get("metrics", {}).get("effect_verified") is True
        )

        overall = exec_scope.get("success") if exec_scope else (successful == len(steps) and len(steps) > 0)

        summaries.append({
            "execution_id": eid,
            "environment": env_instance,
            "template_name": template_name,
            "started_at": timestamps[0] if timestamps else "",
            "ended_at": timestamps[-1] if timestamps else "",
            "total_steps": len(steps),
            "successful_steps": successful,
            "success_rate": (successful / len(steps)) if steps else 0.0,
            "effect_verified_rate": (ev_true / successful) if successful else 0.0,
            "overall_success": bool(overall),
            "has_execution_record": exec_scope is not None,
        })

    summaries.sort(key=lambda s: s["started_at"], reverse=True)
    return summaries


def get_execution(execution_id: str) -> Optional[dict]:
    """Return full detail for one execution: header + ordered step list."""
    records = _load_all_records()
    matching = [r for r in records if str(r.get("execution_id") or "") == execution_id]
    if not matching:
        return None

    steps = [r for r in matching if r.get("scope") == "step"]
    exec_scope = next((r for r in matching if r.get("scope") == "execution"), None)
    steps.sort(key=lambda s: s.get("metrics", {}).get("step_seq") or 0)

    timestamps = sorted(r.get("timestamp", "") for r in matching if r.get("timestamp"))
    env_instance = next(
        (r.get("environment_instance") for r in matching if r.get("environment_instance")),
        "",
    )
    env_family = next(
        (r.get("environment_family") for r in matching if r.get("environment_family")),
        "",
    )
    template_name = next(
        (
            r.get("metrics", {}).get("template_name")
            for r in steps
            if r.get("metrics", {}).get("template_name")
        ),
        "",
    )

    successful = sum(1 for s in steps if s.get("success"))
    ev_true = sum(1 for s in steps if s.get("metrics", {}).get("effect_verified") is True)

    return {
        "execution_id": execution_id,
        "environment_instance": env_instance,
        "environment_family": env_family,
        "template_name": template_name,
        "started_at": timestamps[0] if timestamps else "",
        "ended_at": timestamps[-1] if timestamps else "",
        "total_steps": len(steps),
        "successful_steps": successful,
        "success_rate": (successful / len(steps)) if steps else 0.0,
        "effect_verified_rate": (ev_true / successful) if successful else 0.0,
        "overall_success": (
            exec_scope.get("success") if exec_scope else (successful == len(steps) and len(steps) > 0)
        ),
        "execution_evidence": exec_scope.get("evidence") if exec_scope else "",
        "steps": steps,
    }


def overview_stats() -> dict:
    """Aggregate counts for the campaign overview banner."""
    records = _load_all_records()
    steps = [r for r in records if r.get("scope") == "step"]
    execs = [r for r in records if r.get("scope") == "execution"]

    successful_steps = sum(1 for s in steps if s.get("success"))
    successful_execs = sum(1 for e in execs if e.get("success"))
    ev_true  = sum(1 for s in steps if s.get("success") and s.get("metrics", {}).get("effect_verified") is True)
    ev_false = sum(1 for s in steps if s.get("success") and s.get("metrics", {}).get("effect_verified") is False)
    ev_none  = sum(1 for s in steps if s.get("success") and s.get("metrics", {}).get("effect_verified") is None)
    ev_probed = ev_true + ev_false

    resolver_wins: Counter[str] = Counter()
    for s in steps:
        if not s.get("success"):
            continue
        resolver_wins[s.get("metrics", {}).get("resolved_by") or "unknown"] += 1

    failure_classes: Counter[str] = Counter()
    for s in steps:
        if s.get("success"):
            continue
        failure_classes[s.get("metrics", {}).get("failure_class") or "unclassified"] += 1

    by_env: Counter[str] = Counter()
    for r in records:
        if r.get("scope") == "step":
            by_env[r.get("environment_instance") or "unknown"] += 1

    unknown_field_count = 0
    if UNKNOWN_QUEUE.exists():
        try:
            with UNKNOWN_QUEUE.open(encoding="utf-8") as f:
                unknown_field_count = sum(1 for line in f if line.strip())
        except Exception:
            unknown_field_count = 0

    return {
        "total_steps": len(steps),
        "successful_steps": successful_steps,
        "step_success_rate": (successful_steps / len(steps)) if steps else 0.0,
        "effect_verified_true": ev_true,
        "effect_verified_false": ev_false,
        "effect_verified_none": ev_none,
        "effect_verified_rate": (ev_true / ev_probed) if ev_probed else 0.0,
        "effect_verified_rate_label": "of probed successes (True / (True+False))",
        "total_executions": len(execs),
        "successful_executions": successful_execs,
        "execution_success_rate": (successful_execs / len(execs)) if execs else 0.0,
        "unknown_field_count": unknown_field_count,
        "resolver_wins_top": resolver_wins.most_common(10),
        "failure_classes_top": failure_classes.most_common(10),
        "steps_by_environment": by_env.most_common(),
    }


def load_snapshots() -> list[dict]:
    """Read the campaign_snapshots.jsonl trend log."""
    if not SNAPSHOT_LOG.exists():
        return []
    rows: list[dict] = []
    try:
        with SNAPSHOT_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return rows


def dyad_summary() -> list[dict]:
    """Stage 2.2 — Dyad as observational lens (read-side only).

    Groups OutcomeRecords by (persona_id, environment_instance) and returns
    one row per dyad with computed metrics. NO PERSISTENCE — every call is
    a pure aggregation over the ledger.

    Per Stage 2 authorization: this is a materialized view, not a stored
    entity. Removing it later is a no-op for any downstream consumer.
    """
    records = _load_all_records()
    by_dyad: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        persona = str(r.get("persona_id") or "")
        env = r.get("environment_instance") or ""
        if not persona or not env:
            continue
        by_dyad[(persona, env)].append(r)

    rows: list[dict] = []
    for (persona, env), recs in by_dyad.items():
        steps = [r for r in recs if r.get("scope") == "step"]
        execs = [r for r in recs if r.get("scope") in ("execution", "workflow_instance")]

        successful_steps = sum(1 for s in steps if s.get("success"))
        ev_true = sum(1 for s in steps if s.get("metrics", {}).get("effect_verified") is True)

        # Proxy for "anti-bot heat": fraction of step failures classified as
        # AMBIGUOUS_TARGET or ambiguous identity. High values suggest the
        # site is serving structurally-different DOM to this persona.
        ambig_failures = sum(
            1 for s in steps
            if not s.get("success")
            and s.get("metrics", {}).get("failure_class") == "AMBIGUOUS_TARGET"
        )

        timestamps = sorted(r.get("timestamp", "") for r in recs if r.get("timestamp"))
        templates_touched = sorted({
            s.get("metrics", {}).get("template_name", "")
            for s in steps
            if s.get("metrics", {}).get("template_name")
        })

        rows.append({
            "persona_id": persona,
            "persona_short": persona[:8],
            "environment_instance": env,
            "total_interactions": len(recs),
            "step_count": len(steps),
            "execution_count": len(execs),
            "successful_steps": successful_steps,
            "success_rate": (successful_steps / len(steps)) if steps else 0.0,
            "effect_verified_true": ev_true,
            "effect_verified_rate": (ev_true / successful_steps) if successful_steps else 0.0,
            "ambiguous_failures": ambig_failures,
            "ambiguity_rate": (ambig_failures / len(steps)) if steps else 0.0,
            "first_seen": timestamps[0] if timestamps else "",
            "last_seen": timestamps[-1] if timestamps else "",
            "templates_touched": templates_touched,
            "distinct_templates": len(templates_touched),
        })

    # Order: most-active dyads first.
    rows.sort(key=lambda d: d["total_interactions"], reverse=True)
    return rows


def cascade_distribution() -> dict:
    """Stage 2.1 — cascade telemetry roll-up. Pure aggregation.

    Returns counts of records per cascade_layer and per
    cascade_workflow_class, plus the proxy_for distribution. Used by the
    Timeline Viewer overview and by the campaign analyzer.
    """
    records = _load_all_records()
    by_layer: Counter[int] = Counter()
    by_class: Counter[str] = Counter()
    by_proxy: Counter[str] = Counter()
    annotated = 0
    for r in records:
        m = r.get("metrics") or {}
        layer = m.get("cascade_layer")
        klass = m.get("cascade_workflow_class")
        proxy = m.get("cascade_proxy_for")
        if layer is not None or klass is not None:
            annotated += 1
        if layer is not None:
            by_layer[int(layer)] += 1
        if klass:
            by_class[klass] += 1
        if proxy:
            by_proxy[str(proxy)] += 1
    return {
        "total_records": len(records),
        "annotated_records": annotated,
        "annotation_rate": (annotated / len(records)) if records else 0.0,
        "by_layer": dict(by_layer),
        "by_workflow_class": dict(by_class),
        "by_proxy_for": dict(by_proxy),
    }


# ── UI Phase 1 — view-mode aggregations over the same primitive ─────────
#
# The audit established that Replay Studio, Failure Dashboard, Teacher Queue,
# Approval Queue, and Evidence Viewer are *views* over the same
# Execution → Step → Outcome → Evidence graph, not separate products.
# These functions are the data layer for those views.


def list_failed_executions() -> list[dict]:
    """Failed-only filter on list_executions(). The Failure Dashboard view."""
    return [e for e in list_executions() if not e["overall_success"]]


def list_teacher_queue_items() -> list[dict]:
    """Steps where field resolution was attempted and produced a label the
    Field Registry could not classify — the Teacher Queue view.

    Uses the unknown_fields.jsonl queue as canonical (written by replay
    engine on TargetResolutionError), supplemented by step records whose
    target_name resolved to no field_id.

    Returns a dict shape: {entries: [...], summary: [...], total: int}.
    The field is named "entries" (not "items") to avoid the Jinja2
    builtin-method collision on .items().
    """
    entries: list[dict] = []
    if UNKNOWN_QUEUE.exists():
        try:
            with UNKNOWN_QUEUE.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    entries.append({
                        "source": "unknown_fields_queue",
                        "target_name": row.get("target_name", ""),
                        "container_label": row.get("container_label", ""),
                        "template_id": row.get("template_id", ""),
                        "step_seq": row.get("step_seq"),
                        "timestamp": row.get("timestamp", ""),
                        "execution_id": row.get("execution_id", ""),
                    })
        except Exception:
            pass

    from collections import Counter as _C
    counts = _C(it["target_name"] for it in entries if it.get("target_name"))
    summary = [
        {"target_name": name, "occurrences": n}
        for name, n in counts.most_common()
    ]
    return {"entries": entries, "summary": summary, "total": len(entries)}
def list_pending_approvals() -> list[dict]:
    """Steps in the OutcomeLedger with actual_outcome='ASK' that have not
    yet been actioned. The Approval Queue view.

    A step is "pending" if it has actual_outcome='ASK' and its execution
    has no subsequent step record showing the action was taken. For now
    (no decisions ledger yet) all ASK records appear; once a decisions
    ledger is wired, decided records will be filtered.
    """
    records = _load_all_records()
    decisions = _load_approval_decisions()
    decided_keys: set[tuple] = {
        (str(d.get("execution_id")), int(d.get("step_seq")))
        for d in decisions
        if d.get("execution_id") is not None and d.get("step_seq") is not None
    }

    items: list[dict] = []
    for r in records:
        if r.get("scope") != "step":
            continue
        m = r.get("metrics") or {}
        if m.get("actual_outcome") != "ASK":
            continue
        eid = str(r.get("execution_id") or "")
        seq = m.get("step_seq")
        if seq is None:
            continue
        if (eid, int(seq)) in decided_keys:
            continue
        items.append({
            "execution_id": eid,
            "step_seq": int(seq),
            "action": m.get("action"),
            "role": m.get("role"),
            "name": m.get("name"),
            "evidence": r.get("evidence"),
            "timestamp": r.get("timestamp", ""),
            "environment": r.get("environment_instance", ""),
            "persona_id": str(r.get("persona_id") or ""),
            "template_name": m.get("template_name", ""),
            "failure_reason": m.get("failure_reason") or m.get("root_cause"),
        })
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items


# ── Approval decisions (Phase 1 minimal append-only journal) ────────────

APPROVAL_LOG = Path.home() / ".browsermind" / "approval_decisions.jsonl"


def _load_approval_decisions() -> list[dict]:
    if not APPROVAL_LOG.exists():
        return []
    rows: list[dict] = []
    try:
        with APPROVAL_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return rows


def record_approval_decision(
    execution_id: str,
    step_seq: int,
    decision: str,
    reason: str = "",
    operator: str = "",
) -> dict:
    """Append-only write of an approve/reject decision. Phase 1 minimal —
    no policy linkage yet. The decision is recorded; whether the runtime
    later acts on it is a separate phase.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"decision must be 'approved' or 'rejected', got {decision!r}")
    import datetime as _dt
    row = {
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
        "execution_id": execution_id,
        "step_seq": int(step_seq),
        "decision": decision,
        "reason": reason,
        "operator": operator,
    }
    APPROVAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with APPROVAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def list_approval_decisions(limit: int = 100) -> list[dict]:
    """Read the audit trail of approval/rejection decisions."""
    rows = _load_approval_decisions()
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return rows[:limit]


# ── Live Workspace (read-side over the live-state file) ─────────────────
#
# The replay engine writes a small JSON file at ~/.browsermind/_live_state.json
# at step boundaries. The Live Workspace polls this file. When no run is
# active, the file may be missing or stale — the API surfaces both.

LIVE_STATE_FILE = Path.home() / ".browsermind" / "_live_state.json"
_LIVE_STALE_AFTER_SECONDS = 30


def live_workspace_state() -> dict:
    """Return the current live-state snapshot, with staleness annotation.

    Shape (when live):
      {
        "live": True,
        "stale": False,
        "execution_id": str, "persona_id": str, "persona_name": str,
        "environment_instance": str, "template_name": str,
        "current_step_seq": int, "current_action": str,
        "current_target_role": str, "current_target_name": str,
        "current_strategy": str|None,
        "last_update_ts": str (ISO),
        "age_seconds": float,
        "step_count_so_far": int,
        "successful_so_far": int,
        "failed_so_far": int,
      }

    Shape (when no live state exists or stale):
      {
        "live": False, "stale": True|False,
        "reason": "no_state_file"|"stale",
        ... (last-known fields if present)
      }
    """
    if not LIVE_STATE_FILE.exists():
        return {"live": False, "stale": False, "reason": "no_state_file"}
    try:
        data = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"live": False, "stale": True, "reason": "unreadable"}

    last = data.get("last_update_ts", "")
    age_s = 9999.0
    try:
        import datetime as _dt
        if last:
            ts = _dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
            age_s = (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds()
    except Exception:
        pass

    stale = age_s > _LIVE_STALE_AFTER_SECONDS
    out = dict(data)
    out["live"] = (not stale) and bool(data.get("execution_id"))
    out["stale"] = stale
    out["age_seconds"] = age_s
    if stale:
        out["reason"] = "stale"
    return out
