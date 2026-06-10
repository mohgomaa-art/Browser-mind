"""
sstg_gap_analyzer.py — Coverage audit of the Semantic State Transition Graph.

Surfaces:
  - Dead-end nodes (reachable but no outgoing edges → exploration needed)
  - Isolated nodes (never reached AND never start point)
  - Low-confidence edges (< 0.4 — under-observed, may be wrong)
  - Missing critical transitions (auth gate → dashboard never observed)
  - Coverage ratio: observed states / vocabulary size
  - Per-environment coverage gaps
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from browsermind_core.learning.state_transition_graph import (
    SemanticStateTransitionGraph,
    StateTransitionEdge,
)
from browsermind_core.ontology.semantic_state import AUTH_LEVELS, PAGE_CONTEXTS


# Critical transitions every healthy SSTG should contain.
# These are the minimum-viable navigation edges for autonomous operation.
_CRITICAL_TRANSITIONS: List[Tuple[str, str, str]] = [
    ("unauthenticated:landing",    "authenticated:dashboard",   "login"),
    ("unauthenticated:form_active","authenticated:dashboard",   "login"),
    ("unauthenticated:landing",    "unauthenticated:form_active","navigate_to_login"),
    ("authenticated:search_results","authenticated:item_listing","select_result"),
    ("authenticated:item_listing", "authenticated:checkout",    "add_to_cart"),
    ("authenticated:checkout",     "authenticated:confirmation_page","place_order"),
]


@dataclass
class GapReport:
    """Full coverage audit result."""
    total_nodes: int = 0
    total_edges: int = 0
    vocabulary_size: int = 0          # |AUTH_LEVELS| × |PAGE_CONTEXTS|
    coverage_ratio: float = 0.0       # total_nodes / vocabulary_size

    dead_ends: List[str] = field(default_factory=list)
    isolated_nodes: List[str] = field(default_factory=list)
    low_confidence_edges: List[Dict] = field(default_factory=list)
    missing_critical: List[Dict] = field(default_factory=list)
    env_gaps: Dict[str, List[str]] = field(default_factory=dict)
    high_value_gaps: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"SSTG Gap Analysis",
            f"  Nodes: {self.total_nodes} / {self.vocabulary_size} vocabulary "
            f"({self.coverage_ratio:.0%} coverage)",
            f"  Edges: {self.total_edges}",
            f"  Dead-ends: {len(self.dead_ends)}",
            f"  Isolated: {len(self.isolated_nodes)}",
            f"  Low-confidence edges: {len(self.low_confidence_edges)}",
            f"  Missing critical transitions: {len(self.missing_critical)}",
        ]
        if self.dead_ends:
            lines.append(f"  Dead-end nodes: {self.dead_ends[:5]}")
        if self.missing_critical:
            for mc in self.missing_critical[:3]:
                lines.append(f"  !! Missing: {mc['from']} → {mc['to']} via {mc['capability']}")
        return "\n".join(lines)


class SSTGGapAnalyzer:
    """
    Produces a GapReport from a SemanticStateTransitionGraph.

    Usage:
        analyzer = SSTGGapAnalyzer(sstg)
        report = analyzer.analyze()
        print(report.summary())
    """

    def __init__(
        self,
        sstg: SemanticStateTransitionGraph,
        low_confidence_threshold: float = 0.4,
    ) -> None:
        self._sstg = sstg
        self._low_conf_threshold = low_confidence_threshold

    def analyze(self) -> GapReport:
        report = GapReport()
        report.total_nodes = self._sstg.node_count()
        report.total_edges = self._sstg.edge_count()
        report.vocabulary_size = len(AUTH_LEVELS) * len(PAGE_CONTEXTS)
        report.coverage_ratio = round(
            report.total_nodes / max(report.vocabulary_size, 1), 4
        )

        # Build adjacency sets
        has_outgoing: Set[str] = set()
        has_incoming: Set[str] = set()
        env_node_map: Dict[str, Set[str]] = {}

        for e in self._sstg.edges:
            has_outgoing.add(e.from_state)
            has_incoming.add(e.to_state)
            for env in e.env_keys:
                env_node_map.setdefault(env, set()).update([e.from_state, e.to_state])

        # Dead-ends: nodes with incoming edges but no outgoing
        report.dead_ends = sorted([
            fp for fp in self._sstg.nodes
            if fp not in has_outgoing and fp in has_incoming
        ])

        # Isolated: nodes with neither incoming nor outgoing edges
        all_nodes = set(self._sstg.nodes.keys())
        report.isolated_nodes = sorted([
            fp for fp in all_nodes
            if fp not in has_outgoing and fp not in has_incoming
        ])

        # Low-confidence edges
        report.low_confidence_edges = [
            {
                "from": e.from_state,
                "to": e.to_state,
                "capability": e.capability_hash,
                "confidence": e.confidence,
                "observations": e.observation_count,
            }
            for e in self._sstg.edges
            if e.confidence < self._low_conf_threshold
        ]
        report.low_confidence_edges.sort(key=lambda x: x["confidence"])

        # Missing critical transitions
        edge_set: Set[Tuple[str, str]] = {
            (e.from_state, e.to_state) for e in self._sstg.edges
        }
        for (src, dst, cap) in _CRITICAL_TRANSITIONS:
            if (src, dst) not in edge_set:
                report.missing_critical.append({
                    "from": src,
                    "to": dst,
                    "capability": cap,
                })

        # Per-environment gaps: find envs that are missing nodes compared to total
        all_observed = set(self._sstg.nodes.keys())
        for env, env_nodes in env_node_map.items():
            missing = sorted(all_observed - env_nodes)
            if missing:
                report.env_gaps[env] = missing

        # High-value gaps: vocabulary nodes that are entirely missing from the SSTG
        vocab_fps = {
            f"{auth}:{ctx}"
            for auth in AUTH_LEVELS
            for ctx in PAGE_CONTEXTS
        }
        report.high_value_gaps = sorted(vocab_fps - all_nodes)

        return report

    def exploration_targets(self, report: GapReport, top_n: int = 10) -> List[str]:
        """
        Return a prioritised list of state fingerprints worth exploring next.

        Priority order:
          1. Missing critical transition sources
          2. Dead-end nodes
          3. High-value vocabulary gaps that are adjacent to known nodes
        """
        seen: Set[str] = set()
        targets: List[str] = []

        for mc in report.missing_critical:
            src = mc["from"]
            if src not in seen:
                targets.append(src)
                seen.add(src)

        for fp in report.dead_ends:
            if fp not in seen:
                targets.append(fp)
                seen.add(fp)
                if len(targets) >= top_n:
                    break

        # Fill remaining slots with high-value vocabulary gaps
        if len(targets) < top_n:
            # Only suggest gaps adjacent to known nodes (reachable)
            reachable = set(self._sstg.nodes.keys())
            for fp in report.high_value_gaps:
                if fp not in seen:
                    # Check if any known node has an edge to a related state
                    auth, ctx = fp.split(":", 1) if ":" in fp else (fp, "unknown")
                    if any(
                        e.to_state.startswith(auth + ":")
                        or e.to_state.endswith(":" + ctx)
                        for e in self._sstg.edges
                    ):
                        targets.append(fp)
                        seen.add(fp)
                        if len(targets) >= top_n:
                            break

        return targets[:top_n]
