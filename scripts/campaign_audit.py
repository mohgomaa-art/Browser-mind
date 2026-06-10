"""
Campaign audit script — reads persisted store and emits metrics JSON.
Usage: python scripts/campaign_audit.py [--out reports/campaign_audit_baseline.json]
"""
from __future__ import annotations
import argparse
import json
import pathlib
import statistics
from collections import Counter, defaultdict
from typing import Any

STORE = pathlib.Path.home() / ".browsermind"
QUEUE_FILE = STORE / "missions" / "queue.json"
SSTG_FILE = STORE / "sstg.json"
MEMORY_DIR = STORE / "memory"


def _load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def audit_queue() -> dict:
    raw = _load_json(QUEUE_FILE)
    if raw is None:
        return {"error": "queue.json not found"}
    entries = raw.get("entries", raw) if isinstance(raw, dict) else raw

    status_counts = Counter(e["status"] for e in entries)
    done = [e for e in entries if e["status"] == "done"]
    failed = [e for e in entries if e["status"] == "failed"]
    paused = [e for e in entries if e["status"] == "paused"]

    def _q(entry: dict) -> float:
        return entry.get("avg_quality_score") or 0.0

    qs = [_q(e) for e in done]
    quality_buckets = {
        "0.00": sum(1 for q in qs if q == 0.0),
        "0.01-0.24": sum(1 for q in qs if 0.0 < q < 0.25),
        "0.25-0.49": sum(1 for q in qs if 0.25 <= q < 0.5),
        "0.50-0.74": sum(1 for q in qs if 0.5 <= q < 0.75),
        "0.75-1.00": sum(1 for q in qs if q >= 0.75),
    }

    # step distribution
    steps = [e.get("last_steps") or 0 for e in done]
    # error taxonomy from last_error
    errors = [e.get("last_error") or "" for e in done + failed]
    error_classes: Counter = Counter()
    for err in errors:
        if not err:
            continue
        if "timeout" in err.lower():
            error_classes["timeout"] += 1
        elif "cloudflare" in err.lower() or "captcha" in err.lower() or "bot" in err.lower():
            error_classes["anti_bot"] += 1
        elif "auth" in err.lower() or "login" in err.lower():
            error_classes["auth_gate"] += 1
        elif "navigation" in err.lower():
            error_classes["navigation"] += 1
        elif "net::" in err.lower() or "connection" in err.lower():
            error_classes["network"] += 1
        else:
            error_classes["other"] += 1

    # per-site quality — top and bottom
    site_quality = sorted(
        [{"site": e["site_key"], "quality": _q(e), "steps": e.get("last_steps") or 0}
         for e in done],
        key=lambda x: x["quality"],
    )

    return {
        "total_entries": len(entries),
        "status_counts": dict(status_counts),
        "done_count": len(done),
        "failed_count": len(failed),
        "paused_count": len(paused),
        "quality": {
            "min": round(min(qs), 3) if qs else 0,
            "max": round(max(qs), 3) if qs else 0,
            "mean": round(sum(qs) / len(qs), 3) if qs else 0,
            "median": round(statistics.median(qs), 3) if qs else 0,
            "buckets": quality_buckets,
            "zero_quality_pct": round(quality_buckets["0.00"] / len(done) * 100, 1) if done else 0,
        },
        "steps": {
            "total": sum(steps),
            "mean": round(sum(steps) / len(steps), 1) if steps else 0,
            "max": max(steps) if steps else 0,
        },
        "error_classes": dict(error_classes),
        "bottom_10_sites": site_quality[:10],
        "top_10_sites": site_quality[-10:][::-1],
    }


def audit_sstg() -> dict:
    raw = _load_json(SSTG_FILE)
    if raw is None:
        return {"error": "sstg.json not found"}

    nodes = raw.get("nodes", {})
    edges = raw.get("edges", [])

    # state fingerprints
    state_types: Counter = Counter()
    for fingerprint, node_data in nodes.items():
        if isinstance(node_data, dict):
            state_type = node_data.get("page_type") or node_data.get("state_label") or "unknown"
        else:
            state_type = "unknown"
        state_types[state_type] += 1

    # transition action types
    action_types: Counter = Counter()
    env_coverage: set = set()
    for edge in edges:
        if isinstance(edge, dict):
            action_types[edge.get("capability_hash", "unknown")[:8]] += 1
            env_coverage.update(edge.get("env_keys", []))

    unknown_count = state_types.get("unknown", 0)
    total_nodes = len(nodes)

    return {
        "node_count": total_nodes,
        "edge_count": len(edges),
        "env_coverage": sorted(env_coverage),
        "env_count": len(env_coverage),
        "state_type_distribution": dict(state_types.most_common(20)),
        "unknown_state_pct": round(unknown_count / total_nodes * 100, 1) if total_nodes else 0,
        "top_transitions": dict(Counter(
            e.get("capability_hash", "")[:8] for e in edges if isinstance(e, dict)
        ).most_common(10)),
    }


def audit_capabilities() -> dict:
    cap_files = list(MEMORY_DIR.rglob("capabilities/*.json"))
    records_by_tier: Counter = Counter()
    env_sets: defaultdict = defaultdict(set)
    families: Counter = Counter()
    source_types: Counter = Counter()

    for f in cap_files:
        raw = _load_json(f)
        if not isinstance(raw, dict):
            continue
        tier = raw.get("promotion_tier", "UNKNOWN")
        records_by_tier[tier] += 1
        envs = raw.get("transfer_envs", [])
        for env in envs:
            env_sets[tier].add(env)
        invs = raw.get("invariants", [])
        for inv in invs:
            if "search" in inv:
                families["search"] += 1
            elif "auth" in inv or "login" in inv:
                families["auth"] += 1
            elif "form" in inv:
                families["form"] += 1
            elif "filter" in inv:
                families["filter"] += 1
            elif "navigation" in inv or "link" in inv:
                families["navigation"] += 1
        source_types[raw.get("source", "unknown")] += 1

    return {
        "total_capability_records": len(cap_files),
        "by_tier": dict(records_by_tier),
        "by_family": dict(families),
        "by_source": dict(source_types),
        "env_coverage_by_tier": {k: len(v) for k, v in env_sets.items()},
    }


def audit_procedural() -> dict:
    proc_files = list(MEMORY_DIR.rglob("procedural.json"))
    total_records = 0
    env_count = 0
    family_counts: Counter = Counter()
    strategy_success: Counter = Counter()

    for f in proc_files:
        raw = _load_json(f)
        if not isinstance(raw, dict):
            continue
        env_count += 1
        for key, rec in raw.items():
            if not isinstance(rec, dict):
                continue
            total_records += 1
            family = rec.get("intent_family", "unknown")
            family_counts[family] += 1
            for strategy, counts in (rec.get("strategy_counts") or {}).items():
                if isinstance(counts, dict):
                    strategy_success[strategy] += counts.get("success", 0)

    return {
        "total_procedural_records": total_records,
        "env_files": env_count,
        "by_family": dict(family_counts),
        "strategy_success_counts": dict(strategy_success.most_common(10)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="reports/campaign_audit_baseline.json")
    args = parser.parse_args()

    print("Auditing queue...")
    queue_metrics = audit_queue()

    print("Auditing SSTG...")
    sstg_metrics = audit_sstg()

    print("Auditing capability records...")
    cap_metrics = audit_capabilities()

    print("Auditing procedural records...")
    proc_metrics = audit_procedural()

    report = {
        "queue": queue_metrics,
        "sstg": sstg_metrics,
        "capabilities": cap_metrics,
        "procedural": proc_metrics,
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nBaseline audit written to: {out}")

    # Print summary
    q = queue_metrics
    print(f"\n=== BASELINE SUMMARY ===")
    print(f"Sites done:       {q.get('done_count', 0)}")
    print(f"Sites pending:    {q.get('status_counts', {}).get('pending', 0)}")
    print(f"Quality mean:     {q.get('quality', {}).get('mean', 0):.2f}")
    print(f"Quality=0 sites:  {q.get('quality', {}).get('buckets', {}).get('0.00', 0)} "
          f"({q.get('quality', {}).get('zero_quality_pct', 0):.1f}%)")
    print(f"Total steps:      {q.get('steps', {}).get('total', 0)}")
    s = sstg_metrics
    print(f"SSTG nodes:       {s.get('node_count', 0)}")
    print(f"SSTG edges:       {s.get('edge_count', 0)}")
    print(f"SSTG unknown%:    {s.get('unknown_state_pct', 0):.1f}%")
    c = cap_metrics
    print(f"Cap records:      {c.get('total_capability_records', 0)}")
    print(f"  by tier:        {c.get('by_tier', {})}")
    p = proc_metrics
    print(f"Proc records:     {p.get('total_procedural_records', 0)} "
          f"across {p.get('env_files', 0)} envs")


if __name__ == "__main__":
    main()
