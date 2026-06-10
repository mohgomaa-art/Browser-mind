import pytest
from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder, AmbiguousAssetError

def test_context_aware_environment_binding():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    
    # Scenario 1: Personal Context
    goal_personal = "Forgot my personal GitHub password"
    flows = engine.infer_flow_graph(goal_personal)
    candidates = engine.infer_requirement_candidates(goal_personal, flows)
    graph_personal = graph_resolver.build_graph(goal_personal, flows, candidates)
    
    # Bind
    bound_graph_personal = binder.bind_graph(graph_personal, goal_personal)
    personal_dict = bound_graph_personal.to_dict()
    
    # Assert nodes are bound to Gmail
    assert "primary_user" in personal_dict["nodes"]
    assert personal_dict["nodes"]["primary_user"]["type"] == "Persona"
    assert "gmail_primary" in personal_dict["nodes"]
    assert "gmail" in personal_dict["nodes"]
    
    # Assert relations
    assert any(e["source"] == "email_account" and e["target"] == "gmail_primary" and e["relation"] == "bound_to" for e in personal_dict["edges"])
    assert any(e["source"] == "primary_user" and e["target"] == "gmail_primary" and e["relation"] == "owns" for e in personal_dict["edges"])
    assert any(e["source"] == "gmail_primary" and e["target"] == "gmail" and e["relation"] == "hosted_in" for e in personal_dict["edges"])
    
    # Scenario 2: Work Context
    goal_work = "Forgot my work email password"
    flows_work = engine.infer_flow_graph(goal_work)
    candidates_work = engine.infer_requirement_candidates(goal_work, flows_work)
    graph_work = graph_resolver.build_graph(goal_work, flows_work, candidates_work)
    
    # Bind
    bound_graph_work = binder.bind_graph(graph_work, goal_work)
    work_dict = bound_graph_work.to_dict()
    
    # Assert nodes are bound to Outlook
    assert "primary_user" in work_dict["nodes"]
    assert "outlook_work" in work_dict["nodes"]
    assert "outlook" in work_dict["nodes"]
    
    # Assert relations
    assert any(e["source"] == "email_account" and e["target"] == "outlook_work" and e["relation"] == "bound_to" for e in work_dict["edges"])
    assert any(e["source"] == "primary_user" and e["target"] == "outlook_work" and e["relation"] == "owns" for e in work_dict["edges"])
    assert any(e["source"] == "outlook_work" and e["target"] == "outlook" and e["relation"] == "hosted_in" for e in work_dict["edges"])

def test_ambiguity_detection():
    engine = FlowInferenceEngine()
    graph_resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    
    # Scenario 3: Ambiguous context
    # Multiple email instances (gmail_primary, gmail_school, outlook_work) exist but the goal has no tags to distinguish them.
    goal_ambiguous = "Forgot my password"
    flows = engine.infer_flow_graph(goal_ambiguous)
    candidates = engine.infer_requirement_candidates(goal_ambiguous, flows)
    graph = graph_resolver.build_graph(goal_ambiguous, flows, candidates)
    
    with pytest.raises(AmbiguousAssetError) as exc_info:
        binder.bind_graph(graph, goal_ambiguous)
        
    assert exc_info.value.asset_type == "email_account"
    assert "gmail_primary" in exc_info.value.candidates
    assert "outlook_work" in exc_info.value.candidates

    # Verify that the UNRESOLVED node is part of the graph state
    graph_dict = graph.to_dict()
    unresolved_node = "UNRESOLVED_email_account"
    assert unresolved_node in graph_dict["nodes"]
    assert graph_dict["nodes"][unresolved_node]["type"] == "UNRESOLVED"
    assert graph_dict["nodes"][unresolved_node]["metadata"]["status"] == "ambiguous"
    assert "gmail_primary" in graph_dict["nodes"][unresolved_node]["metadata"]["candidates"]
    assert any(e["source"] == "email_account" and e["target"] == unresolved_node and e["relation"] == "bound_to" for e in graph_dict["edges"])
