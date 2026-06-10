# scripts/experiments/p7g_satisfaction_planning.py
"""P7G: Requirement Satisfaction & Capability Composition Planning Benchmark.

Evaluates RequirementSatisfactionPlanner's ability to recursively compile capability paths
satisfying goal requirements. Reports average dependency path length, total mapped facts, and coverage.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder, AmbiguousAssetError
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine
from browsermind_core.agent.satisfaction_planner import RequirementSatisfactionPlanner

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    print(f"\n========================================================")
    print(f" P7G: REQUIREMENT SATISFACTION PLANNING BENCHMARK")
    print(f"========================================================\n")

    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    planner = RequirementSatisfactionPlanner()

    dataset = [
        {"goal": "Forgot my personal GitHub password", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my work email password", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my university portal password", "expected_outcome": "RESOLVED"},
        {"goal": "Modify my secure recovery settings", "expected_outcome": "RESOLVED"},
        {"goal": "Modify my settings configuration on local vault", "expected_outcome": "RESOLVED"},
        {"goal": "Update company password preferences", "expected_outcome": "RESOLVED"},
        {"goal": "Buy a laptop on WebArena using my personal card", "expected_outcome": "RESOLVED"},
        {"goal": "Checkout corporate cart on WebArena", "expected_outcome": "RESOLVED"},
        {"goal": "Create personal GitHub account", "expected_outcome": "RESOLVED"},
        {"goal": "Search python documentation", "expected_outcome": "RESOLVED"},
        {"goal": "Login to my corporate portal", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my password", "expected_outcome": "AMBIGUOUS"},
        {"goal": "Reset my credentials", "expected_outcome": "AMBIGUOUS"},
        {"goal": "Buy a book", "expected_outcome": "AMBIGUOUS"}
    ]

    metrics = {
        "resolved_goals": 0,
        "ambiguous_goals": 0,
        "incorrect_goals": 0,
        "total_satisfies_edges": 0,
        "total_needs_edges": 0,
        "path_lengths": []
    }

    print(f"{'Goal':<48} | {'Outcome':<10} | {'Satisfaction Dependency Chain / Path'}")
    print("-" * 120)

    for item in dataset:
        goal = item["goal"]
        expected_outcome = item["expected_outcome"]

        flows = engine.infer_flow_graph(goal)
        candidates = engine.infer_requirement_candidates(goal, flows)
        graph = resolver.build_graph(goal, flows, candidates)

        actual_outcome = ""
        is_pass = False
        chain_str = "[]"

        try:
            # 1. Environment Binding
            bound_graph = binder.bind_graph(graph, goal)
            # 2. Capability Discovery
            cap_graph = cap_engine.bind_capabilities(bound_graph)
            # 3. Satisfaction Planning
            resolved_graph = planner.plan_satisfaction(cap_graph, goal)
            
            actual_outcome = "RESOLVED"
            graph_dict = resolved_graph.to_dict()

            # Inspect satisfaction edges
            satisfies_edges = [e for e in graph_dict["edges"] if e["relation"] == "satisfies"]
            needs_edges = [e for e in graph_dict["edges"] if e["relation"] == "needs"]
            
            metrics["total_satisfies_edges"] += len(satisfies_edges)
            metrics["total_needs_edges"] += len(needs_edges)

            # Build a simple visualization string of the chains
            chains = []
            for e in satisfies_edges:
                # Trace back capability dependencies
                dependencies = [d["target"] for d in needs_edges if d["source"] == e["source"]]
                dep_str = " + ".join(dependencies)
                if dep_str:
                    chains.append(f"({dep_str}) -> {e['source']} -> satisfies -> {e['target']}")
                else:
                    chains.append(f"{e['source']} -> satisfies -> {e['target']}")

            chain_str = " | ".join(chains)
            metrics["path_lengths"].append(len(satisfies_edges) + len(needs_edges))

            is_pass = (expected_outcome == "RESOLVED")
            if is_pass:
                metrics["resolved_goals"] += 1

        except AmbiguousAssetError:
            actual_outcome = "AMBIGUOUS"
            is_pass = (expected_outcome == "AMBIGUOUS")
            if is_pass:
                metrics["ambiguous_goals"] += 1
            else:
                metrics["incorrect_goals"] += 1
        except Exception as e:
            actual_outcome = f"ERROR: {type(e).__name__}"
            metrics["incorrect_goals"] += 1

        status_str = "PASS" if is_pass else "FAIL"
        print(f"{goal:<48} | {actual_outcome:<10} | {chain_str}")
        if not is_pass:
            print(f"  [WARNING] Failed expected alignment: {expected_outcome} vs {actual_outcome}")

    print("-" * 120)
    print("\n========================================================")
    print(" P7G SATISFACTION PLANNING COVERAGE SUMMARY")
    print("========================================================")
    print(f"Successfully Resolved Goals    : {metrics['resolved_goals']}")
    print(f"Correctly Flagged Ambiguous    : {metrics['ambiguous_goals']}")
    print(f"Total Satisfies Edges Compiled : {metrics['total_satisfies_edges']}")
    print(f"Total Needs Edges Compiled     : {metrics['total_needs_edges']}")
    
    avg_path = sum(metrics["path_lengths"]) / len(metrics["path_lengths"]) if metrics["path_lengths"] else 0
    print(f"Average Satisfaction Path Size : {avg_path:.2f} edges")
    print(f"Incorrect / Failed Plannings   : {metrics['incorrect_goals']}")
    print("========================================================\n")

    if metrics["incorrect_goals"] == 0:
        print("VERDICT: SUCCESS. Planner resolved all dependency pathways and composition chains correctly.")
        sys.exit(0)
    else:
        print("VERDICT: FAILED. Planning path mismatch errors encountered.")
        sys.exit(1)


if __name__ == "__main__":
    main()
