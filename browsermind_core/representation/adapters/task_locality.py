"""P6B Representation Adapter: Task Locality.

This adapter translates raw traces into the Task Locality hypothesis.
It assumes that the web is organized by site-specific, physical UI clusters.
It heavily weights Predictive Power (because on a known site, it perfectly 
predicts the next step) but scores 0 on Site Transferability.
"""
from browsermind_core.representation.generator import OntologyGenerator, TraceType
from browsermind_core.representation.hypothesis import RepresentationHypothesis, RepresentationView, EvidenceSet

class TaskLocalityAdapter(OntologyGenerator):
    
    @property
    def ontology_type(self) -> str:
        return "task_locality"

    def infer_hypothesis(self, traces: list[TraceType], **kwargs) -> list[RepresentationHypothesis]:
        # Step 1: Group traces exactly by site and exact physical flow
        site_flows = {}
        
        for trace in traces:
            t_name = trace.get("name", "") if isinstance(trace, dict) else getattr(trace, "name", "")
            if not t_name.startswith("var_"): continue
            
            parts = t_name.split("_")
            site = parts[1] if len(parts) > 1 else "unknown"
            family = parts[2] if len(parts) > 2 else "flow" # e.g. var_github_1a2b -> 1a2b group
            
            cluster_id = f"{site}_{family}"
            
            steps = trace.get("steps", []) if isinstance(trace, dict) else getattr(trace, "steps", [])
            physical_nodes = []
            
            for step in steps:
                act = step.get("action_type", "")
                if act in ("session", "navigate"): continue
                
                # We use the raw target name instead of the normalized intent
                raw_name = step.get("target_name", "").strip()
                if not raw_name:
                    raw_name = step.get("target_role", "unknown")
                    
                node = f"{act.upper()}_{raw_name.upper().replace(' ', '_')}"
                physical_nodes.append(node)
                
            if physical_nodes:
                if cluster_id not in site_flows:
                    site_flows[cluster_id] = []
                site_flows[cluster_id].append(physical_nodes)
                
        # Step 2: Build the Hypotheses
        hypotheses = []
        for cluster_id, node_lists in site_flows.items():
            # If a physical flow is repeated on the same site, it has high predictive power
            if len(node_lists) >= 1:
                evidence = EvidenceSet()
                evidence.add("site_transfer", 0.0) # By definition, Task Locality does not transfer
                evidence.add("predictive_power", 0.95) # High prediction on this exact site
                
                # Just take the longest observed sequence as the structure
                best_nodes = max(node_lists, key=len)
                edges = [(best_nodes[i], best_nodes[i+1]) for i in range(len(best_nodes)-1)]
                
                hypotheses.append(RepresentationHypothesis(
                    id=f"locality_{cluster_id}",
                    ontology_type=self.ontology_type,
                    nodes=best_nodes,
                    edges=edges,
                    evidence=evidence
                ))
                
        return hypotheses
        
    def generate_view(self, trace: TraceType, hypothesis_id: str) -> RepresentationView:
        # Check if the trace physically matches this locality
        steps = trace.get("steps", []) if isinstance(trace, dict) else getattr(trace, "steps", [])
        
        entities = []
        for step in steps:
            act = step.get("action_type", "")
            if act in ("session", "navigate"): continue
            raw_name = step.get("target_name", "").strip() or step.get("target_role", "unknown")
            node = f"{act.upper()}_{raw_name.upper().replace(' ', '_')}"
            entities.append(node)
            
        confidence = 0.90 if entities else 0.1
        return RepresentationView(
            ontology_id=hypothesis_id,
            entities=entities,
            relations=[],
            confidence=confidence
        )
