import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness

async def run_integrity_replay():
    harness = ReplayExperimentHarness()
    site_key = "saucedemo"
    template_name = "exp_saucedemo_checkout"
    
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "target_integrity" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Replaying {template_name} to gather target_integrity forensics...")
    
    for i in range(10):
        print(f"Run {i+1}...")
        result = await harness.run_full(site_key, template_name=template_name, skip_record=True)
        
        # Check if it's the anomaly: completed 24 steps but URL contains inventory.html
        if result.resolved_steps == 24:
            rules = result.verification_report.get("rule_results", [])
            final_url = ""
            for r in rules:
                if r.get("rule", {}).get("type") == "url_contains":
                    final_url = r.get("actual_value", "")
            if "inventory.html" in final_url:
                print(f"\nFOUND THE ANOMALY (Run {i+1})!")
                path = harness.save_result(result, output_dir)
                print(f"Saved replay result to {path}")
                
                # Analyze the result
                if result.step_outcomes:
                    for out in result.step_outcomes:
                        step = out.get("seq")
                        ti = out.get("target_integrity") or {}
                        if not ti:
                            continue
                            
                        exp_role = ti.get("expected_role")
                        exp_name = ti.get("expected_name")
                        res_tag = ti.get("resolved_tag")
                        res_text = ti.get("resolved_text")
                        
                        print(f"\nStep {step}:")
                        print(f"  Expected: role='{exp_role}', name='{exp_name}'")
                        print(f"  Resolved: tag='{res_tag}', text='{res_text}'")
                        print(f"  URL Before: {ti.get('url_before')}")
                        print(f"  URL After:  {ti.get('url_after')}")
                return
    
    print("Could not reproduce the 24-step anomaly in 10 runs.")
            
if __name__ == "__main__":
    asyncio.run(run_integrity_replay())
