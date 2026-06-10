from browsermind_core.agent.inference import FlowInferenceEngine

def test_requirements_extraction_scenarios():
    engine = FlowInferenceEngine()
    
    # Scenario 1: Password change
    res1 = engine.infer_goal_state("Change my GitHub password")
    assert "AUTH_FLOW" in res1["flows"]
    assert "SETTINGS_FLOW" in res1["flows"]
    assert "authenticated_session" in res1["requirement_candidates"]
    assert "current_password" in res1["requirement_candidates"]
    
    # Scenario 2: Registration
    res2 = engine.infer_goal_state("Create GitHub account")
    assert "AUTH_FLOW" in res2["flows"]
    assert "PROFILE_FLOW" in res2["flows"]
    assert "email" in res2["requirement_candidates"]
    assert "username" in res2["requirement_candidates"]
    assert "password" in res2["requirement_candidates"]
    assert "authenticated_session" not in res2["requirement_candidates"]
    
    # Scenario 3: Purchase / Checkout
    res3 = engine.infer_goal_state("Buy a laptop under $1000")
    assert "CHECKOUT_FLOW" in res3["flows"]
    assert "payment_method" in res3["requirement_candidates"]
    assert "billing_address" in res3["requirement_candidates"]
    
    # Scenario 4: Password recovery
    res4 = engine.infer_goal_state("I forgot my password for reddit")
    assert "email_or_username" in res4["requirement_candidates"]
    assert "credentials" not in res4["requirement_candidates"]
    
    # Scenario 5: Login
    res5 = engine.infer_goal_state("Login to my upwork account")
    assert "credentials" in res5["requirement_candidates"]
    
    # Scenario 6: Search
    res6 = engine.infer_goal_state("Search for courses")
    assert "search_query" in res6["requirement_candidates"]
    
    # Scenario 7: Navigation
    res7 = engine.infer_goal_state("Go to the upwork home page")
    assert "target_url" in res7["requirement_candidates"]
    
    # Scenario 8: Filtering
    res8 = engine.infer_goal_state("Filter products by size M")
    assert "filter_criteria" in res8["requirement_candidates"]
