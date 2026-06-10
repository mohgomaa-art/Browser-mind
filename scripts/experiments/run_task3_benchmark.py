"""Task 3A/3B: Record a new session to capture container_label, then replay 20 times to measure identity preservation."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site

async def main():
    harness = ReplayExperimentHarness(headless=False)
    site_key = "saucedemo"
    site = get_site(site_key)
    
    print("\n==========================================")
    print("STEP 1: RECORD NEW SESSION")
    print("==========================================")
    print("Please login, add 'Sauce Labs Backpack' to cart, go to cart, and checkout.")
    # Record + Compile once
    session = await harness.record(site)
    template = harness.compile(session, f"exp_{site_key}_checkout")
    
    print(f"\n==========================================")
    print("STEP 2: REPLAY 20 TIMES")
    print("==========================================")
    
    ambiguous_runs = 0
    resolved_container_runs = 0
    
    harness.headless = True # Replay headless for speed
    
    for i in range(20):
        try:
            print(f"\nRun {i + 1}/20...")
            # Replay engine will pick up the new compiled template
            report = await harness.replay(site, template)
            result = harness.result_from_report(site=site, template=template, report=report)
            
            ambiguous = [s for s in result.step_outcomes if s.get("outcome") == "AMBIGUOUS_IDENTITY"]
            if ambiguous:
                ambiguous_runs += 1
                
            # Check if any step resolved via semantic+container
            container_resolved = [s for s in result.step_outcomes if s.get("resolution_strategy") == "semantic+container"]
            if container_resolved:
                resolved_container_runs += 1
                
            print(f"  Ambiguity Rate: {result.ambiguity_rate:.2f}")
            print(f"  Replay Success: {result.replay_success}")
            if container_resolved:
                print(f"  [SUCCESS] Identity Resolved via semantic+container in {len(container_resolved)} steps!")
                
            if ambiguous:
                print(f"  [WARNING] AMBIGUOUS_IDENTITY occurred in {len(ambiguous)} steps.")
                
            if i == 0:
                # Print selection forensics for the Add to cart step
                add_to_cart_step = next((s for s in result.step_outcomes if s.get("name") == "Add to cart"), None)
                if add_to_cart_step:
                    print(f"\n  [Forensics] Step {add_to_cart_step['seq']} Selection Forensics:")
                    print(f"  {add_to_cart_step.get('target_integrity', {}).get('selection_forensics', {})}")

        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n==========================================")
    print("FINAL RESULTS")
    print("==========================================")
    print(f"Total Runs: 20")
    print(f"Runs with semantic+container resolution : {resolved_container_runs}/20")
    print(f"Runs with AMBIGUOUS_IDENTITY          : {ambiguous_runs}/20")

if __name__ == "__main__":
    asyncio.run(main())
