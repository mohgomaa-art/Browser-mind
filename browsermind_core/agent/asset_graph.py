# browsermind_core/agent/asset_graph.py
"""Asset Graph Resolver — Maps requirement candidates to abstract asset types."""
from typing import Any, Dict, List, Optional
from browsermind_core.ontology.asset import AssetType, AssetGraph
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry


class AssetGraphResolver:
    """Resolves flows and requirements to abstract Asset Types."""

    def __init__(self):
        # Mapping requirement candidates to abstract AssetTypes
        self.asset_mapping: Dict[str, AssetType] = {
            "authenticated_session": AssetType(name="session_token", description="Session credentials and active tokens"),
            "verification_code": AssetType(name="email_account", description="Access to verification/MFA email codes"),
            "email_or_username": AssetType(name="email_account", description="Access to recovery/support email address"),
            "credentials": AssetType(name="credential_asset", description="Credentials storing usernames and passwords"),
            "current_password": AssetType(name="credential_asset", description="Credentials storing usernames and passwords"),
            "password": AssetType(name="credential_asset", description="Password vault for authentication"),
            "email": AssetType(name="identity_profile", description="User personal profile data"),
            "username": AssetType(name="identity_profile", description="User personal profile data"),
            "payment_method": AssetType(name="payment_asset", description="Payment card and token wallets"),
            "billing_address": AssetType(name="payment_asset", description="Payment billing address details"),
            "search_query": AssetType(name="goal_context", description="Direct search input details"),
            "target_url": AssetType(name="goal_context", description="Destination URL of navigation"),
            "filter_criteria": AssetType(name="goal_context", description="Filter constraints details")
        }
        self.state_registry = RequirementStateRegistry()

    def build_graph(self, goal: str, flows: List[str], candidates: List[str]) -> AssetGraph:
        """Compiles a complete AssetGraph for a goal, flows, and candidate requirements."""
        graph = AssetGraph()
        
        # Add Goal Node
        graph.add_node(goal, "Goal")
        
        # Add Flow Nodes and connect to Goal
        for flow in flows:
            graph.add_node(flow, "Flow")
            graph.add_edge(goal, flow, "decomposes_to")
            
        # Map each candidate requirement to its asset type and connect it
        for candidate in candidates:
            target_states = self.state_registry.get_target_states(candidate)
            graph.add_node(candidate, "Requirement", {
                "target_states": target_states
            })
            
            # Connect candidate requirement to the corresponding flows
            for flow in flows:
                if flow == "SETTINGS_FLOW" and candidate in ["authenticated_session", "current_password"]:
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "AUTH_FLOW" and candidate in ["credentials", "email_or_username", "verification_code"]:
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "CHECKOUT_FLOW" and candidate in ["payment_method", "billing_address"]:
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "SEARCH_FLOW" and candidate == "search_query":
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "NAVIGATION_FLOW" and candidate == "target_url":
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "FILTERING_FLOW" and candidate == "filter_criteria":
                    graph.add_edge(flow, candidate, "requires")
                elif flow == "PROFILE_FLOW" and candidate in ["email", "username", "password"]:
                    graph.add_edge(flow, candidate, "requires")
                    
            # Map requirement candidate to AssetType
            asset_type = self.asset_mapping.get(candidate)
            if asset_type:
                graph.add_node(asset_type.name, "AssetType", {
                    "description": asset_type.description
                })
                graph.add_edge(candidate, asset_type.name, "derived_from")
                
        return graph
