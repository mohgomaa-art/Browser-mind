"""P6 Utility Validation: Representation Gateway.

The Read-API contract. Replay and the Compiler consume representations through 
this Gateway instead of parsing raw traces directly.
"""
from typing import Optional
from browsermind_core.representation.generator import TraceType
from browsermind_core.representation.hypothesis import RepresentationBundle, RepresentationView
from browsermind_core.representation.adapters.flow_domain import FlowDomainAdapter
from browsermind_core.representation.adapters.task_locality import TaskLocalityAdapter

class RepresentationGateway:
    def __init__(self):
        self.adapters = {
            "flow_domain": FlowDomainAdapter(),
            "task_locality": TaskLocalityAdapter()
        }
        
        # We assume for this minimal test that the adapters have already generated
        # the hypotheses from the discovery phase. We hardcode the active hypotheses.
        self.active_hypotheses = {
            "flow_domain": "flow_domain_authentication_flow",
            "task_locality": "locality_github_412506f8"
        }
        
    def generate_bundle(self, trace: TraceType) -> RepresentationBundle:
        """Processes a trace into a multi-perspective Bundle."""
        bundle = RepresentationBundle()
        for ontology_type, adapter in self.adapters.items():
            hyp_id = self.active_hypotheses.get(ontology_type)
            if hyp_id:
                view = adapter.generate_view(trace, hyp_id)
                bundle.views.append(view)
        return bundle
        
    def get_view(self, trace: TraceType, preferred_ontology: str) -> Optional[RepresentationView]:
        """Returns the specific View requested by Replay/Compiler."""
        bundle = self.generate_bundle(trace)
        for view in bundle.views:
            # We loosely map the preferred ontology to the hypothesis ID for the test
            if preferred_ontology in view.ontology_id:
                return view
        return None
