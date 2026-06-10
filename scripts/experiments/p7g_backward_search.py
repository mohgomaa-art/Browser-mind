"""
P7G-B3: Path Ranking Benchmark

Evaluates the full pipeline with strict separation between:
  - binding_failures  : asset ambiguity (EnvironmentBinder layer)
  - planning_failures : missing states or data (BackwardStatePlanner layer)

Sorts and displays ALL candidate paths per requirement according to the 
Planning Utility Function (State Quality > Trust > Permissions > Length).
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.path_utility import PathUtilityScorer

GOALS = [
    "Reset my GitHub password via email",
    "Log in to Slack using 2FA",
    "Sign in to my corporate VPN with 2FA",
    "Buy a laptop on WebArena using my personal card",
    "Checkout corporate cart on WebArena",
    "Update my shipping address on Amazon",
    "Change my display name on GitHub",
    "Find the cheapest flight from Cairo to Dubai",
    "Search for Python books on O'Reilly",
    "Book a hotel in Paris and pay with my work card",
    "Download my invoice from last month"
]

def main():
    print("==================================================================")
    print("  P7G-B2.5  Path Enumeration Benchmark")
    print("==================================================================")

    inference  = FlowInferenceEngine()
    resolver   = AssetGraphResolver()
    binder     = EnvironmentBinder()
    discovery  = CapabilityDiscoveryEngine()
    registry   = RequirementStateRegistry()
    planner    = BackwardStatePlanner()
    scorer     = PathUtilityScorer()

    total_goals      = len(GOALS)
    goals_reachable  = 0
    goals_unreachable= 0

    # Strictly separate counters:
    total_binding_failures  = 0   # EnvironmentBinder could not resolve asset (ambiguous)
    total_planning_failures = 0   # Planner could not find any path (missing state or data)
    errors                  = 0

    total_paths_found = 0

    for goal in GOALS:
        print(f"\nGoal: '{goal}'")
        try:
            # 1. Inference
            inf_result = inference.infer_goal_state(goal)
            flows      = inf_result["flows"]
            candidates = inf_result["requirement_candidates"]

            # 2. Asset Graph Construction
            graph = resolver.build_graph(goal, flows, candidates)

            # 3. Environment Binding
            graph = binder.bind_graph(graph, goal)

            # 4. Capability Discovery
            graph = discovery.bind_capabilities(graph)

            # 5. Enumerate ALL paths for each requirement
            goal_fully_reachable = True

            for candidate in candidates:
                target_states = registry.get_target_states(candidate)
                if not target_states:
                    continue

                # Check if binding failed for this candidate (UNRESOLVED node in graph)
                # Find the AssetType node for this candidate
                binding_failed = False
                for n, d in graph.nodes.items():
                    if d["type"] == "UNRESOLVED":
                        meta = d.get("metadata", {})
                        if meta.get("asset_type") in [
                            graph.nodes.get(e_dst, {}).get("metadata", {}).get("derived_from", "")
                            for _, e_dst, _ in graph.edges if _ == candidate
                        ]:
                            binding_failed = True

                # Simpler check: look for UNRESOLVED nodes in the graph at all
                unresolved_nodes = [n for n, d in graph.nodes.items() if d["type"] == "UNRESOLVED"]

                all_candidate_paths = []
                all_binding_failures  = []
                all_planning_failures = []

                for t_state in target_states:
                    res = planner.check_reachability(t_state, graph)
                    if res["reachable"]:
                        for path, score in zip(res["candidate_paths"], res["path_scores"]):
                            if (path, score) not in all_candidate_paths:
                                all_candidate_paths.append((path, score))
                    else:
                        all_binding_failures.extend(res.get("missing_states", []))
                        all_planning_failures.extend(res.get("missing_assets", []))

                if all_candidate_paths:
                    # Sort globally using Lexicographic Ordering
                    all_candidate_paths.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)
                    total_paths_found += len(all_candidate_paths)
                    
                    print(f"  [{candidate}] {len(all_candidate_paths)} path(s) found:")
                    for i, (path, score) in enumerate(all_candidate_paths):
                        paths_str = " -> ".join(path)
                        print(f"    {i+1}. {paths_str}  {score}")
                else:
                    goal_fully_reachable = False
                    # Determine root cause
                    if unresolved_nodes:
                        asset_types = [graph.nodes[n].get("metadata", {}).get("asset_type", n) for n in unresolved_nodes]
                        print(f"  [{candidate}] BINDING FAILURE (ambiguous: {asset_types})")
                        total_binding_failures += 1
                    elif all_binding_failures:
                        print(f"  [{candidate}] PLANNING FAILURE (missing states: {sorted(set(all_binding_failures))})")
                        total_planning_failures += 1
                    elif all_planning_failures:
                        print(f"  [{candidate}] PLANNING FAILURE (missing assets: {sorted(set(all_planning_failures))})")
                        total_planning_failures += 1
                    else:
                        print(f"  [{candidate}] UNREACHABLE (unknown reason)")
                        total_planning_failures += 1

            if goal_fully_reachable:
                goals_reachable += 1
            else:
                goals_unreachable += 1

        except Exception as e:
            errors += 1
            print(f"  ERROR: {e}")
            traceback.print_exc()

    print("\n==================================================================")
    print("  AGGREGATE SUMMARY")
    print("==================================================================")
    print(f"  total_goals           : {total_goals}")
    print(f"  goals_reachable       : {goals_reachable}")
    print(f"  goals_unreachable     : {goals_unreachable}")
    print(f"  ---")
    print(f"  binding_failures      : {total_binding_failures}   (EnvironmentBinder)")
    print(f"  planning_failures     : {total_planning_failures}  (BackwardStatePlanner)")
    print(f"  total_paths_found     : {total_paths_found}")
    print(f"  errors                : {errors}")
    print()
    print("  Health check:")
    if errors == 0:
        print("  [PASS] No exceptions raised.")
    else:
        print(f"  [WARN] {errors} goal(s) raised exceptions.")
    total_processed = goals_reachable + goals_unreachable
    pct = round(goals_reachable / total_processed * 100, 1) if total_processed else 0
    print(f"  [INFO] {goals_reachable}/{total_processed} resolvable goals fully reachable ({pct}%).")


if __name__ == "__main__":
    main()
