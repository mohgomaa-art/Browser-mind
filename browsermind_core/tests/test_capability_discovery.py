import pytest
from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine


def test_capability_discovery_baseline_and_overrides():
    engine = CapabilityDiscoveryEngine()
    
    # Test case 1: Gmail (inherits email_client baseline + overrides manage_labels)
    gmail_caps = engine.discover_capabilities("gmail", "email_client")
    gmail_names = [c.name for c in gmail_caps]
    assert len(gmail_caps) == 3
    assert "search_email" in gmail_names
    assert "read_email" in gmail_names
    assert "manage_labels" in gmail_names
    
    # Test case 2: Outlook (inherits email_client baseline + overrides manage_folders)
    outlook_caps = engine.discover_capabilities("outlook", "email_client")
    outlook_names = [c.name for c in outlook_caps]
    assert len(outlook_caps) == 3
    assert "search_email" in outlook_names
    assert "read_email" in outlook_names
    assert "manage_folders" in outlook_names
    
    # Test case 3: Proton (inherits email_client baseline, no overrides)
    proton_caps = engine.discover_capabilities("proton", "email_client")
    proton_names = [c.name for c in proton_caps]
    assert len(proton_caps) == 2
    assert "search_email" in proton_names
    assert "read_email" in proton_names
    assert "manage_labels" not in proton_names
    assert "manage_folders" not in proton_names

    # Test case 4: OnePassword (inherits secrets_manager baseline + overrides generate_otp)
    op_caps = engine.discover_capabilities("onepassword", "secrets_manager")
    op_names = [c.name for c in op_caps]
    assert len(op_caps) == 2
    assert "retrieve_credential" in op_names
    assert "generate_otp" in op_names


def test_capability_no_workflow_leakage():
    engine = CapabilityDiscoveryEngine()
    
    forbidden_terms = ["verification_code", "password_reset", "login", "authentication", "recover_account", "mfa"]
    
    # Check all registered capabilities across all kinds and overrides
    all_caps = []
    for caps in engine.baseline_capabilities.values():
        all_caps.extend(caps)
    for caps in engine.overrides.values():
        all_caps.extend(caps)
        
    for cap in all_caps:
        # Check name and outputs
        for term in forbidden_terms:
            assert term not in cap.name.lower(), f"Capability name '{cap.name}' leaks workflow semantic: {term}"
            for out in cap.outputs:
                assert term not in out.lower(), f"Capability output '{out}' in '{cap.name}' leaks workflow semantic: {term}"


def test_capability_graph_binding():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    
    # Goal: Personal github password recovery maps to gmail environment
    goal = "Forgot my personal GitHub password"
    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    graph = graph_resolver.build_graph(goal, flows, candidates)
    
    # 1. Bind Environments
    bound_graph = binder.bind_graph(graph, goal)
    
    # 2. Bind Capabilities
    fully_bound = cap_engine.bind_capabilities(bound_graph)
    graph_dict = fully_bound.to_dict()
    
    # gmail Environment should support its baseline and overridden capabilities
    assert "search_email" in graph_dict["nodes"]
    assert "read_email" in graph_dict["nodes"]
    assert "manage_labels" in graph_dict["nodes"]
    assert graph_dict["nodes"]["read_email"]["type"] == "Capability"
    
    # Check edge relations
    assert any(e["source"] == "gmail" and e["target"] == "read_email" and e["relation"] == "supports" for e in graph_dict["edges"])
    assert any(e["source"] == "gmail" and e["target"] == "manage_labels" and e["relation"] == "supports" for e in graph_dict["edges"])
