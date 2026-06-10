from browsermind_core.agent.inference import FlowInferenceEngine

def test_adversarial_flow_inference():
    engine = FlowInferenceEngine()
    
    test_cases = {
        "I forgot my password": ["AUTH_FLOW"],
        "I want to access my account again": ["AUTH_FLOW"],
        "I need to publish a new model": ["PROFILE_FLOW"],
        "Find a course and enroll in it": ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
        "I want to update billing information": ["AUTH_FLOW", "SETTINGS_FLOW"],
    }
    
    for goal, expected_graph in test_cases.items():
        graph = engine.infer_flow_graph(goal)
        assert graph == expected_graph, f"Goal '{goal}' decomposed to {graph}, expected {expected_graph}"
