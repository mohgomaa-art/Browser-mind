"""P5A — Representation Schemas for Invariant Discovery.

Defines the structure of the Invariant Graph, which uses Partial Order Graphs
and Support Scores to capture behavioral invariants across human variance.
"""
import hashlib
from typing import List, Dict, Tuple
from pydantic import BaseModel, Field

class InvariantGraph(BaseModel):
    """
    The collapsed behavioral representation of a Goal.
    Uses support scores instead of hard thresholds, and partial ordering
    instead of linear sequences.
    """
    goal_id: str
    demonstrations_count: int

    # Intents with support score == 1.0
    invariants: List[str] = Field(default_factory=list)

    # Intents with support score < 1.0 but >= threshold (e.g. 0.2)
    variants: List[str] = Field(default_factory=list)

    # Intents with very low support (e.g. < 0.2)
    noise: List[str] = Field(default_factory=list)

    # Continuous support scores for all observed intents (0.0 to 1.0)
    support_scores: Dict[str, float] = Field(default_factory=dict)

    # Partial Order Graph (DAG) edges: [A, B] means A must precede B.
    # We only store strict precedences that hold across ALL demonstrations where both A and B occur.
    partial_order_edges: List[Tuple[str, str]] = Field(default_factory=list)

    @property
    def invariant_hash(self) -> str:
        """Content-addressed structural identity for this capability pattern.

        Deterministic: depends only on the sorted invariant intent list, not on
        goal_id or any site-specific label. Two graphs with identical invariants
        produced from different workflows on different environments will share the
        same hash — that is the point. This is the pre-naming identity key.

        Returns a 16-character hex prefix of SHA-256(sorted invariants joined by '|').
        Empty invariant list → hash of empty string (still deterministic).
        """
        canonical = "|".join(sorted(self.invariants))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
