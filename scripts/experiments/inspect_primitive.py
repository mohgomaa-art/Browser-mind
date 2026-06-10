"""P5E.0 — Primitive Split Test.

Extracts all instances of a target primitive (e.g., SUBMIT_QUERY) across
all variance groups and records their full context.

We do NOT run any clustering algorithm. We print a raw context table.
The human observer decides if the instances form natural clusters.

Usage:
    python scripts/experiments/inspect_primitive.py --primitive SUBMIT_QUERY
    python scripts/experiments/inspect_primitive.py --primitive SUBMIT_QUERY --level 0
"""
import sys
import argparse
from collections import defaultdict
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
from browsermind_core.representation.candidate_families import get_candidate_family


def extract_instances(target_primitive: str, collapse_level: int = 0):
    harness = ReplayExperimentHarness(headless=True)
    normalizer = PrimitiveNormalizer(collapse_level=collapse_level)

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

            # Build the intent sequence for this demonstration
            intent_seq = []
            raw_seq = []
            for step in steps:
                action_type = step.get("action_type", "")
                if action_type in ("session", "navigate"):
                    continue
                role = step.get("target_role", "")
                name = step.get("target_name", "")
                intent = normalizer.normalize(action_type, role, name)
                intent_seq.append(intent)
                raw_seq.append({
                    "action_type": action_type,
                    "target_role": role,
                    "target_name": name.strip()[:60].replace("\n", " "),
                    "intent": intent
                })

            # Find all occurrences of the target primitive
            for idx, (intent, raw) in enumerate(zip(intent_seq, raw_seq)):
                if intent != target_primitive:
                    continue

                # Context
                preceded_by = intent_seq[idx - 1] if idx > 0 else "(start)"
                followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
                position_ratio = idx / max(len(intent_seq) - 1, 1)

                instances.append({
                    "group": group_key[-8:],
                    "demo": t_name[-1],
                    "family": family,
                    "action_type": raw["action_type"],
                    "target_role": raw["target_role"],
                    "target_name": raw["target_name"],
                    "preceded_by": preceded_by,
                    "followed_by": followed_by,
                    "position": round(position_ratio, 2),
                })

    return instances


def run():
    parser = argparse.ArgumentParser(description="P5E.0 Primitive Split Test")
    parser.add_argument("--primitive", required=True, help="Primitive to inspect (e.g. SUBMIT_QUERY)")
    parser.add_argument("--level", type=int, default=0, help="Collapse level for normalization (default: 0)")
    args = parser.parse_args()

    instances = extract_instances(args.primitive, collapse_level=args.level)

    print(f"\n========================================================")
    print(f" P5E.0: PRIMITIVE SPLIT TEST")
    print(f" Target Primitive : {args.primitive}  (L{args.level})")
    print(f" Total Instances  : {len(instances)}")
    print(f"========================================================\n")

    if not instances:
        print(f" No instances of '{args.primitive}' found across any variance group.")
        return

    # Group by family for clarity
    by_family = defaultdict(list)
    for inst in instances:
        by_family[inst["family"]].append(inst)

    col_w = {
        "group": 10, "demo": 4, "action": 10, "role": 12, "name": 35,
        "preceded": 20, "followed": 20, "pos": 6
    }

    header = (f"{'Group':<{col_w['group']}} {'D':<{col_w['demo']}} "
              f"{'Action':<{col_w['action']}} {'Role':<{col_w['role']}} "
              f"{'Target Name':<{col_w['name']}} "
              f"{'Preceded By':<{col_w['preceded']}} "
              f"{'Followed By':<{col_w['followed']}} "
              f"{'Pos':>{col_w['pos']}}")

    for family, insts in sorted(by_family.items()):
        print(f" [{family}]")
        print(f" {header}")
        print(f" {'-' * (sum(col_w.values()) + len(col_w))}")
        for i in insts:
            row = (f" {i['group']:<{col_w['group']}} {i['demo']:<{col_w['demo']}} "
                   f"{i['action_type']:<{col_w['action']}} {i['target_role']:<{col_w['role']}} "
                   f"{i['target_name']:<{col_w['name']}} "
                   f"{i['preceded_by']:<{col_w['preceded']}} "
                   f"{i['followed_by']:<{col_w['followed']}} "
                   f"{i['position']:>{col_w['pos']}.2f}")
            print(row)
        print()

    print(f"========================================================")
    print(f" OBSERVER QUESTIONS:")
    print(f"  1. Does 'preceded_by' separate into distinct groups?")
    print(f"  2. Does 'followed_by' separate into distinct groups?")
    print(f"  3. Does 'position' cluster early vs late?")
    print(f"  4. Does 'target_role' differ systematically?")
    print(f"\n  If YES to 2+ questions: the primitive is overloaded.")
    print(f"  If NO:                  the primitive is coherent.")
    print(f"========================================================")


if __name__ == "__main__":
    run()
