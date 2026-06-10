# browsermind_core/agent/capability_dependency_planner.py
"""
Capability Dependency Planner (P7G-A)

Answers one question only:
    "What capabilities must exist before this capability can run?"

This is a pure graph problem.
- No SATISFACTION_MAP
- No semantic aliases
- No content interpretation
- No assumption about what an output "means"

A capability B depends on capability A if:
    any output of A matches any input of B
    (exact string match only — no inference)

The planner builds a directed dependency graph over all Capability nodes
found in the AssetGraph and reports:
    - dependency_paths  : list of (provider_cap, consumer_cap) pairs
    - unsatisfied_inputs: inputs that no capability in the graph produces
    - cycles_detected   : True if any cycle exists in the dependency graph
    - max_depth         : longest chain found
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from browsermind_core.ontology.asset import AssetGraph


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class CapabilityNode:
    """Lightweight view of a Capability as extracted from the AssetGraph."""
    name: str
    inputs: List[str]
    outputs: List[str]
    consumes_state: List[str]
    produces_state: List[str]


@dataclass
class DependencyPlanResult:
    """Output of the Capability Dependency Planner."""
    # (provider_capability, consumer_capability) — A must run before B
    dependency_paths: List[Tuple[str, str]] = field(default_factory=list)
    # states that no capability in the graph can produce
    unsatisfied_states: List[str] = field(default_factory=list)
    # inputs (assets/data) that are not provided in the graph
    unsatisfied_inputs: List[str] = field(default_factory=list)
    # True if the dependency graph contains a cycle
    cycles_detected: bool = False
    # Longest dependency chain (number of hops)
    max_depth: int = 0
    # Per-capability: which capabilities it directly depends on
    adjacency: Dict[str, List[str]] = field(default_factory=dict)

    def summary(self) -> Dict:
        return {
            "dependency_paths": len(self.dependency_paths),
            "unsatisfied_states": len(self.unsatisfied_states),
            "unsatisfied_states_detail": self.unsatisfied_states,
            "unsatisfied_inputs": len(self.unsatisfied_inputs),
            "unsatisfied_inputs_detail": self.unsatisfied_inputs,
            "cycles_detected": self.cycles_detected,
            "max_depth": self.max_depth,
        }


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class CapabilityDependencyPlanner:
    """
    Builds a Capability Dependency Graph from the AssetGraph.

    Algorithm:
        1. Extract all Capability nodes from the AssetGraph.
        2. For every capability C, for every required state S in C.consumes_state:
               find every capability P whose produces_state contains S  ->  P must precede C
        3. Detect cycles using DFS.
        4. Compute max chain depth via topological ordering.
        5. Record missing required states (unsatisfied_states) and missing data/assets (unsatisfied_inputs).

    This planner does NOT:
        - interpret what an output token means
        - map outputs to requirement categories
        - perform any semantic reasoning
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(self, graph: AssetGraph) -> DependencyPlanResult:
        """Compute the capability dependency plan for the given AssetGraph."""
        capabilities = self._extract_capabilities(graph)
        state_index = self._build_state_index(capabilities)
        output_index = self._build_output_index(capabilities)
        asset_provided = self._extract_asset_tokens(graph)
        return self._compute_plan(capabilities, state_index, output_index, asset_provided)

    # ------------------------------------------------------------------
    # Step 1: Extract capabilities
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

    # ------------------------------------------------------------------
    # Step 2: Build output index
    # ------------------------------------------------------------------

    def _build_state_index(
        self, capabilities: List[CapabilityNode]
    ) -> Dict[str, List[str]]:
        """Maps each produces_state token -> list of capability names that produce it."""
        index: Dict[str, List[str]] = {}
        for cap in capabilities:
            for state in cap.produces_state:
                index.setdefault(state, []).append(cap.name)
        return index

    def _build_output_index(
        self, capabilities: List[CapabilityNode]
    ) -> Dict[str, List[str]]:
        """Maps each output token -> list of capability names that produce it."""
        index: Dict[str, List[str]] = {}
        for cap in capabilities:
            for out in cap.outputs:
                index.setdefault(out, []).append(cap.name)
        return index

    def _extract_asset_tokens(self, graph: AssetGraph) -> Set[str]:
        """
        Returns the set of tokens that are considered 'externally provided':
        names of AssetInstance and AssetType nodes.

        A capability input that matches one of these tokens is satisfied
        by an owned asset, not by another capability.  It should NOT appear
        in unsatisfied_inputs.
        """
        provided: Set[str] = set()
        for node_name, node_data in graph.nodes.items():
            if node_data["type"] in ("AssetInstance", "AssetType"):
                provided.add(node_name)
                # Also add the asset_type field so capability inputs like
                # 'email_account' (type token, not instance name) are covered.
                meta = node_data.get("metadata", {})
                at = meta.get("asset_type")
                if at:
                    provided.add(at)
        return provided

    # ------------------------------------------------------------------
    # Step 3: Compute the dependency plan
    # ------------------------------------------------------------------

    def _compute_plan(
        self,
        capabilities: List[CapabilityNode],
        state_index: Dict[str, List[str]],
        output_index: Dict[str, List[str]],
        asset_provided: Set[str],
    ) -> DependencyPlanResult:
        result = DependencyPlanResult()

        # All states produced by capabilities in the graph
        all_produced_states: Set[str] = set(state_index.keys())
        
        # All data/assets provided by outputs or external assets
        all_provided_inputs: Set[str] = set(output_index.keys()) | asset_provided

        # Adjacency: cap_name -> list of caps that MUST run before it
        adjacency: Dict[str, List[str]] = {c.name: [] for c in capabilities}

        for cap in capabilities:
            # 1. State Dependencies (Capability -> Capability)
            for req_state in cap.consumes_state:
                providers = state_index.get(req_state, [])
                if providers:
                    for provider in providers:
                        if provider != cap.name:  # skip self-loops
                            pair = (provider, cap.name)
                            if pair not in result.dependency_paths:
                                result.dependency_paths.append(pair)
                            if provider not in adjacency[cap.name]:
                                adjacency[cap.name].append(provider)
                elif req_state not in all_produced_states:
                    if req_state not in result.unsatisfied_states:
                        result.unsatisfied_states.append(req_state)

            # 2. Input/Data Verification (Data dependencies, do not build structural DAG edges here)
            for inp in cap.inputs:
                if inp not in all_provided_inputs:
                    if inp not in result.unsatisfied_inputs:
                        result.unsatisfied_inputs.append(inp)

        result.adjacency = adjacency

        # Cycle detection + max depth via DFS
        result.cycles_detected, result.max_depth = self._analyse_dag(adjacency)

        return result

    # ------------------------------------------------------------------
    # Cycle detection + depth computation (DFS)
    # ------------------------------------------------------------------

    def _analyse_dag(
        self, adjacency: Dict[str, List[str]]
    ) -> Tuple[bool, int]:
        """Returns (cycle_found, max_depth).

        max_depth is the number of hops in the longest dependency chain.
        A chain A -> B -> C has max_depth = 2.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in adjacency}
        # longest_path[n] = max hops from any leaf to n (including self)
        longest_path: Dict[str, int] = {n: 0 for n in adjacency}
        cycle_found = False

        def dfs(node: str) -> int:
            nonlocal cycle_found
            if color[node] == BLACK:
                return longest_path[node]
            color[node] = GREY
            best = 0
            for predecessor in adjacency.get(node, []):
                if color[predecessor] == GREY:
                    cycle_found = True
                else:
                    child_depth = dfs(predecessor)
                    best = max(best, child_depth + 1)
            color[node] = BLACK
            longest_path[node] = best
            return best

        overall_max = 0
        for node in list(adjacency.keys()):
            if color[node] == WHITE:
                d = dfs(node)
                overall_max = max(overall_max, d)

        return cycle_found, overall_max
