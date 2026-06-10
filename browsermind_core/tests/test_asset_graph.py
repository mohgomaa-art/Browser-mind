from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver

def test_asset_graph_compilation():
    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()
    
    # Target: Reset GitHub Password
    goal = "Forgot my GitHub password"
    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    
    # Compile Asset Graph
    graph = resolver.build_graph(goal, flows, candidates)
    graph_dict = graph.to_dict()
    
    # Assert nodes are added correctly
    assert goal in graph_dict["nodes"]
    assert "AUTH_FLOW" in graph_dict["nodes"]
    assert "email_or_username" in graph_dict["nodes"]
    assert "email_account" in graph_dict["nodes"]
    
    # Assert edges map flow -> requirement -> asset_type
    edges = graph_dict["edges"]
    assert any(e["source"] == goal and e["target"] == "AUTH_FLOW" for e in edges)
    assert any(e["source"] == "AUTH_FLOW" and e["target"] == "email_or_username" for e in edges)
    assert any(e["source"] == "email_or_username" and e["target"] == "email_account" for e in edges)
