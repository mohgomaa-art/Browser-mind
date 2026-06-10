"""P6A Representation Kernel: Hypothesis Engine.

This module defines the core architectural entities for the Ontology Competition Era.
It is strictly agnostic to any specific ontological theory (e.g., Flow Domain, Capability).
It only knows about mathematical evidence and hypothetical graph structures.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvidenceDimension:
    """A single dimension of evidence for an ontology hypothesis."""
    name: str
    value: float
    confidence: float
    sample_size: int

@dataclass
class EvidenceSet:
    """Open set of evidence dimensions for an ontology hypothesis.
    
    Scores are kept separate (not merged into a single authority scalar) 
    because different ontologies win in different regions. The dimensions are 
    open-ended to support future metrics (e.g., cross_agent_transfer).
    """
    dimensions: dict[str, EvidenceDimension] = field(default_factory=dict)
    
    def add(self, name: str, value: float, confidence: float = 1.0, sample_size: int = 1):
        self.dimensions[name] = EvidenceDimension(name, value, confidence, sample_size)
        
    def get(self, name: str) -> float:
        return self.dimensions[name].value if name in self.dimensions else 0.0

@dataclass
class RepresentationHypothesis:
    """A single proposed ontological theory generated from traces.
    
    The kernel does not enforce what `ontology_type` means (it could be 
    "flow_domain", "task_locality", or "capability"). It only stores the
    resulting structure and its empirical evidence.
    """
    id: str
    ontology_type: str
    
    # The proposed ontology structure
    nodes: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    
    # Metadata about the hypothesis origin or constraints
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # The empirical authority of this hypothesis
    evidence: EvidenceSet = field(default_factory=EvidenceSet)

@dataclass
class RepresentationView:
    """How a specific trace is represented according to a specific Ontology."""
    ontology_id: str
    entities: list[str]
    relations: list[tuple[str, str]]
    confidence: float

@dataclass
class RepresentationBundle:
    """The final output of the Representation Kernel for a single trace.
    Contains multiple concurrent perspectives (views) of what just happened.
    """
    views: list[RepresentationView] = field(default_factory=list)
