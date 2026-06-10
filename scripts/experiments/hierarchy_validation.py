"""P5K — Flow Domain Validation (Cross-Site Transfer).

This script tests if the Flow Domains discovered in P5J.0 survive Cross-Site Transfer.
If a domain is just a Task Locality (site-specific neighborhood), it will not cluster 
with equivalent primitives from other sites. 
If it is a true Flow Domain, `github:QUERY_PROVISION` will cluster with 
`wikipedia:QUERY_PROVISION` based purely on their shared context structure.

We output 'Candidate Ontologies' based on the resulting clusters.
"""
import sys
import math
from collections import defaultdict
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
from browsermind_core.representation.candidate_families import get_candidate_family

def assign_level0_provision(target_name: str, target_role: str, action: str) -> str:
    """Intercept and assign our Level 0 PROVISION primitives based ONLY on name/role."""
    if action != "fill" or target_role not in ("textbox", "searchbox", "combobox", "input"):
        return None
        
    name = target_name.lower()
    if any(x in name for x in ["password", "username", "login", "email address", "auth token"]):
        return "CREDENTIAL_PROVISION"
    if any(x in name for x in ["search", "query", "find", "filter"]) or (target_role in ("searchbox", "combobox") and not name):
        return "QUERY_PROVISION"
    if any(x in name for x in ["first name", "last name", "name", "bio", "company", "location", "address", "zip", "postal", "city", "country"]):
        return "PROFILE_PROVISION"
    if any(x in name for x in ["title", "body", "description", "comment", "issue"]):
        return "CONTENT_PROVISION"
    if any(x in name for x in ["card", "cvc", "expiry", "shipping"]):
        return "PAYMENT_PROVISION"
    if "email" in name:
        return "CREDENTIAL_PROVISION"
    return "UNKNOWN_PROVISION"


def run():
    harness = ReplayExperimentHarness(headless=True)
    normalizer = PrimitiveNormalizer(collapse_level=0)

    all_templates = harness.kernel.workflow_store.list_templates()
    raw_groups = defaultdict(list)
    for t_meta in all_templates:
        if t_meta["name"].startswith("var_"):
            parts = t_meta["name"].rsplit("_", 1)
            if len(parts) == 2:
                raw_groups[parts[0]].append(t_meta["name"])

    traces = []
    global_intents = set(["(start)", "(end)"])
    global_families = set()

    # Pass 1: Build the intent sequences
    for group_key, template_names in raw_groups.items():
        family = get_candidate_family(group_key)
        global_families.add(family)
        site = group_key.split("_")[1] if len(group_key.split("_")) > 1 else "unknown"
        
        for t_name in template_names:
            template = harness.load_template(t_name)
            steps = template.steps
            
            intent_seq = []
            valid_steps = []
            
            for step in steps:
                act = step.get("action_type", "")
                if act in ("session", "navigate"):
                    continue
                role = step.get("target_role", "")
                raw_name = step.get("target_name", "")
                
                intent = normalizer.normalize(act, role, raw_name)
                
                provision_intent = assign_level0_provision(raw_name, role, act)
                if provision_intent and provision_intent != "UNKNOWN_PROVISION":
                    intent = provision_intent
                    
                intent_seq.append(intent)
                global_intents.add(intent)
                valid_steps.append({"intent": intent, "family": family, "site": site})
                
            traces.append((valid_steps, intent_seq))

    # Pass 2: Collect contexts using Site-Aware Nodes (site:intent)
    # The context relies on the generic intents so cross-site overlap is possible.
    primitive_contexts = defaultdict(list)
    
    for valid_steps, intent_seq in traces:
        for idx, step_info in enumerate(valid_steps):
            intent = step_info["intent"]
            site = step_info["site"]
            site_intent = f"{site}:{intent}"
            
            preceded_by = intent_seq[idx - 1] if idx > 0 else "(start)"
            followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
            pos = idx / max(len(intent_seq) - 1, 1)
            
            primitive_contexts[site_intent].append({
                "preceded_by": preceded_by,
                "followed_by": followed_by,
                "family": step_info["family"],
                "pos": pos,
                "base_intent": intent
            })

    # Pass 3: Build ABLATED Embeddings (No role, No action)
    sorted_intents = sorted(list(global_intents))
    sorted_families = sorted(list(global_families))
    
    embeddings = {}
    
    for site_prim, insts in primitive_contexts.items():
        if len(insts) < 1:  # Accept even small instances for cross-site checks
            continue 
            
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

    # Pass 4: Global Distance Matrix (Euclidean)
    def dist(v1, v2):
        return math.sqrt(sum((a - b)**2 for a, b in zip(v1, v2)))

    primitives = sorted(embeddings.keys())
    
    print(f"\n========================================================")
    print(f" P5K: CROSS-SITE TRANSFER (COMPETING ONTOLOGIES)")
    print(f"========================================================\n")
    
    # We want to check specifically if PROVISION primitives transfer across sites.
    targets = ["CREDENTIAL_PROVISION", "PROFILE_PROVISION", "QUERY_PROVISION", "CONTENT_PROVISION", "PAYMENT_PROVISION"]
    
    # Find all site-aware nodes for these targets
    site_targets = []
    for t in targets:
        site_targets.extend([p for p in primitives if p.endswith(f":{t}")])
        
    print(" 🔍 Nearest Neighbors for Cross-Site Validation:")
    print(" -----------------------------------------------------------------")
    
    clusters_formed = defaultdict(list)
    
    for t in sorted(site_targets):
        distances = []
        for p in primitives:
            if p != t:
                distances.append((p, dist(embeddings[t], embeddings[p])))
                
        distances.sort(key=lambda x: x[1])
        
        base_t = t.split(":", 1)[1]
        print(f"🎯 {t:<35}")
        
        top_neighbors = []
        for p, d in distances[:3]:
            base_p = p.split(":", 1)[1]
            # Is it transferring across site for the SAME provision?
            is_cross_site = "⭐" if (base_p == base_t and p.split(":")[0] != t.split(":")[0]) else "  "
            print(f"      {is_cross_site} -> {p:<35} (dist: {d:.2f})")
            top_neighbors.append(p)
            
        clusters_formed[base_t].append((t, top_neighbors))
        print()

    print(f"========================================================")
    print(f" CANDIDATE ONTOLOGIES VERDICT")
    print(f"========================================================")
    
    for base_t, results in clusters_formed.items():
        cross_site_count = 0
        total_sites = len(results)
        for t, neighbors in results:
            if any(n.split(":")[1] == base_t for n in neighbors):
                cross_site_count += 1
                
        if total_sites > 1 and cross_site_count >= 1:
            print(f" ✅ {base_t}: FLOW DOMAIN DETECTED")
            print(f"    Survived Cross-Site Transfer across {total_sites} sites.")
        elif total_sites == 1:
            print(f" ⚠️ {base_t}: TASK LOCALITY (Only observed on 1 site)")
        else:
            print(f" ❌ {base_t}: SHATTERED")
            print(f"    Failed to transfer. It is highly site-specific.")
            
    print(f"\n========================================================")
    print(f" CONCLUSION: P5 completes by generating these candidate")
    print(f" ontologies. The representation schema must support competing")
    print(f" frameworks rather than a single frozen hierarchy.")
    print(f"========================================================")

if __name__ == "__main__":
    run()
