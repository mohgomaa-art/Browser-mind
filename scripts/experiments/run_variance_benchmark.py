"""Human Variance Benchmark Runner (v2).

Replays a group of varied human demonstrations, collects the final states,
and calculates the Action, Workflow, State Path, and State Achievement distances.
Extracts Invariant Capabilities (Always Present vs Sometimes Present).
"""
import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import statistics

import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site
from browsermind_core.experiments.variance_metrics import (
    action_distance, workflow_distance, state_path_distance, state_achievement
)

async def run_benchmark(target: str, group_id: str):
    harness = ReplayExperimentHarness(headless=True)
    site = get_site(target)
    
    # 1. Find all templates for this variance group
    prefix = f"var_{target}_{group_id[:8]}"
    templates_meta = [t for t in harness.kernel.workflow_store.list_templates() if t["name"].startswith(prefix)]
    
    if not templates_meta:
        print(f"No templates found for group {group_id}")
        return
        
    print(f"\n========================================================")
    print(f" HUMAN VARIANCE BENCHMARK (v2)")
    print(f" Target: {site.label} ({site.key})")
    print(f" Group ID: {group_id}")
    print(f" Found {len(templates_meta)} varied demonstrations.")
    print(f"========================================================\n")

    runs_data = []

    for t_meta in templates_meta:
        t_name = t_meta["name"]
        template = harness.load_template(t_name)
        demo_id = template.metadata.get("compiled_from")
        
        session = None
        if demo_id:
            import uuid
            session = harness.demo_repo.load(uuid.UUID(demo_id))
            
        print(f"Replaying {t_name}...")
        try:
            # Replay the compiled workflow to get the verified end state
            result = await harness.run_full(target, template_name=t_name, skip_record=True)
        except Exception as e:
            print(f"  ERROR replaying {t_name}: {e}")
            continue
            
        final_url = ""
        inferred_state = "UNKNOWN"
        
        # P4C Evidence
        if result.state_inference:
            inferred_state = result.state_inference.get("inferred_state", "UNKNOWN")
            evidence = result.state_inference.get("evidence", {})
            final_url = evidence.get("url_pattern", "")
            
        runs_data.append({
            "name": t_name,
            "demo_actions": [a.model_dump() for a in session.actions] if session else [],
            "workflow_steps": template.steps,
            "final_url": final_url,
            "inferred_state": inferred_state,
            "replay_success": result.replay_success
        })
        
    n = len(runs_data)
    if n == 0:
        return
        
    # 2. Compute pairwise distances
    action_matrix = [[0.0]*n for _ in range(n)]
    workflow_matrix = [[0.0]*n for _ in range(n)]
    state_path_matrix = [[0.0]*n for _ in range(n)]
    state_achieve_matrix = [[0.0]*n for _ in range(n)]
    
    # 3. Invariant Discovery
    # Collect set of semantic steps for each run: "role|name"
    run_capabilities = []
    
    for i in range(n):
        r1 = runs_data[i]
        
        caps = set()
        for s in r1["workflow_steps"]:
            if s.get("action_type") not in ("session", "navigate"):
                role = s.get("target_role", "")
                name = s.get("target_name", "")
                caps.add(f"{role}|{name}")
        run_capabilities.append(caps)
        
        for j in range(n):
            if i == j:
                continue
            r2 = runs_data[j]
            
            action_matrix[i][j] = action_distance(r1["demo_actions"], r2["demo_actions"])
            workflow_matrix[i][j] = workflow_distance(r1["workflow_steps"], r2["workflow_steps"])
            state_path_matrix[i][j] = state_path_distance(r1["workflow_steps"], r2["workflow_steps"])
            state_achieve_matrix[i][j] = state_achievement(r1["inferred_state"], r2["inferred_state"], r1["final_url"], r2["final_url"])

    def avg_distance(matrix):
        vals = [matrix[i][j] for i in range(n) for j in range(n) if i < j]
        return statistics.mean(vals) if vals else 0.0

    avg_action = avg_distance(action_matrix)
    avg_workflow = avg_distance(workflow_matrix)
    avg_state_path = avg_distance(state_path_matrix)
    avg_state_achieve = avg_distance(state_achieve_matrix)

    # Invariant Discovery Math
    all_caps = set.union(*run_capabilities) if run_capabilities else set()
    always_present = []
    sometimes_present = []
    
    for cap in all_caps:
        count = sum(1 for c_set in run_capabilities if cap in c_set)
        if count == n:
            always_present.append(cap)
        else:
            sometimes_present.append(f"{cap} (in {count}/{n})")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "variance" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "group_id": group_id,
        "target": target,
        "demonstrations": n,
        "averages": {
            "action_distance": avg_action,
            "workflow_distance": avg_workflow,
            "state_path_distance": avg_state_path,
            "state_achievement_distance": avg_state_achieve
        },
        "invariants": {
            "always_present": sorted(always_present),
            "sometimes_present": sorted(sometimes_present)
        },
        "matrices": {
            "action": action_matrix,
            "workflow": workflow_matrix,
            "state_path": state_path_matrix,
            "state_achievement": state_achieve_matrix
        }
    }
    
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n========================================================")
    print(f" VARIANCE BENCHMARK RESULTS")
    print(f"========================================================")
    print(f"--------------------------------------------------------")
    print(f" Action Distance      : {avg_action:.2%}  (High = Good)")
    print(f" Workflow Distance    : {avg_workflow:.2%}  (High = Good)")
    print(f" State Path Distance  : {avg_state_path:.2%}  (High = Varied Trajectories)")
    print(f" State Achievement    : {avg_state_achieve:.2%}   (Low = Goals Converged)")
    print(f"--------------------------------------------------------")
    print(f"\n INVARIANT DISCOVERY:")
    print(f" Always Present (Core Capabilities):")
    for cap in sorted(always_present):
        print(f"   - {cap}")
        
    print(f"\n Sometimes Present (Variance Noise):")
    for cap in sorted(sometimes_present):
        print(f"   - {cap}")
        
    print(f"\n--------------------------------------------------------")
    
    if avg_workflow > 0.2 and avg_state_achieve < 0.1:
        print(" => [ONTOLOGY VALIDATED] Diverse paths successfully collapsed into identical states.")
    elif avg_state_achieve > 0.3:
        print(" => [ONTOLOGY FAILED] Human paths diverged into fundamentally different final states.")
    else:
        print(" => [INCONCLUSIVE] Variance is too low to prove mathematical collapse.")
        
    print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Human Variance Benchmark v2")
    parser.add_argument("--target", default="github", help="Site key (default: github)")
    parser.add_argument("--group", required=True, help="Variance Group ID (from record_variance.py)")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args.target, args.group))
