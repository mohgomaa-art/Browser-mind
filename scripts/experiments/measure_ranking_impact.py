"""
Measures Decision Flips introduced by Lexicographic Ranking.
Runs backward state planner with and without ranking logic
and counts how many top-preferred paths actually changed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.ontology.asset import AssetGraph, StateClass
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry
from browsermind_core.agent.path_utility import PathUtilityScorer

def build_multi_path_graph() -> AssetGraph:
    """Graph where multiple paths exist, forcing the ranker to choose."""
    graph = AssetGraph()
    graph.add_node("email_account", "AssetType")
    graph.add_node("goal_context", "AssetType")
    graph.add_node("credential_asset", "AssetType")
    graph.add_node("payment_asset", "AssetType")

    # Path 1: Email (OBSERVATION)
    graph.add_node("search_email", "Capability", {
        "inputs": ["email_account", "goal_context"],
        "outputs": ["email_id"],
        "consumes_state": [],
        "produces_state": ["email.selected"]
    })
    graph.add_node("read_email", "Capability", {
        "inputs": ["email_id"],
        "outputs": ["email_content"],
        "consumes_state": ["email.selected"],
        "produces_state": ["email.opened"]
    })

    # Path 2: Vault (AVAILABILITY)
    graph.add_node("retrieve_credential", "Capability", {
        "inputs": ["credential_asset"],
        "outputs": ["credential_id"],
        "consumes_state": [],
        "produces_state": ["vault.credentials_unlocked"]
    })
    graph.add_node("generate_otp", "Capability", {
        "inputs": ["credential_id"],
        "outputs": ["otp_code"],
        "consumes_state": ["vault.credentials_unlocked"],
        "produces_state": ["vault.otp_generated"]
    })

    # Path 3: Payment Wallet (AVAILABILITY)
    graph.add_node("charge_payment", "Capability", {
        "inputs": ["payment_asset"],
        "outputs": ["receipt"],
        "consumes_state": [],
        "produces_state": ["checkout.payment_processed"]
    })

    return graph


def measure_flips():
    print("======================================================")
    print("  Lexicographic Ranking — Decision Impact Analysis")
    print("======================================================")

    graph = build_multi_path_graph()
    planner = BackwardStatePlanner()
    scorer = PathUtilityScorer()
    registry = RequirementStateRegistry()

    requirements_to_test = ["verification_code", "payment_method"]
    total_decisions = len(requirements_to_test)
    decisions_changed = 0

    for req in requirements_to_test:
        target_states = registry.get_target_states(req)
        
        all_paths = []
        for t_state in target_states:
            res = planner.check_reachability(t_state, graph)
            if res["reachable"]:
                for p in res["candidate_paths"]:
                    if p not in all_paths:
                        all_paths.append(p)
                        
        if not all_paths:
            continue
            
        # 1. Unranked (Insertion Order / DFS order)
        # In a real environment, BFS/DFS would just return the first reachable path found
        unranked_top = all_paths[0] 

        # 2. Ranked (Lexicographic Ordering)
        scored_paths = [(p, scorer.score_path(p, target_states[0], graph)) for p in all_paths]
        # Re-score properly against their actual target states
        properly_scored = []
        for p in all_paths:
            # Find which target state this path produces
            prod_state = None
            for cap_name in reversed(p):
                cap_data = graph.nodes.get(cap_name)
                if cap_data and "produces_state" in cap_data.get("metadata", {}):
                    for ts in cap_data["metadata"]["produces_state"]:
                        if ts in target_states:
                            prod_state = ts
                            break
                if prod_state: break
                
            score = scorer.score_path(p, prod_state, graph)
            properly_scored.append((p, score))

        properly_scored.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)
        ranked_top = properly_scored[0][0]
        
        print(f"\nRequirement: {req}")
        print(f"  Unranked Top Path : {' -> '.join(unranked_top)}")
        print(f"  Ranked Top Path   : {' -> '.join(ranked_top)}")

        if unranked_top != ranked_top:
            print("  [FLIP DETECTED] Lexicographic ranking altered the planner's decision.")
            decisions_changed += 1
        else:
            print("  [NO CHANGE] Ranked path aligns with insertion order.")

    print("\n======================================================")
    print("  IMPACT SUMMARY")
    print("======================================================")
    print(f"  Total Decisions Tested : {total_decisions}")
    print(f"  Decisions Changed      : {decisions_changed}")
    print(f"  Impact Ratio           : {(decisions_changed/total_decisions)*100:.1f}%")
    
    if decisions_changed > 0:
        print("\n  CONCLUSION: The Preference Model is actively overriding graph insertion defaults.")
    else:
        print("\n  CONCLUSION: The Preference Model currently has no effect over default BFS/DFS.")

if __name__ == "__main__":
    measure_flips()
