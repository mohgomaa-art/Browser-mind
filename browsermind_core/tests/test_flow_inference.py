from browsermind_core.agent.inference import FlowInferenceEngine

def test_flow_inference_mapping():
    engine = FlowInferenceEngine()
    
    # Test cases mapping user goals to flow domains
    test_cases = {
        "Find microsoft/playwright": "SEARCH_FLOW",
        "Search python documentation": "SEARCH_FLOW",
        "Go to the Wikipedia main page": "NAVIGATION_FLOW",
        "Navigate to github settings": "NAVIGATION_FLOW",
        "Read latest news articles": "DISCOVERY_FLOW",
        "Filter products by XL size": "FILTERING_FLOW",
        "Pay for my shopping order": "CHECKOUT_FLOW",
        "Enable dark mode in my settings": "SETTINGS_FLOW",
        "Change my profile picture": "PROFILE_FLOW",
        "Update my bio profile details": "PROFILE_FLOW",
        "Login to my GitHub account": "AUTH_FLOW",
        "Sign out of the session": "AUTH_FLOW",
    }
    
    for goal, expected_flow in test_cases.items():
        flow, confidence = engine.infer_flow(goal)
        assert flow == expected_flow, f"Goal '{goal}' inferred as '{flow}', expected '{expected_flow}'"
        assert confidence > 0.0
