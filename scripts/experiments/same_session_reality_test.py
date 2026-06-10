#!/usr/bin/env python3
"""
Phase 2: Same Session Reality Test

Records a workflow once, then replays it 20 times in the same session.
Measures state_match (goal achievement).

Workflows:
- SauceDemo Login (saucedemo)
- Wikipedia Search (static_baseline)
- GitHub Repository Search (github)
"""

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

import argparse

async def run_reality_test():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=str, help="Specific site to test")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs")
    args = parser.parse_args()

    harness = ReplayExperimentHarness()
    sites = [args.target] if args.target else ["saucedemo", "static_baseline", "github"]
    runs_per_site = args.runs

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "reality_test" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for site_key in sites:
        print(f"\n=========================================")
        print(f"Testing {site_key}")
        print(f"=========================================")
        
        site = get_site(site_key)
        
        # 1. Record once
        print(f"\n--- Recording {site_key} ---")
        print("Please complete the workflow in the opened browser window.")
        first_result = await harness.run_full(site_key, skip_record=False)
        template_name = first_result.template_name
        
        print(f"\nSuccessfully recorded template: {template_name}")
        print(f"First run state match: {first_result.verification_report.get('state_match') if first_result.verification_report else False}")
        
        # 2. Replay 20 times
        print(f"\n--- Replaying {site_key} 20 times ---")
        state_matches = 0
        
        for i in range(runs_per_site):
            print(f"Run {i+1}/{runs_per_site}...")
            result = await harness.run_full(site_key, template_name=template_name, skip_record=True)
            
            # Save result
            path = harness.save_result(result, output_dir / site_key)
            
            match = False
            if result.verification_report:
                match = result.verification_report.get("state_match", False)
            
            if match:
                state_matches += 1
                
            print(f"  Result: {'PASS' if match else 'FAIL'}")

        success_rate = state_matches / runs_per_site
        print(f"\n{site_key} state_match rate: {success_rate*100:.1f}%")
        
        summary.append({
            "site": site_key,
            "template": template_name,
            "runs": runs_per_site,
            "state_matches": state_matches,
            "success_rate": success_rate
        })

    # Write summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=========================================")
    print("Reality Test Complete")
    for s in summary:
        print(f"{s['site']}: {s['success_rate']*100:.1f}% state_match")
    print(f"Saved to: {output_dir}")

if __name__ == "__main__":
    try:
        asyncio.run(run_reality_test())
    except KeyboardInterrupt:
        print("\nInterrupted.")
