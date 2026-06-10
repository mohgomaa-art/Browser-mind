"""P5B — Convergence Metrics.

Calculates the mathematical overlap (Intersection over Union) of behavioral
invariants and DAG structures across completely different goals/domains.
"""
from typing import List, Tuple, Set

def calculate_node_convergence(nodes_a: List[str], nodes_b: List[str]) -> float:
    """
    Computes Jaccard similarity between two sets of invariant intents.
    """
    set_a = set(nodes_a)
    set_b = set(nodes_b)
    
    if not set_a and not set_b:
        return 0.0
        
    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)
    
    return len(intersection) / len(union)

def calculate_edge_convergence(edges_a: List[List[str]], edges_b: List[List[str]]) -> float:
    """
    Computes Jaccard similarity between two sets of partial order edges (DAG).
    An edge is a directed relationship A -> B.
    """
    # Convert lists to tuples for hashing
    set_a = set(tuple(e) for e in edges_a)
    set_b = set(tuple(e) for e in edges_b)
    
    if not set_a and not set_b:
        return 0.0
        
    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)
    
    return len(intersection) / len(union)
