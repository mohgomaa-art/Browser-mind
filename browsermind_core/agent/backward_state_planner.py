"""Backward State Reachability Search (P7G-B2)."""

from typing import Dict, List, Set, Optional, Tuple
from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.path_utility import PathUtilityScorer

class CapabilityNode:
    """Lightweight view of a Capability as extracted from the AssetGraph."""
    def __init__(self, name: str, inputs: List[str], outputs: List[str], consumes_state: List[str], produces_state: List[str]):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.consumes_state = consumes_state
        self.produces_state = produces_state

class BackwardStatePlanner:
    """
    Determines if a target state is reachable by traversing capabilities backwards.
    1. Backwards DFS on `consumes_state` / `produces_state` to form structural capability paths.
    2. Forward pass over the candidate path to ensure data `inputs` are satisfied by assets or previous `outputs`.
    """

    def check_reachability(self, target_state: str, graph: AssetGraph) -> Dict:
        """Checks if a target state can be reached from the available graph assets."""
        capabilities = self._extract_capabilities(graph)
        state_index = self._build_state_index(capabilities)
        asset_provided = self._extract_asset_tokens(graph)
        cap_by_name = {c.name: c for c in capabilities}

        missing_states = set()

        # Step 1: Backward search to find candidate structural paths (Enumerate All)
        # A path is a list of capability names, ordered from END to START
        structural_paths = self._find_paths_backward(target_state, state_index, cap_by_name, set(), missing_states)

        valid_candidate_paths = []
        all_missing_assets = set()

        # Step 2: Forward data verification (Independent Pass)
        for backward_path in structural_paths:
            # Reorder from START to END
            forward_path = list(reversed(backward_path))
            missing_assets = self._verify_data_dependencies(forward_path, cap_by_name, asset_provided)
            
            if not missing_assets:
                valid_candidate_paths.append(forward_path)
            else:
                all_missing_assets.update(missing_assets)

        # Step 3: Path Ranking (P7G-B3a)
        # Score and sort paths deterministically using Lexicographic Ordering
        scorer = PathUtilityScorer()
        scored_paths = []
        for path in valid_candidate_paths:
            score = scorer.score_path(path, target_state, graph)
            scored_paths.append((path, score))
            
        # Sort descending by the Scorer's explicit Ranking Policy
        scored_paths.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)

        if scored_paths:
            return {
                "target_state": target_state,
                "reachable": True,
                "candidate_paths": [p[0] for p in scored_paths],
                "path_scores": [p[1] for p in scored_paths],
                "missing_states": [],
                "missing_assets": []
            }
        else:
            return {
                "target_state": target_state,
                "reachable": False,
                "candidate_paths": [],
                "missing_states": list(missing_states),
                "missing_assets": list(all_missing_assets)
            }

    # ------------------------------------------------------------------
    # Graph Extraction
    # ------------------------------------------------------------------

    def _extract_capabilities(self, graph: AssetGraph) -> List[CapabilityNode]:
        caps: List[CapabilityNode] = []
        for node_name, node_data in graph.nodes.items():
            if node_data["type"] == "Capability":
                meta = node_data.get("metadata", {})
                caps.append(CapabilityNode(
                    name=node_name,
                    inputs=list(meta.get("inputs", [])),
                    outputs=list(meta.get("outputs", [])),
                    consumes_state=list(meta.get("consumes_state", [])),
                    produces_state=list(meta.get("produces_state", [])),
                ))
        return caps

    def _build_state_index(self, capabilities: List[CapabilityNode]) -> Dict[str, List[str]]:
        """Maps each produces_state token -> list of capability names that produce it."""
        index: Dict[str, List[str]] = {}
        for cap in capabilities:
            for state in cap.produces_state:
                index.setdefault(state, []).append(cap.name)
        return index

    def _extract_asset_tokens(self, graph: AssetGraph) -> Set[str]:
        provided: Set[str] = set()
        for node_name, node_data in graph.nodes.items():
            if node_data["type"] in ("AssetInstance", "AssetType"):
                provided.add(node_name)
                meta = node_data.get("metadata", {})
                at = meta.get("asset_type")
                if at:
                    provided.add(at)
        return provided

    # ------------------------------------------------------------------
    # Pathfinding Algorithms
    # ------------------------------------------------------------------

    def _find_paths_backward(self, current_state: str, state_index: Dict[str, List[str]], cap_by_name: Dict[str, CapabilityNode], visited_states: Set[str], missing_states: Set[str]) -> List[List[str]]:
        """
        Recursively finds paths backwards using ONLY structural state relationships.
        Returns a list of paths, ordered from END (target) to START (no dependencies).
        """
        if current_state in visited_states:
            return [] # Cycle detected
            
        producers = state_index.get(current_state, [])
        if not producers:
            missing_states.add(current_state)
            return []

        visited_states.add(current_state)
        all_paths = []

        for producer_name in producers:
            producer = cap_by_name[producer_name]
            
            if not producer.consumes_state:
                # Base case: this capability requires no prior state
                all_paths.append([producer_name])
            else:
                # Recursive case: this capability requires prior states
                # (Assuming linear structural chains for now. Compound preconditions (AND)
                # can be supported later by splitting and merging paths)
                req_state = producer.consumes_state[0]
                sub_paths = self._find_paths_backward(req_state, state_index, cap_by_name, visited_states, missing_states)
                for sp in sub_paths:
                    # prepend producer_name to the backward path
                    all_paths.append([producer_name] + sp)
                    
        visited_states.remove(current_state)
        return all_paths

    def _verify_data_dependencies(self, path: List[str], cap_by_name: Dict[str, CapabilityNode], asset_provided: Set[str]) -> List[str]:
        """
        Forward Verification Pass. Walks the structural path from start to end 
        and verifies that all data inputs are satisfied.
        """
        available_data = set(asset_provided)
        missing = []
        for cap_name in path:
            cap = cap_by_name[cap_name]
            for inp in cap.inputs:
                if inp not in available_data:
                    if inp not in missing:
                        missing.append(inp)
            for out in cap.outputs:
                available_data.add(out)
        return missing
