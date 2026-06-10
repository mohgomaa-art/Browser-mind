"""
Unit tests for Requirement State Registry (P7G-B1 Option A).
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry
from browsermind_core.agent.asset_graph import AssetGraphResolver

def test_registry_mapping():
    registry = RequirementStateRegistry()
    
    # Test 1: verification_code -> target execution states
    targets = registry.get_target_states("verification_code")
    assert "email.opened" in targets
    assert "vault.otp_generated" in targets
    
    # Test 2: current_password -> target execution states
    targets = registry.get_target_states("current_password")
    assert "vault.credentials_unlocked" in targets


def test_asset_graph_integration():
    resolver = AssetGraphResolver()
    
    goal = "Reset my GitHub password via email"
    flows = ["AUTH_FLOW", "SETTINGS_FLOW"]
    candidates = ["verification_code", "current_password", "authenticated_session"]
    
    graph = resolver.build_graph(goal, flows, candidates)
    
    # Verify that Requirement nodes have the target_states metadata attached
    assert "verification_code" in graph.nodes
    assert "email.opened" in graph.nodes["verification_code"]["metadata"]["target_states"]
    
    assert "current_password" in graph.nodes
    assert "vault.credentials_unlocked" in graph.nodes["current_password"]["metadata"]["target_states"]
    
    assert "authenticated_session" in graph.nodes
    assert graph.nodes["authenticated_session"]["metadata"]["target_states"] == []


def main():
    print("Running P7G-B1 Unit Tests...")
    test_registry_mapping()
    test_asset_graph_integration()
    print("[PASS] Requirement State Registry mapping validated (Option A).")
    print("[PASS] AssetGraph Integration validated (Option A).")

if __name__ == "__main__":
    main()
