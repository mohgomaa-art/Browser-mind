from browsermind_core.agent.inference import FlowInferenceEngine

def test_flow_graph_decomposition():
    engine = FlowInferenceEngine()
    
    test_cases = {
        "Buy a laptop under $1000": [
            "SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"
        ],
        "Update my GitHub profile picture": [
            "AUTH_FLOW", "PROFILE_FLOW"
        ],
        "Login and enable dark mode": [
            "AUTH_FLOW", "SETTINGS_FLOW"
        ],
        "Find playwright and read reviews": [
            "SEARCH_FLOW", "DISCOVERY_FLOW"
        ]
    }
    
    for goal, expected_graph in test_cases.items():
        graph = engine.infer_flow_graph(goal)
        assert graph == expected_graph, f"Goal '{goal}' decomposed to {graph}, expected {expected_graph}"
