from browsermind_core.agent.inference import FlowInferenceEngine

def test_generalization_lexicon():
    engine = FlowInferenceEngine()
    
    # Layer A (Easy)
    assert engine.infer_flow_graph("search python docs") == ["SEARCH_FLOW"]
    assert engine.infer_flow_graph("login to my account") == ["AUTH_FLOW"]
    
    # Layer B (Paraphrases)
    assert engine.infer_flow_graph("acquire a laptop") == ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"]
    assert engine.infer_flow_graph("obtain product data") == ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"]
    
    # Layer C (Indirect Intent)
    assert engine.infer_flow_graph("I forgot my password") == ["AUTH_FLOW"]
    assert engine.infer_flow_graph("I can't get into my account") == ["AUTH_FLOW"]
    assert engine.infer_flow_graph("I lost access to my profile") == ["AUTH_FLOW", "PROFILE_FLOW"]
    assert engine.infer_flow_graph("I need to complete my order") == ["CHECKOUT_FLOW"]
    assert engine.infer_flow_graph("I want to personalize my page") == ["AUTH_FLOW", "PROFILE_FLOW"]
    
    # Layer D (Multi-intent)
    assert engine.infer_flow_graph("Find a course and enroll in it") == ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"]
    assert engine.infer_flow_graph("Change my password and update my email") == ["AUTH_FLOW", "SETTINGS_FLOW"]
