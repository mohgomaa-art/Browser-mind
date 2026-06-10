"""P6A Representation Kernel: Ontology Generator Interface.

This module defines the bottom-up inference engine. Traces create ontologies.
The Kernel provides this abstract base class. Specific adapters (like 
FlowDomainAdapter or TaskLocalityAdapter) will implement this to generate 
hypotheses from raw data.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from browsermind_core.representation.hypothesis import RepresentationHypothesis, RepresentationView

# In a real run, this would be the actual ReplayTrace or WorkflowTemplate.
# We use Any here to avoid circular imports during kernel bootstrap.
TraceType = Any


class OntologyGenerator(ABC):
    """Abstract base class for all Ontology Adapters.
    
    Generators do not 'evaluate' an existing ontology against a trace.
    They 'infer' a hypothesis FROM a collection of traces, and then 
    generate specific 'views' for new traces.
    """
    
    @property
    @abstractmethod
    def ontology_type(self) -> str:
        """The type of ontology this generator produces (e.g., 'flow_domain')."""
        pass

    @abstractmethod
    def infer_hypothesis(self, traces: list[TraceType], **kwargs) -> list[RepresentationHypothesis]:
        """Generates one or more RepresentationHypothesis objects from traces.
        
        Args:
            traces: A collection of recorded workflow traces.
            **kwargs: Adapter-specific parameters (e.g., ablation settings).
            
        Returns:
            A list of generated hypotheses with preliminary EvidenceSets.
        """
        pass
        
    @abstractmethod
    def generate_view(self, trace: TraceType, hypothesis_id: str) -> RepresentationView:
        """Translates a single trace into the specific language of the given hypothesis.
        
        Args:
            trace: A single recorded workflow trace.
            hypothesis_id: The ID of the RepresentationHypothesis to use.
            
        Returns:
            A RepresentationView representing the trace through the lens of the hypothesis.
        """
        pass
