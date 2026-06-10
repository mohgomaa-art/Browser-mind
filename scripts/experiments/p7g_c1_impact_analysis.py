"""
P7G-C1: Decision Impact Analysis

Simulates 200 decision scenarios where multiple valid paths exist
for a given requirement. Tests how often the Lexicographic
Preference Model overrides the default (unranked) graph search.
"""
import sys
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browsermind_core.ontology.asset import AssetGraph, StateClass
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.path_utility import PathUtilityScorer

def build_randomized_graph(num_paths: int) -> tuple[AssetGraph, str]:
    """
    Builds a synthetic graph with `num_paths` converging on a shared requirement context.
    Randomly assigns path lengths and target state classes.
    Returns the graph and the target requirement label.
    """
    graph = AssetGraph()
    req_name = "simulated_requirement"
    
    # We will define some mock Target States that map to Observation vs Availability
    target_states = []
    
    for i in range(num_paths):
        # 1. Randomly decide if this path guarantees Availability or Observation
        is_availability = random.choice([True, False])
        
        # 2. Randomly decide path length (1 to 4 steps)
        length = random.randint(1, 4)
        
        state_class = StateClass.AVAILABILITY if is_availability else StateClass.OBSERVATION
        final_state = f"state_target_{i}_{state_class.value}"
        target_states.append(final_state)
        
        # Build the capability chain backward
        current_state = final_state
        for step in range(length):
            cap_name = f"cap_path_{i}_step_{step}"
            prev_state = f"state_path_{i}_step_{step}" if step < length - 1 else None
            
            consumes = [prev_state] if prev_state else []
            produces = [current_state]
            
            graph.add_node(cap_name, "Capability", {
                "inputs": ["mock_asset"],
                "outputs": [],
                "consumes_state": consumes,
                "produces_state": produces
            })
            current_state = prev_state

        graph.add_node("mock_asset", "AssetType")
        
    return graph, target_states


def run_analysis(num_tasks: int = 200):
    print("======================================================")
    print(f"  P7G-C1: Decision Impact Analysis ({num_tasks} Tasks)")
    print("======================================================")

    planner = BackwardStatePlanner()
    scorer = PathUtilityScorer()
    
    stats = {
        "total_tasks": num_tasks,
        "ranking_changed_decisions": 0,
        "availability_wins": 0,
        "observation_wins": 0,
        "ties": 0,
        "total_paths_evaluated": 0,
        "total_availability_paths": 0,
        "total_observation_paths": 0
    }

    # Since PathUtilityScorer usually reads from RequirementStateRegistry,
    # and our states are dynamic, we must monkey-patch `_evaluate_state_quality`
    # temporarily to read from the state string itself.
    def mock_evaluate_state_quality(target_state: str) -> StateClass:
        if "availability" in target_state:
            return StateClass.AVAILABILITY
        return StateClass.OBSERVATION
        
    scorer._evaluate_state_quality = mock_evaluate_state_quality

    for task_idx in range(num_tasks):
        # Generate 2 to 5 competing paths
        num_paths = random.randint(2, 5)
        graph, target_states = build_randomized_graph(num_paths)
        
        all_paths = []
        path_to_state = {}
        
        for t_state in target_states:
            res = planner.check_reachability(t_state, graph)
            if res["reachable"]:
                for p in res["candidate_paths"]:
                    if tuple(p) not in all_paths:
                        all_paths.append(tuple(p))
                        path_to_state[tuple(p)] = t_state
                        
                        # Accumulate path stats
                        if "availability" in t_state:
                            stats["total_availability_paths"] += 1
                        else:
                            stats["total_observation_paths"] += 1
                            
        stats["total_paths_evaluated"] += len(all_paths)
        
        if not all_paths:
            continue
            
        # Simulate Unranked (Insertion / DFS Order)
        unranked_top = all_paths[0]
        
        # Ranked Order
        scored_paths = []
        for p in all_paths:
            t_state = path_to_state[p]
            score = scorer.score_path(list(p), t_state, graph)
            scored_paths.append((p, score))
            
        scored_paths.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)
        ranked_top = scored_paths[0][0]
        ranked_score = scored_paths[0][1]
        
        if unranked_top != ranked_top:
            stats["ranking_changed_decisions"] += 1
            
        # Track winning class
        if ranked_score.state_quality == StateClass.AVAILABILITY:
            stats["availability_wins"] += 1
        else:
            stats["observation_wins"] += 1
            
    # Print Report
    print("\n[IMPACT METRICS]")
    print(f"  Tasks Processed             : {stats['total_tasks']}")
    print(f"  Decisions Changed           : {stats['ranking_changed_decisions']}")
    print(f"  Impact Ratio (Decision Flip): {(stats['ranking_changed_decisions']/stats['total_tasks'])*100:.1f}%")
    print("\n[OUTCOME METRICS]")
    print(f"  Availability Wins           : {stats['availability_wins']}")
    print(f"  Observation Wins            : {stats['observation_wins']}")
    print(f"  Ties (Arbitrary)            : {stats['ties']}")
    print("\n[GRAPH METRICS]")
    print(f"  Total Paths Evaluated       : {stats['total_paths_evaluated']}")
    print(f"  Availability Paths          : {stats['total_availability_paths']} ({(stats['total_availability_paths']/stats['total_paths_evaluated'])*100:.1f}%)")
    print(f"  Observation Paths           : {stats['total_observation_paths']} ({(stats['total_observation_paths']/stats['total_paths_evaluated'])*100:.1f}%)")
    
    # Save JSON report locally
    import json
    with open("p7g_c1_report.json", "w") as f:
        json.dump(stats, f, indent=2)
        
if __name__ == "__main__":
    run_analysis(200)
