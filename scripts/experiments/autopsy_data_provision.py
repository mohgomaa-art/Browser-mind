"""P5I-A — Unsupervised Semantic Autopsy for DATA_PROVISION.

Rather than forcing DATA_PROVISION into predefined semantic buckets 
(which uses ontology to discover ontology), this script extracts 
raw features and looks for natural, unsupervised clusters.

Features Extracted:
- target_name
- target_role
- goal_family
- preceded_by (intent)
- followed_by (intent)
- position_ratio

We group by `target_name` (normalized) to see what structures emerge.
"""
import sys
from collections import defaultdict, Counter
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
from browsermind_core.representation.candidate_families import get_candidate_family
from scripts.experiments.semantic_center_test import infer_transition


def normalize_name(name: str) -> str:
    """Normalize target names to group extremely similar fields."""
    name = name.lower().strip()
    # Remove common filler words that don't change the field semantics
    for word in ["enter", "your", "input", "the", "please", "confirm"]:
        name = name.replace(word, "").strip()
    return name if name else "[unnamed]"


def run():
    harness = ReplayExperimentHarness(headless=True)
    normalizer = PrimitiveNormalizer(collapse_level=0)

    all_templates = harness.kernel.workflow_store.list_templates()
    raw_groups = defaultdict(list)
    for t_meta in all_templates:
        name = t_meta["name"]
        if name.startswith("var_"):
            parts = name.rsplit("_", 1)
            if len(parts) == 2:
                raw_groups[parts[0]].append(name)

    instances = []

    for group_key, template_names in sorted(raw_groups.items()):
        family = get_candidate_family(group_key)
        for t_name in sorted(template_names):
            template = harness.load_template(t_name)
            steps = template.steps
            intent_seq, raw_seq = [], []

            for step in steps:
                act = step.get("action_type", "")
                if act in ("session", "navigate"):
                    continue
                role = step.get("target_role", "")
                raw_name = step.get("target_name", "")
                intent = normalizer.normalize(act, role, raw_name)
                intent_seq.append(intent)
                raw_seq.append({"role": role, "name": raw_name.strip(), "intent": intent})

            for idx, (intent, raw) in enumerate(zip(intent_seq, raw_seq)):
                preceded_by = intent_seq[idx - 1] if idx > 0 else "(start)"
                followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
                pos = idx / max(len(intent_seq) - 1, 1)
                
                # Structural transition
                trans = infer_transition(raw["name"], raw["role"], followed_by, pos)
                
                if trans == "NO_DATA -> DATA_PROVIDED":
                    norm_name = normalize_name(raw["name"])
                    instances.append({
                        "norm_name": norm_name,
                        "raw_name": raw["name"],
                        "role": raw["role"],
                        "family": family,
                        "preceded_by": preceded_by,
                        "followed_by": followed_by,
                        "pos": pos,
                        "original_intent": intent  # e.g. AUTHENTICATE or SUBMIT_QUERY
                    })

    total_instances = len(instances)
    
    print(f"\n========================================================")
    print(f" P5I-A: UNSUPERVISED SEMANTIC AUTOPSY (DATA_PROVISION)")
    print(f" Total Structural Instances: {total_instances}")
    print(f"========================================================\n")

    if total_instances == 0:
        print(" No instances found.")
        return

    # Cluster by normalized name
    clusters = defaultdict(list)
    for inst in instances:
        clusters[inst["norm_name"]].append(inst)

    # Sort clusters by size
    sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))

    # Print top clusters
    print(" TOP EMERGING DATA PATTERNS (By Field Name)")
    print(" --------------------------------------------------------")
    for name, insts in sorted_clusters:
        if len(insts) < 2:  # Skip one-offs to reduce noise
            continue
            
        pct = len(insts) / total_instances
        
        # Gather contextual features for this cluster
        families = Counter([i["family"] for i in insts])
        roles = Counter([i["role"] for i in insts])
        precedings = Counter([i["preceded_by"] for i in insts])
        followings = Counter([i["followed_by"] for i in insts])
        
        top_family = families.most_common(1)[0][0]
        top_role = roles.most_common(1)[0][0]
        top_pre = precedings.most_common(1)[0][0]
        top_post = followings.most_common(1)[0][0]
        
        print(f" 📂 '{name}' (n={len(insts)}, {pct:.0%})")
        print(f"      Family Context : {top_family} (and {len(families)-1} others)")
        print(f"      Element Role   : {top_role}")
        print(f"      Flow Context   : {top_pre} -> [DATA] -> {top_post}")
        print()

    print(f"========================================================")
    print(f" EMERGING QUESTIONS FOR THE HUMAN OBSERVER:")
    print(f" 1. Do these patterns represent distinct Primitives (Split)?")
    print(f" 2. Do they represent noise around a single Primitive (Survive)?")
    print(f" 3. Do they represent a Hierarchy (Meta-Primitive -> Primitives)?")
    print(f"========================================================")


if __name__ == "__main__":
    run()
