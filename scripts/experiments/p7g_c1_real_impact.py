"""
P7G-C1: Real Decision Impact Analysis

Evaluates actual requirements from the RequirementStateRegistry against
real candidate paths to see if Lexicographic Ranking changes the outcome.
No random generators, no mock registries.
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.path_utility import PathUtilityScorer
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry


def build_real_decision_graph() -> AssetGraph:
    """Builds a graph with concrete paths for the tested requirements."""
    graph = AssetGraph()
    
    # Global dummy assets so paths are satisfied
    assets = ["email_account", "goal_context", "credential_asset", "payment_asset", "profile_asset"]
    for a in assets:
        graph.add_node(a, "AssetType")

    # Path for `email.opened` (OBSERVATION)
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

    # Path for `vault.otp_generated` and `vault.credentials_unlocked` (AVAILABILITY)
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

    # Path for `wallet.billing_info_loaded` (AVAILABILITY)
    graph.add_node("load_wallet", "Capability", {
        "inputs": ["payment_asset"],
        "outputs": ["wallet_id"],
        "consumes_state": [],
        "produces_state": ["wallet.active"]
    })
    graph.add_node("read_billing_info", "Capability", {
        "inputs": ["wallet_id"],
        "outputs": ["billing_data"],
        "consumes_state": ["wallet.active"],
        "produces_state": ["wallet.billing_info_loaded"]
    })

    # Path for `profile.loaded` (OBSERVATION)
    graph.add_node("navigate_profile", "Capability", {
        "inputs": ["profile_asset"],
        "outputs": ["profile_id"],
        "consumes_state": [],
        "produces_state": ["profile.active"]
    })
    graph.add_node("read_profile", "Capability", {
        "inputs": ["profile_id"],
        "outputs": ["profile_data"],
        "consumes_state": ["profile.active"],
        "produces_state": ["profile.loaded"]
    })
    
    # Path for `checkout.payment_processed` (AVAILABILITY)
    graph.add_node("charge_payment", "Capability", {
        "inputs": ["payment_asset"],
        "outputs": ["receipt"],
        "consumes_state": [],
        "produces_state": ["checkout.payment_processed"]
    })

    return graph


def run_real_impact_analysis():
    planner = BackwardStatePlanner()
    scorer = PathUtilityScorer()
    registry = RequirementStateRegistry()
    graph = build_real_decision_graph()

    requirements = [
        "verification_code", 
        "current_password", 
        "billing_address", 
        "payment_method", 
        "email"
    ]
    
    results = []

    for req in requirements:
        target_states = registry.get_target_states(req)
        
        # Collect all structurally reachable paths across all target states
        all_paths = []
        path_state_map = {}
        for t_state in target_states:
            res = planner.check_reachability(t_state, graph)
            if res["reachable"]:
                for p in res["candidate_paths"]:
                    if tuple(p) not in all_paths:
                        all_paths.append(tuple(p))
                        path_state_map[tuple(p)] = t_state
                        
        if not all_paths:
            continue
            
        # Unranked Decision (first found in insertion order / standard DFS)
        unranked_top = all_paths[0]
        unranked_state = path_state_map[unranked_top]
        
        # Ranked Decision
        scored_paths = []
        for p in all_paths:
            t_state = path_state_map[p]
            score = scorer.score_path(list(p), t_state, graph)
            scored_paths.append((p, score))
            
        # Lexicographic sort
        scored_paths.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)
        ranked_top = scored_paths[0][0]
        ranked_state = path_state_map[ranked_top]
        
        changed = unranked_top != ranked_top
        
        results.append({
            "requirement": req,
            "paths_available": len(all_paths),
            "unranked": {
                "path": " -> ".join(unranked_top),
                "reaches_state": unranked_state
            },
            "ranked": {
                "path": " -> ".join(ranked_top),
                "reaches_state": ranked_state
            },
            "changed": changed
        })

    print(json.dumps(results, indent=2))
    
    # Save to report artifact
    with open("p7g_c1_real_decision_impact.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    run_real_impact_analysis()
