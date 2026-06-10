"""
Unit tests for Backward State Reachability Search (P7G-B2).
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner

def build_test_graph() -> AssetGraph:
    graph = AssetGraph()
    # Add external assets
    graph.add_node("email_account", "AssetType")
    graph.add_node("goal_context", "AssetType")
    
    # Add Capabilities
    # search_email: consumes nothing, produces email.selected, requires email_account, goal_context
    graph.add_node("search_email", "Capability", {
        "inputs": ["email_account", "goal_context"],
        "outputs": ["email_id"],
        "consumes_state": [],
        "produces_state": ["email.selected"]
    })
    
    # read_email: consumes email.selected, produces email.opened, requires email_id
    graph.add_node("read_email", "Capability", {
        "inputs": ["email_id"],
        "outputs": ["email_content"],
        "consumes_state": ["email.selected"],
        "produces_state": ["email.opened"]
    })

    # retrieve_credential: consumes nothing, produces vault.credentials_unlocked, requires credential_asset
    graph.add_node("retrieve_credential", "Capability", {
        "inputs": ["credential_asset"],
        "outputs": ["credential_id"],
        "consumes_state": [],
        "produces_state": ["vault.credentials_unlocked"]
    })

    # generate_otp: consumes vault.credentials_unlocked, produces vault.otp_generated, requires credential_id
    graph.add_node("generate_otp", "Capability", {
        "inputs": ["credential_id"],
        "outputs": ["otp_code"],
        "consumes_state": ["vault.credentials_unlocked"],
        "produces_state": ["vault.otp_generated"]
    })
    return graph

def test_reachable_path():
    graph = build_test_graph()
    planner = BackwardStatePlanner()
    
    result = planner.check_reachability("email.opened", graph)
    
    assert result["reachable"] is True
    assert len(result["candidate_paths"]) == 1
    assert result["candidate_paths"][0] == ["search_email", "read_email"]

def test_missing_asset():
    graph = build_test_graph()
    planner = BackwardStatePlanner()
    
    # Target state requires credential_asset which is missing from the graph
    result = planner.check_reachability("vault.otp_generated", graph)
    
    assert result["reachable"] is False
    assert len(result["candidate_paths"]) == 0
    assert "credential_asset" in result["missing_assets"]
    assert len(result["missing_states"]) == 0

def test_missing_state():
    graph = build_test_graph()
    planner = BackwardStatePlanner()
    
    # Target state is not produced by any capability
    result = planner.check_reachability("unknown_state", graph)
    
    assert result["reachable"] is False
    assert "unknown_state" in result["missing_states"]

def main():
    print("Running P7G-B2 Unit Tests...")
    test_reachable_path()
    print("[PASS] Reachable path (Backward Search + Forward Verification) works.")
    
    test_missing_asset()
    print("[PASS] Missing asset correctly blocks execution during Forward Verification.")
    
    test_missing_state()
    print("[PASS] Missing state correctly halts Structural Search.")

if __name__ == "__main__":
    main()
