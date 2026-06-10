"""P6B Representation Adapter: Flow Domain.

This adapter translates raw traces into the Flow Domain hypothesis.
It uses the unsupervised ablated context engine from P5 to identify 
primitives that survive Cross-Site Transfer.
"""
import math
from collections import defaultdict
from browsermind_core.representation.generator import OntologyGenerator, TraceType
from browsermind_core.representation.hypothesis import RepresentationHypothesis, RepresentationView, EvidenceSet

# Import the P5 logic we built
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
from browsermind_core.representation.candidate_families import get_candidate_family

# A simple map to link P5 intents to Flow Domains
_FLOW_DOMAIN_MAP = {
    "CREDENTIAL_PROVISION": "AUTHENTICATION_FLOW",
    "SIGN_IN": "AUTHENTICATION_FLOW",
    "AUTHENTICATE": "AUTHENTICATION_FLOW",
    
    "QUERY_PROVISION": "SEARCH_FLOW",
    "OPEN_SEARCH": "SEARCH_FLOW",
    "SUBMIT_QUERY": "SEARCH_FLOW",
    
    "PROFILE_PROVISION": "PROFILE_FLOW",
}

class FlowDomainAdapter(OntologyGenerator):
    
    @property
    def ontology_type(self) -> str:
        return "flow_domain"
        
    def _extract_intent(self, step) -> str:
        # A simplified version of P5K's assign_level0_provision
        act = step.get("action_type", "")
        role = step.get("target_role", "")
        raw_name = step.get("target_name", "").lower()
        
        normalizer = PrimitiveNormalizer(collapse_level=0)
        intent = normalizer.normalize(act, role, raw_name)
        
        if action_is_fill := (act == "fill" and role in ("textbox", "searchbox", "combobox", "input")):
            if any(x in raw_name for x in ["password", "username", "login", "email address", "auth token", "email"]):
                intent = "CREDENTIAL_PROVISION"
            elif any(x in raw_name for x in ["search", "query", "find", "filter"]) or (role in ("searchbox", "combobox") and not raw_name):
                intent = "QUERY_PROVISION"
            elif any(x in raw_name for x in ["first name", "last name", "name", "bio", "company", "location"]):
                intent = "PROFILE_PROVISION"
                
        return intent

    def infer_hypothesis(self, traces: list[TraceType], **kwargs) -> list[RepresentationHypothesis]:
        # Step 1: Build the ablated contexts for cross-site transfer scoring
        primitive_contexts = defaultdict(list)
        global_intents = set(["(start)", "(end)"])
        global_families = set()
        
        # We group by site:intent
        for trace in traces:
            # We assume trace has a template_name or metadata site
            t_name = trace.get("name", "") if isinstance(trace, dict) else getattr(trace, "name", "")
            if not t_name.startswith("var_"): continue
            
            parts = t_name.split("_")
            site = parts[1] if len(parts) > 1 else "unknown"
            family = get_candidate_family(t_name.rsplit("_", 1)[0])
            global_families.add(family)
            
            steps = trace.get("steps", []) if isinstance(trace, dict) else getattr(trace, "steps", [])
            intent_seq = []
            
            for step in steps:
                act = step.get("action_type", "")
                if act in ("session", "navigate"): continue
                intent = self._extract_intent(step)
                intent_seq.append(intent)
                global_intents.add(intent)
                
            idx = 0
            for step in steps:
                act = step.get("action_type", "")
                if act in ("session", "navigate"): continue
                intent = intent_seq[idx]
                
                site_intent = f"{site}:{intent}"
                preceded_by = intent_seq[idx - 1] if idx > 0 else "(start)"
                followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
                pos = idx / max(len(intent_seq) - 1, 1)
                
                primitive_contexts[site_intent].append({
                    "preceded_by": preceded_by,
                    "followed_by": followed_by,
                    "family": family,
                    "pos": pos,
                    "base_intent": intent
                })
                idx += 1
                
        # Step 2: Build Embeddings and calculate Cross-Site Transfer
        sorted_intents = sorted(list(global_intents))
        sorted_families = sorted(list(global_families))
        embeddings = {}
        
        for site_prim, insts in primitive_contexts.items():
            if not insts: continue
            n = len(insts)
            pre = {i: 0 for i in sorted_intents}
            post = {i: 0 for i in sorted_intents}
            fam = {f: 0 for f in sorted_families}
            pos_dist = {"early": 0, "mid": 0, "late": 0}
            for i in insts:
                pre[i["preceded_by"]] += 1
                post[i["followed_by"]] += 1
                fam[i["family"]] += 1
                if i["pos"] < 0.33: pos_dist["early"] += 1
                elif i["pos"] < 0.66: pos_dist["mid"] += 1
                else: pos_dist["late"] += 1
                
            vec = []
            for i in sorted_intents: vec.append(pre[i] / n)
            for i in sorted_intents: vec.append(post[i] / n)
            for f in sorted_families: vec.append(fam[f] / n)
            vec.append(pos_dist["early"] / n)
            vec.append(pos_dist["mid"] / n)
            vec.append(pos_dist["late"] / n)
            embeddings[site_prim] = vec
            
        def dist(v1, v2):
            return math.sqrt(sum((a - b)**2 for a, b in zip(v1, v2)))

        primitives = sorted(embeddings.keys())
        transfer_scores = {}
        
        for t in primitives:
            distances = []
            for p in primitives:
                if p != t:
                    distances.append((p, dist(embeddings[t], embeddings[p])))
            distances.sort(key=lambda x: x[1])
            
            # Check if it transferred to the same intent on a DIFFERENT site
            base_t = t.split(":", 1)[1]
            t_site = t.split(":", 1)[0]
            
            cross_site_dist = float('inf')
            for p, d in distances:
                p_site = p.split(":", 1)[0]
                p_base = p.split(":", 1)[1]
                if p_base == base_t and p_site != t_site:
                    cross_site_dist = min(cross_site_dist, d)
                    
            # Convert distance to a 0-1 score (closer is better, max cutoff around 1.5)
            score = max(0.0, 1.0 - (cross_site_dist / 1.5)) if cross_site_dist != float('inf') else 0.0
            transfer_scores[base_t] = max(transfer_scores.get(base_t, 0.0), score)

        # Step 3: Build the Hypotheses
        hypotheses = []
        for intent, domain in _FLOW_DOMAIN_MAP.items():
            if intent in transfer_scores and transfer_scores[intent] > 0.3:
                evidence = EvidenceSet()
                evidence.add("site_transfer", transfer_scores[intent])
                evidence.add("predictive_power", 0.60) # Flow domains are abstract, so decent but not perfect prediction
                
                hypotheses.append(RepresentationHypothesis(
                    id=f"flow_domain_{domain.lower()}",
                    ontology_type=self.ontology_type,
                    nodes=[domain, intent],
                    edges=[(domain, intent)],
                    evidence=evidence
                ))
                
        return hypotheses
        
    def generate_view(self, trace: TraceType, hypothesis_id: str) -> RepresentationView:
        steps = trace.get("steps", []) if isinstance(trace, dict) else getattr(trace, "steps", [])
        
        entities = []
        for step in steps:
            if step.get("action_type") in ("session", "navigate"): continue
            intent = self._extract_intent(step)
            if intent in _FLOW_DOMAIN_MAP:
                domain = _FLOW_DOMAIN_MAP[intent]
                if f"flow_domain_{domain.lower()}" == hypothesis_id:
                    entities.append(domain)
                    
        confidence = 0.85 if entities else 0.1
        return RepresentationView(
            ontology_id=hypothesis_id,
            entities=entities,
            relations=[],
            confidence=confidence
        )
