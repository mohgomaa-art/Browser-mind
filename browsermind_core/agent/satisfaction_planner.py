# browsermind_core/agent/satisfaction_planner.py
"""Requirement Satisfaction Planner — Compiles capability dependency chains dynamically to satisfy goal requirements."""
from typing import Dict, List, Optional, Set, Tuple
from browsermind_core.ontology.asset import Capability, AssetGraph


# Semantic satisfaction mappings: capability outputs and asset statuses -> requirement categories
SATISFACTION_MAP = {
    "email_content": ["verification_code", "email_body"],
    "password": ["credentials", "current_password", "password"],
    "username": ["credentials", "username", "email_or_username"],
    "payment_status": ["payment_method"],
    "profile_data": ["user_metadata", "billing_address", "email", "username"],
    "query_parameters": ["query", "search_query", "filter_criteria", "target_url"],
    "session_token": ["authenticated_session"],
    "session_active": ["authenticated_session"],
    "email_account": ["email_or_username", "email"],
    "identity_profile": ["email", "username"],
    "goal_context": ["search_query", "filter_criteria", "target_url"]
}

CAPABILITY_ONLY_REQUIREMENTS = {"query"}


class RequirementSatisfactionPlanner:
    """Recursively resolves requirements to Capability dependency chains inside the AssetGraph."""

    def __init__(self):
        self.satisfaction_map = SATISFACTION_MAP

    def _is_satisfied_by(self, output: str, requirement: str) -> bool:
        """Helper to check if a capability output satisfies a given requirement name."""
        reqs = self.satisfaction_map.get(output, [])
        return requirement in reqs or output == requirement

    def plan_satisfaction(self, graph: AssetGraph, goal: str) -> AssetGraph:
        """Scans Requirement nodes in the graph, recursively plans capability chains, and adds resolution edges."""
        # 1. Identify all requirements in the graph
        requirements = [
            node_name for node_name, node_data in graph.nodes.items()
            if node_data["type"] == "Requirement"
        ]

        # 2. Track resolved requirements and capabilities to prevent infinite recursion
        resolved: Set[str] = set()

        def resolve_req(req_name: str, path: List[str]) -> bool:
            if req_name in resolved:
                return True
            if req_name in path:
                # Detect dependency loop/cycle
                return False

            # Special case 1: Check if requirement is satisfied directly by a bound AssetInstance
            # Find derived AssetType edge: req_name -> derived_from -> asset_type
            derived_asset_type = None
            for edge in graph.edges:
                if edge[0] == req_name and edge[2] == "derived_from":
                    derived_asset_type = edge[1]
                    break
                    
            if derived_asset_type:
                # Check if asset_type is bound to an AssetInstance
                bound_instance = None
                for edge in graph.edges:
                    if edge[0] == derived_asset_type and edge[2] == "bound_to":
                        bound_instance = edge[1]
                        break
                        
                if bound_instance:
                    # Verify if it satisfies req_name directly (via mapping registry)
                    if self._is_satisfied_by(derived_asset_type, req_name) or self._is_satisfied_by(bound_instance, req_name):
                        graph.add_edge(bound_instance, req_name, "satisfies")
                        resolved.add(req_name)
                        return True

            # Special case 2: authenticated_session satisfied directly by active session instance
            if req_name == "authenticated_session" and "session_active" in graph.nodes:
                graph.add_edge("session_active", "authenticated_session", "satisfies")
                resolved.add(req_name)
                return True

            # Find candidates: Capabilities in the graph whose outputs can satisfy the requirement
            candidates: List[Tuple[str, str, Capability]] = [] # (env_name, cap_name, Capability)

            # Traverse the graph to find supported Capabilities
            for node_name, node_data in graph.nodes.items():
                if node_data["type"] == "Environment":
                    # Find all capabilities supported by this environment
                    supported_caps = [
                        edge[1] for edge in graph.edges
                        if edge[0] == node_name and edge[2] == "supports"
                    ]
                    for cap_name in supported_caps:
                        cap_data = graph.nodes[cap_name]
                        cap_obj = Capability(
                            name=cap_name,
                            inputs=cap_data["metadata"].get("inputs", []),
                            outputs=cap_data["metadata"].get("outputs", []),
                            description=cap_data["metadata"].get("description")
                        )
                        # Check if any output of the capability satisfies the requirement
                        for out in cap_obj.outputs:
                            if self._is_satisfied_by(out, req_name):
                                candidates.append((node_name, cap_name, cap_obj))
                                break

            # Try to satisfy requirements using candidate capabilities
            for env_name, cap_name, cap in candidates:
                # Resolve each input of the capability
                inputs_resolved = True
                input_edges = []

                for inp in cap.inputs:
                    if inp == "goal_context":
                        graph.add_edge(cap_name, "goal_parameters", "needs")
                        continue

                    # Check if inp is an AssetType or AssetInstance owned by Persona
                    is_owned_asset = False
                    
                    # 1. Is it a direct AssetInstance owned by persona?
                    if inp in graph.nodes and graph.nodes[inp]["type"] == "AssetInstance":
                        is_owned_asset = True
                        input_edges.append((cap_name, inp, "needs"))
                    else:
                        # 2. Is there an AssetInstance of AssetType 'inp' owned by the persona?
                        # E.g. inp is 'email_account', which is bound to 'gmail_primary'
                        for edge in graph.edges:
                            if edge[0] == inp and edge[2] == "bound_to":
                                bound_instance = edge[1]
                                is_owned_asset = True
                                input_edges.append((cap_name, bound_instance, "needs"))
                                break

                    if not is_owned_asset:
                        if inp in CAPABILITY_ONLY_REQUIREMENTS and inp not in graph.nodes:
                            graph.add_node(inp, "Requirement")
                        # If not an owned asset, it is a sub-requirement!
                        # Recursively resolve it
                        if resolve_req(inp, path + [req_name]):
                            # Find which capability satisfies inp and connect it
                            for edge in graph.edges:
                                if edge[1] == inp and edge[2] == "satisfies":
                                    input_edges.append((cap_name, edge[0], "needs"))
                                    break
                            else:
                                # Fallback connection to the capability satisfying it
                                input_edges.append((cap_name, inp, "needs"))
                        else:
                            inputs_resolved = False
                            break

                if inputs_resolved:
                    # All inputs satisfied! Add edges and mark as resolved
                    for src, tgt, rel in input_edges:
                        graph.add_edge(src, tgt, rel)
                    graph.add_edge(cap_name, req_name, "satisfies")
                    resolved.add(req_name)
                    return True

            return False

        for req in requirements:
            if not resolve_req(req, []):
                raise Exception(f"Planning Failure: Requirement '{req}' cannot be satisfied by any capability chain in the graph.")

        return graph
