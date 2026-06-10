#!/usr/bin/env python3
"""
P4C Aggregate — reads all replay experiment reports and computes the
Representation Ledger distribution across every run.

Usage:
    python scripts/experiments/p4c_aggregate.py
    python scripts/experiments/p4c_aggregate.py --since 2026-06-01
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "reports" / "replay_experiments"
OUT_DIR = ROOT_DIR / "reports" / "survivability"


def load_all_reports(since: str = None) -> list:
    reports = []
    if not REPORTS_DIR.exists():
        return reports
    for run_dir in sorted(REPORTS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        if since and run_dir.name < since:
            continue
        for f in run_dir.glob("*.json"):
            if f.name in ("summary.json",):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "workflow_id" in data and "step_outcomes" in data:
                    reports.append(data)
            except Exception:
                pass
    return reports


def aggregate(reports: list) -> dict:
    # Resolution Depth Distribution
    depth_counts: dict = defaultdict(int)
    rep_counts: dict = defaultdict(int)   # by resolved_by
    rep_success: dict = defaultdict(int)  # steps that resolved (not SKIPPED/FAILED)
    rep_attempts: dict = defaultdict(int) # all attempts per representation
    
    total_steps_resolved = 0
    total_steps_run = 0
    
    site_results: dict = defaultdict(lambda: {"runs": 0, "success": 0, "state_match": 0})
    
    for report in reports:
        site = report.get("site", "unknown")
        site_results[site]["runs"] += 1
        if report.get("replay_success"):
            site_results[site]["success"] += 1
        
        si = report.get("state_inference") or {}
        if si.get("match"):
            site_results[site]["state_match"] += 1

        for step in report.get("step_outcomes", []):
            outcome    = step.get("outcome", "")
            resolved_by = step.get("resolved_by")
            depth       = step.get("resolution_depth")
            
            if outcome in ("SKIPPED",):
                continue

            total_steps_run += 1

            if outcome == "RESOLVED" or outcome == "TRANSITION_SUCCESS":
                total_steps_resolved += 1
                if resolved_by:
                    rep_counts[resolved_by] += 1
                    rep_success[resolved_by] += 1
                if depth is not None:
                    depth_counts[depth] += 1
            elif resolved_by:
                # attempted but failed
                rep_attempts[resolved_by] += 1

    # Build depth distribution
    total_resolved = sum(depth_counts.values())
    depth_dist = []
    for d in sorted(depth_counts):
        count = depth_counts[d]
        share = count / total_resolved if total_resolved else 0
        label = {0: "primary/loose semantic", 1: "placeholder", 2: "nearby_text", 3: "structural_path"}.get(d, f"depth_{d}")
        depth_dist.append({"depth": d, "label": label, "count": count, "share": round(share, 4)})

    # Build representation survival table
    all_reps = set(rep_counts) | set(rep_attempts)
    rep_table = []
    for rep in sorted(all_reps):
        success  = rep_counts.get(rep, 0)
        attempts = rep_attempts.get(rep, 0)
        total    = success + attempts
        rate     = success / total if total else 0
        rep_table.append({
            "representation": rep,
            "resolved": success,
            "failed": attempts,
            "total": total,
            "survival_rate": round(rate, 4),
        })
    rep_table.sort(key=lambda x: -x["resolved"])

    # Site summary
    site_table = []
    for site, data in sorted(site_results.items()):
        runs = data["runs"]
        site_table.append({
            "site": site,
            "runs": runs,
            "replay_success_rate": round(data["success"] / runs, 4) if runs else 0,
            "state_match_rate": round(data["state_match"] / runs, 4) if runs else 0,
        })

    # Depth 0 share
    depth0_share = 0
    if depth_dist:
        d0 = next((d for d in depth_dist if d["depth"] == 0), None)
        depth0_share = d0["share"] if d0 else 0

    return {
        "total_reports": len(reports),
        "total_steps_run": total_steps_run,
        "total_steps_resolved": total_steps_resolved,
        "overall_resolution_rate": round(total_steps_resolved / total_steps_run, 4) if total_steps_run else 0,
        "depth0_share": depth0_share,
        "depth_distribution": depth_dist,
        "representation_survival": rep_table,
        "site_summary": site_table,
    }


def print_report(agg: dict):
    print()
    print("=" * 65)
    print("  P4C Aggregate — Representation Ledger")
    print("=" * 65)
    print(f"  Reports analyzed : {agg['total_reports']}")
    print(f"  Steps run        : {agg['total_steps_run']}")
    print(f"  Steps resolved   : {agg['total_steps_resolved']}")
    print(f"  Resolution rate  : {agg['overall_resolution_rate']:.1%}")
    print(f"  Depth-0 share    : {agg['depth0_share']:.1%}")
    print()

    print("  Resolution Depth Distribution")
    print("  " + "-" * 55)
    for d in agg["depth_distribution"]:
        bar = "█" * int(d["share"] * 30)
        print(f"  depth={d['depth']} ({d['label']:<22}) {d['count']:>5} steps  {d['share']:>6.1%}  {bar}")
    print()

    print("  Representation Survival Rate")
    print("  " + "-" * 55)
    print(f"  {'Representation':<22} {'Resolved':>8} {'Failed':>8} {'Rate':>8}")
    for r in agg["representation_survival"]:
        print(f"  {r['representation']:<22} {r['resolved']:>8} {r['failed']:>8} {r['survival_rate']:>8.1%}")
    print()

    print("  Site Summary")
    print("  " + "-" * 55)
    print(f"  {'Site':<22} {'Runs':>5} {'Replay':>8} {'StateMatch':>10}")
    for s in agg["site_summary"]:
        print(f"  {s['site']:<22} {s['runs']:>5} {s['replay_success_rate']:>8.1%} {s['state_match_rate']:>10.1%}")
    print()

    # Key finding
    d0 = agg["depth0_share"]
    if d0 >= 0.90:
        verdict = "STRONG — abstraction AND representation survive"
    elif d0 >= 0.60:
        verdict = "MODERATE — abstraction survives, some representation fragility"
    else:
        verdict = "FRAGILE — system survives, but representation does not"
    print(f"  Verdict: {verdict}")
    print()


def main():
    parser = argparse.ArgumentParser(description="P4C Aggregate — Representation Ledger")
    parser.add_argument("--since", default=None, help="Only include run dirs >= this string (e.g. 20260601)")
    parser.add_argument("--output", default=None, help="Write JSON output to file")
    args = parser.parse_args()

    reports = load_all_reports(since=args.since)
    if not reports:
        print("[P4C Aggregate] No reports found.")
        return

    agg = aggregate(reports)
    print_report(agg)

    out_path = args.output or str(OUT_DIR / "p4c_aggregate.json")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)
    print(f"  JSON → {out_path}")


if __name__ == "__main__":
    main()
