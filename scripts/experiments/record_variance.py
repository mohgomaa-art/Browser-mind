"""Human Variance Data Collection.

Records multiple demonstrations for the same target goal, prompting the user
to take explicitly different paths each time. Clusters these demonstrations
under a single `variance_group_id` for distance analysis.

Usage:
    python scripts/experiments/record_variance.py --target saucedemo --runs 5
"""
import asyncio
import argparse
import uuid
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site

async def main():
    parser = argparse.ArgumentParser(description="Human Variance Data Collection")
    parser.add_argument("--target", default="saucedemo", help="Site key (default: saucedemo)")
    parser.add_argument("--runs", type=int, default=3, help="Number of varied human demonstrations to record (default: 3)")
    args = parser.parse_args()

    harness = ReplayExperimentHarness(headless=False)
    site = get_site(args.target)
    
    variance_group_id = str(uuid.uuid4())
    print(f"\n========================================================")
    print(f" HUMAN VARIANCE DATA COLLECTION")
    print(f" Target: {site.label} ({site.key})")
    print(f" Group ID: {variance_group_id}")
    print(f"========================================================\n")
    print(f"You will be asked to complete the SAME goal {args.runs} times.")
    print(f"CRITICAL: You must take an explicitly DIFFERENT path each time.")
    print(f"Example variations:")
    print(f"  - Using search instead of navigation")
    print(f"  - Clicking from different collections")
    print(f"  - Taking suboptimal or winding routes")
    print(f"  - Interacting with different visually equivalent targets\n")

    recorded_sessions = []

    for i in range(args.runs):
        print(f"\n--- Variance Run {i + 1} of {args.runs} ---")
        print("Please complete the workflow using a unique path.")
        session = await harness.record(site)
        
        # Tag the session with the variance group
        session.metadata["variance_group_id"] = variance_group_id
        session.metadata["variance_run_index"] = i + 1
        
        # Save updated metadata
        harness.demo_repo.save(session)
        
        # We also compile it immediately so we have the semantic WorkflowTemplate for WorkflowDistance
        template_name = f"var_{args.target}_{variance_group_id[:8]}_{i+1}"
        harness.compile(session, template_name)
        
        recorded_sessions.append(session.id)
        
    print(f"\n========================================================")
    print(f" COLLECTION COMPLETE")
    print(f"========================================================")
    print(f"Group ID: {variance_group_id}")
    print(f"Recorded {len(recorded_sessions)} varied paths.")
    print(f"Next step: Run the Variance Benchmark using this Group ID:")
    print(f"  python scripts/experiments/run_variance_benchmark.py --group {variance_group_id}")

if __name__ == "__main__":
    asyncio.run(main())
