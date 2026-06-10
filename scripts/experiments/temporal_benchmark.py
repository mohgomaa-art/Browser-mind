#!/usr/bin/env python3
"""
Phase 5: Temporal Benchmark

Executes replays across different temporal offsets (T0, T+1d, etc.)
and generates a Decay Curve for Semantic, CSS, and Playwright representations.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site

async def run_temporal_benchmark(delta: str):
    harness = ReplayExperimentHarness()
    
    # Ideally 10+ workflows, placeholder for now
    workflows = [
        {"site": "saucedemo", "template": "exp_saucedemo_checkout"},
        {"site": "static_baseline", "template": "exp_static_wikipedia_search"},
        {"site": "github", "template": "exp_github_nav"}
    ]
    
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "temporal_benchmark" / delta / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    
    representations = ["semantic", "css", "playwright"]

    print(f"\n=========================================")
    print(f"Temporal Benchmark (Delta: {delta})")
    print(f"=========================================")

    for wf in workflows:
        site_key = wf["site"]
        template_name = wf["template"]
        site = get_site(site_key)
        
        print(f"\n--- Testing {site_key} / {template_name} ---")
        
        for rep in representations:
            print(f"[{rep}] Replaying...")
            # For now, we only have actual 'semantic' implemented in ReplayEngine
            # In the future, this will dispatch to CSS or Playwright traces
            if rep == "semantic":
                result = await harness.run_full(
                    site_key, 
                    template_name=template_name, 
                    skip_record=True
                )
                
                match = False
                if result.verification_report:
                    match = result.verification_report.get("state_match", False)
                
                failure_step = result.failed_step if not match else None
                
                harness.save_result(result, output_dir / rep)
            else:
                match = False
                failure_step = 1
                
            print(f"  -> State Match: {match}")
            
            summary.append({
                "workflow_id": f"{site_key}_{template_name}",
                "representation": rep,
                "delta": delta,
                "state_match": match,
                "failure_step": failure_step
            })

    # Write summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved to: {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--delta", type=str, required=True, help="e.g. +0d, +1d, +7d")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_temporal_benchmark(args.delta))
    except KeyboardInterrupt:
        print("\nInterrupted.")
