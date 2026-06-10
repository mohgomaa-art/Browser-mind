"""P5A.1 & P5A.2 — Invariant Compiler & Partial Order Graphs.

Transforms a set of DemonstrationSessions into an InvariantGraph
using canonical Intents, support scores, and strict precedence logic.
"""
from typing import List, Dict, Set
from collections import defaultdict

from browsermind_core.ontology.p1_schemas import WorkflowTemplate
from browsermind_core.representation.p5_schemas import InvariantGraph
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

class InvariantCompiler:
    """Compiles N demonstrations into 1 Invariant Graph (DAG)."""

    def __init__(self, variant_threshold: float = 0.2, collapse_level: int = 0):
        self.variant_threshold = variant_threshold
        self.collapse_level = collapse_level

    def compile_from_templates(self, goal_id: str, templates: List[WorkflowTemplate]) -> InvariantGraph:
        """
        Extracts canonical intents, calculates support scores, and builds a Partial Order Graph.
        """
        N = len(templates)
        if N == 0:
            return InvariantGraph(goal_id=goal_id, demonstrations_count=0)
            
        intent_counts: Dict[str, int] = defaultdict(int)
        run_sequences: List[List[str]] = []
        normalizer = PrimitiveNormalizer(collapse_level=self.collapse_level)

        
        for template in templates:
            seq = []
            seen_in_run = set()
            for step in template.steps:
                action_type = step.get("action_type")
                if action_type in ("session", "navigate"):
                    continue
                    
                intent = normalizer.normalize(
                    action_type=action_type,
                    target_role=step.get("target_role", ""),
                    target_name=step.get("target_name", "")
                )
                
                # If an intent happens multiple times in a run (e.g. typing multiple characters),
                # we only record its first occurrence for the DAG.
                if intent not in seen_in_run:
                    seen_in_run.add(intent)
                    seq.append(intent)
                    intent_counts[intent] += 1
            
            run_sequences.append(seq)
                
        # 1. Classify and Calculate Support Scores
        graph = InvariantGraph(goal_id=goal_id, demonstrations_count=N)
        
        for intent, count in intent_counts.items():
            score = count / N
            graph.support_scores[intent] = round(score, 3)
            
            if score == 1.0:
                graph.invariants.append(intent)
            elif score >= self.variant_threshold:
                graph.variants.append(intent)
            else:
                graph.noise.append(intent)
                
        graph.invariants.sort()
        graph.variants.sort(key=lambda i: graph.support_scores[i], reverse=True)
        graph.noise.sort(key=lambda i: graph.support_scores[i], reverse=True)
        
        # 2. Extract Partial Order Graph (DAG)
        # We only care about precedence between invariants for the core DAG.
        # Rule: A precedes B IF AND ONLY IF A appears before B in EVERY run where they BOTH appear.
        
        # First, gather all pairs that appear together in at least 1 run
        pair_precedence_counts = defaultdict(lambda: {"A_before_B": 0, "B_before_A": 0})
        
        # Only build DAG for invariants + strong variants to keep it clean
        dag_nodes = set(graph.invariants + graph.variants)
        
        for seq in run_sequences:
            seq_len = len(seq)
            for i in range(seq_len):
                node_a = seq[i]
                if node_a not in dag_nodes: continue
                for j in range(i + 1, seq_len):
                    node_b = seq[j]
                    if node_b not in dag_nodes: continue
                    # A occurred before B
                    pair_precedence_counts[(node_a, node_b)]["A_before_B"] += 1
                    pair_precedence_counts[(node_b, node_a)]["B_before_A"] += 1

        edges = set()
        for node_a in dag_nodes:
            for node_b in dag_nodes:
                if node_a == node_b: continue
                stats = pair_precedence_counts[(node_a, node_b)]
                # If A always occurred before B (A_before_B > 0 and B_before_A == 0)
                if stats["A_before_B"] > 0 and stats["B_before_A"] == 0:
                    edges.add((node_a, node_b))
                    
        # Transitive Reduction: Remove edges A->C if A->B and B->C exist.
        # This keeps the DAG minimal and readable.
        reduced_edges = set(edges)
        for (a, b) in edges:
            for (c, d) in edges:
                if b == c: # a -> b -> d implies a -> d
                    if (a, d) in reduced_edges:
                        reduced_edges.remove((a, d))
                        
        graph.partial_order_edges = sorted(list(reduced_edges))
        
        return graph
