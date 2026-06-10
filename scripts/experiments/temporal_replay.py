#!/usr/bin/env python3
"""
Experiment 1: Temporal Replay Framework (Workflow Half-Life)
Measures the survivability of workflows over time (Day 0, Day 1, Day 7, Day 30).

Key addition in P4C: Environment Fingerprinting.
Each eval run records the environment fingerprint alongside the replay result,
enabling post-hoc distinction between:
  - Workflow died        (fingerprint unchanged, resolution_rate dropped)
  - Environment changed  (fingerprint changed, resolution_rate dropped)
"""
import argparse
import subprocess
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def get_latest_report(site_key: str) -> dict:
    reports_dir = ROOT_DIR / "reports" / "replay_experiments"
    if not reports_dir.exists():
        return {}
    dirs = [d for d in reports_dir.iterdir() if d.is_dir()]
    if not dirs:
        return {}
    latest_dir = sorted(dirs, key=lambda d: d.name)[-1]
    for file in latest_dir.glob(f"{site_key}_*.json"):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Temporal Replay Framework")
    parser.add_argument("--mode", choices=["baseline", "temporal_eval"], required=True,
                        help="Record a baseline (Day 0) or evaluate (Day N)")
    parser.add_argument("--site", required=True, help="Site key to test")
    parser.add_argument("--delay-days", type=int, default=0, help="Actual delay in days since baseline")
    args = parser.parse_args()

    print(f"=== Temporal Replay Framework ===")
    print(f"Mode: {args.mode} | Site: {args.site} | Delta: +{args.delay_days}d\n")

    out_dir = ROOT_DIR / "reports" / "survivability" / "temporal"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.site}_temporal.json"

    if out_file.exists():
        with open(out_file, "r", encoding="utf-8") as f:
            temporal_data = json.load(f)
    else:
        temporal_data = {"site": args.site, "runs": []}

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    if args.mode == "baseline":
        print(f"Recording Baseline (Day 0) for {args.site}...")
        subprocess.run(["python", "scripts/auto_record.py", "run", "--site", args.site],
                       env=env, cwd=ROOT_DIR)
        print("\nBaseline recorded and compiled.")

        temporal_data["baseline_recorded_at"] = datetime.now(timezone.utc).isoformat()
        temporal_data["runs"].append({
            "delay_days": 0,
            "resolution_rate": 1.0,
            "state_match": True,
            "workflow_success": True,
            "env_fingerprint": None,      # captured during actual replay, not record
            "env_delta": None,
            "failure_cause": None,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

    elif args.mode == "temporal_eval":
        print(f"Executing Temporal Evaluation (+{args.delay_days} days) for {args.site}...")
        subprocess.run(["python", "scripts/run_replay_experiments.py", "replay", "--site", args.site],
                       env=env, cwd=ROOT_DIR)

        report = get_latest_report(args.site)
        if not report:
            print("Could not find generated ReplayReport.")
            sys.exit(1)

        resolution_rate = report.get("resolution_rate", 0.0)
        replay_success  = report.get("replay_success", False)

        # Extract state_inference
        state_inference = report.get("state_inference") or {}
        state_match = state_inference.get("match", False)

        # Extract environment fingerprints
        fp_end   = report.get("env_fingerprint_end") or {}
        baseline_runs = [r for r in temporal_data.get("runs", []) if r.get("delay_days") == 0]
        fp_baseline = (baseline_runs[0].get("env_fingerprint") if baseline_runs else None) or {}

        # Compute environment delta
        env_delta = None
        failure_cause = None
        if fp_baseline and fp_end:
            dom_changed = fp_baseline.get("dom_hash") != fp_end.get("dom_hash")
            env_delta = {"dom_changed": dom_changed}
            if not replay_success:
                failure_cause = "environment_changed" if dom_changed else "workflow_degraded"
        elif not replay_success:
            failure_cause = "unknown"

        temporal_data["runs"].append({
            "delay_days": args.delay_days,
            "resolution_rate": resolution_rate,
            "state_match": state_match,
            "workflow_success": replay_success and state_match,
            "env_fingerprint": fp_end,
            "env_delta": env_delta,
            "failure_cause": failure_cause,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

        if replay_success and state_match:
            print(f"\n[Temporal] SURVIVED +{args.delay_days} days | resolution={resolution_rate:.1%}")
        else:
            cause_label = f"({failure_cause})" if failure_cause else ""
            print(f"\n[Temporal] DECAYED at +{args.delay_days} days | resolution={resolution_rate:.1%} {cause_label}")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(temporal_data, f, indent=2)
    print(f"Metrics → {out_file}")


if __name__ == "__main__":
    main()
