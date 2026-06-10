"""
Experimental: Goal Synthesizer
Uses an Oracle LLM to generate user goals. Preserved for future generative coverage.
Do not use in the primary deterministic pipeline.
"""
from typing import Dict, Any

class GoalSynthesizer:
    def __init__(self, oracle_llm_client):
        self.llm = oracle_llm_client
        
    def synthesize_interaction_goal(self, page_context: str, target: Dict[str, Any]) -> str:
        name = target.get('name', '')
        return f"Experimental interact with {name}"

    def synthesize_extraction_goal(self, page_context: str, target: Dict[str, Any]) -> str:
        desc = target.get('description', 'data')
        return f"Experimental extract {desc}"
