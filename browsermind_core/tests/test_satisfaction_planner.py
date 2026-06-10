import pytest
from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine
from browsermind_core.agent.satisfaction_planner import RequirementSatisfactionPlanner


def test_recursive_satisfaction_planning():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    planner = RequirementSatisfactionPlanner()
    
    # Goal: personal recovery requires verification_code
    goal = "Forgot my personal GitHub password"
    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    graph = graph_resolver.build_graph(goal, flows, candidates)
    
    # Run the full resolution pipeline
    bound_graph = binder.bind_graph(graph, goal)
    cap_graph = cap_engine.bind_capabilities(bound_graph)
    resolved_graph = planner.plan_satisfaction(cap_graph, goal)
    
    graph_dict = resolved_graph.to_dict()
    
    # Assert capability resolutions are present as satisfies edges
    # read_email satisfies verification_code
    assert any(e["source"] == "read_email" and e["target"] == "verification_code" and e["relation"] == "satisfies" for e in graph_dict["edges"])
    # search_email satisfies email_id (internal capability dependency)
    assert any(e["source"] == "search_email" and e["target"] == "email_id" and e["relation"] == "satisfies" for e in graph_dict["edges"])
    # read_context satisfies query
    assert any(e["source"] == "read_context" and e["target"] == "query" and e["relation"] == "satisfies" for e in graph_dict["edges"])

    # Assert dependency edges (needs)
    # read_email needs search_email (since it needs email_id)
    assert any(e["source"] == "read_email" and e["target"] == "search_email" and e["relation"] == "needs" for e in graph_dict["edges"])
    # search_email needs read_context (since it needs query)
    assert any(e["source"] == "search_email" and e["target"] == "read_context" and e["relation"] == "needs" for e in graph_dict["edges"])
    # search_email needs gmail_primary (since it needs email_account asset)
    assert any(e["source"] == "search_email" and e["target"] == "gmail_primary" and e["relation"] == "needs" for e in graph_dict["edges"])


def test_direct_session_satisfaction():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    planner = RequirementSatisfactionPlanner()
    
    # Goal: change setting (requires authenticated_session)
    goal = "Enable dark mode on settings panel"
    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    graph = graph_resolver.build_graph(goal, flows, candidates)
    
    # Run pipeline
    bound_graph = binder.bind_graph(graph, goal)
    cap_graph = cap_engine.bind_capabilities(bound_graph)
    resolved_graph = planner.plan_satisfaction(cap_graph, goal)
    
    graph_dict = resolved_graph.to_dict()
    
    # session_active directly satisfies authenticated_session
    assert any(e["source"] == "session_active" and e["target"] == "authenticated_session" and e["relation"] == "satisfies" for e in graph_dict["edges"])


def test_planning_failure_on_missing_resource():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    planner = RequirementSatisfactionPlanner()
    
    # Create a custom graph with an unsatisfiable requirement
    goal = "Forgot my password"
    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    graph = graph_resolver.build_graph(goal, flows, candidates)
    
    # Manually add an unsatisfiable requirement to the graph
    graph.add_node("impossible_requirement", "Requirement")
    
    # Bind environments (will fail if ambiguous, but let's use a clear goal context or just binder manually)
    # E.g. use "Forgot my personal GitHub password" to bind cleanly first, then add the bad requirement
    goal_good = "Forgot my personal GitHub password"
    flows_good = engine.infer_flow_graph(goal_good)
    candidates_good = engine.infer_requirement_candidates(goal_good, flows_good)
    graph_good = graph_resolver.build_graph(goal_good, flows_good, candidates_good)
    
    bound = binder.bind_graph(graph_good, goal_good)
    cap_graph = cap_engine.bind_capabilities(bound)
    
    # Now inject an impossible requirement
    cap_graph.add_node("impossible_requirement", "Requirement")
    
    # Planner should raise Exception on planning failure
    with pytest.raises(Exception) as exc_info:
        planner.plan_satisfaction(cap_graph, goal_good)
        
    assert "Planning Failure" in str(exc_info.value)
    assert "impossible_requirement" in str(exc_info.value)
