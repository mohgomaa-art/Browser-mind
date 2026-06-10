#!/usr/bin/env python3
"""
Phase 4: Recovery Ablation

Runs Replay with Recovery OFF vs Recovery ON.
Measures state_match and false recovery count.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site

async def run_ablation():
    harness = ReplayExperimentHarness()
    sites = ["saucedemo", "static_baseline", "github"]
    runs_per_condition = 10

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "recovery_ablation" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for site_key in sites:
        print(f"\n=========================================")
        print(f"Ablation Testing {site_key}")
        print(f"=========================================")
        
        site = get_site(site_key)
        
        # 1. Record once
        print(f"\n--- Recording {site_key} ---")
        first_result = await harness.run_full(site_key, skip_record=False)
        template_name = first_result.template_name
        print(f"Successfully recorded template: {template_name}")
        
        conditions = [
            {"name": "Recovery OFF", "enable_recovery": False},
            {"name": "Recovery ON", "enable_recovery": True}
        ]
        
        site_stats = {}
        for condition in conditions:
            name = condition["name"]
            enable_rec = condition["enable_recovery"]
            print(f"\n--- {name} ---")
            
            state_matches = 0
            recovered_steps = 0
            
            for i in range(runs_per_condition):
                result = await harness.run_full(
                    site_key, 
                    template_name=template_name, 
                    skip_record=True, 
                    enable_recovery=enable_rec
                )
                
                match = False
                if result.verification_report:
                    match = result.verification_report.get("state_match", False)
                
                if match:
                    state_matches += 1
                    
                # Count recovered steps
                for step in result.step_outcomes:
                    if step.get("recovered_by"):
                        recovered_steps += 1
                        
                # save result
                path = harness.save_result(result, output_dir / f"{site_key}_{name.replace(' ', '_')}")
                
            success_rate = state_matches / runs_per_condition
            site_stats[name] = {
                "success_rate": success_rate,
                "recovered_steps_total": recovered_steps
            }
            
            print(f"{name} state_match rate: {success_rate*100:.1f}%")

        off_rate = site_stats["Recovery OFF"]["success_rate"]
        on_rate = site_stats["Recovery ON"]["success_rate"]
        improvement = (on_rate - off_rate) * 100
        
        summary.append({
            "site": site_key,
            "template": template_name,
            "recovery_off_rate": off_rate,
            "recovery_on_rate": on_rate,
            "recovery_helped": improvement > 0,
            "improvement": improvement
        })

    # Write summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=========================================")
    print("Ablation Test Complete")
    for s in summary:
        print(f"{s['site']}: OFF={s['recovery_off_rate']*100:.1f}%, ON={s['recovery_on_rate']*100:.1f}% -> Helped: {s['recovery_helped']} ({s['improvement']:.1f}%)")
    print(f"Saved to: {output_dir}")

if __name__ == "__main__":
    try:
        asyncio.run(run_ablation())
    except KeyboardInterrupt:
        print("\nInterrupted.")
