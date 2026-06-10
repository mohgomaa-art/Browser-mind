"""P5F.1 — Semantic Center Test + Primitive Death Ledger.

For every primitive that appears in the dataset, asks ONE question:
    Can all instances be explained by ONE state transition?

If YES: the primitive has a semantic center → ALIVE
If PARTIAL (2-3 distinct transitions): → SUSPECT
If NO (4+ distinct transitions): the primitive is a namespace collision → DEAD

Output: The Primitive Death Ledger.
"""
import sys
import json
from collections import defaultdict
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
from browsermind_core.representation.candidate_families import get_candidate_family


def infer_transition(target_name: str, target_role: str,
                     followed_by: str, position: float) -> str:
    """Same heuristic as autopsy_primitive.py — minimal, signal-based only."""
    name = target_name.lower()

    if any(x in name for x in ["finish", "complete", "done", "back home", "thank you"]):
        return "??? -> GOAL_ACHIEVED"
    if any(x in name for x in ["continue", "next", "proceed"]):
        return "STEP_N -> STEP_N+1"
    if any(x in name for x in ["checkout", "cart", "payment", "shipping"]):
        return "BROWSING -> TRANSACTION_FLOW"
    if any(x in name for x in ["add to cart", "add to bag"]):
        return "ENTITY_ABSENT -> ENTITY_IN_CART"
    if any(x in name for x in ["remove", "delete"]):
        return "ENTITY_PRESENT -> ENTITY_ABSENT"
    if target_role in ("textbox", "input") or any(
            x in name for x in ["first name", "last name", "zip", "postal", "email", "password"]):
        return "NO_DATA -> DATA_PROVIDED"
    if target_role in ("link", "article", "card") and len(target_name.strip()) > 3:
        return "UNKNOWN_ENTITY -> SPECIFIC_ENTITY"
    if any(x in name for x in ["cancel", "back", "reset"]):
        return "CURRENT_STATE -> PREVIOUS_STATE"
    if any(x in name for x in ["search", "find", "jump to", "search wikipedia",
                                "search models", "search code"]):
        return "SEARCH_CLOSED -> SEARCH_OPEN"
    if target_role in ("combobox", "dialog", "searchbox") and "search" in name:
        return "EMPTY_QUERY -> QUERY_ENTERED"
    if position > 0.85 and followed_by == "(end)":
        return "PENULTIMATE -> TERMINAL"

    return "? -> ?"


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

    # Collect transitions per primitive
    # structure: { primitive -> { transition -> count } }
    primitive_transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    primitive_families: dict[str, set] = defaultdict(set)

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
                followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
                pos = idx / max(len(intent_seq) - 1, 1)
                trans = infer_transition(raw["name"], raw["role"], followed_by, pos)
                primitive_transitions[intent][trans] += 1
                primitive_families[intent].add(family)

    # --- Build the Death Ledger ---
    ledger = []
    for primitive, transitions in sorted(primitive_transitions.items()):
        n_distinct = len(transitions)
        total_instances = sum(transitions.values())
        families = sorted(primitive_families[primitive])

        if n_distinct == 1:
            status = "ALIVE"
        elif n_distinct <= 3:
            status = "SUSPECT"
        else:
            status = "DEAD"

        dominant_trans = max(transitions, key=transitions.get)
        dominant_pct = transitions[dominant_trans] / total_instances

        ledger.append({
            "primitive": primitive,
            "status": status,
            "instances": total_instances,
            "distinct_transitions": n_distinct,
            "dominant_transition": dominant_trans,
            "dominant_pct": round(dominant_pct, 2),
            "all_transitions": dict(sorted(transitions.items(), key=lambda x: -x[1])),
            "families_seen_in": families,
        })

    # Sort: DEAD first, then SUSPECT, then ALIVE; then by instance count
    order = {"DEAD": 0, "SUSPECT": 1, "ALIVE": 2}
    ledger.sort(key=lambda x: (order[x["status"]], -x["instances"]))

    # Print
    print(f"\n========================================================")
    print(f" PRIMITIVE DEATH LEDGER (P5F.1)")
    print(f" Criterion: Can all instances share ONE state transition?")
    print(f"========================================================\n")

    status_icons = {"ALIVE": "✅", "SUSPECT": "⚠️ ", "DEAD": "❌"}
    status_counts = defaultdict(int)

    for entry in ledger:
        icon = status_icons[entry["status"]]
        pct = f"{entry['dominant_pct']:.0%}"
        fams = ", ".join(entry["families_seen_in"])
        print(f" {icon} [{entry['status']:<7}] {entry['primitive']:<35}"
              f"  n={entry['instances']:>3}  distinct={entry['distinct_transitions']}"
              f"  dominant={pct}  [{fams}]")

        if entry["status"] != "ALIVE":
            for trans, count in entry["all_transitions"].items():
                bar = "█" * min(count, 20)
                print(f"             {trans:<45} x{count}  {bar}")
        print()
        status_counts[entry["status"]] += 1

    print(f"========================================================")
    print(f" SUMMARY")
    print(f"   ALIVE   : {status_counts['ALIVE']}")
    print(f"   SUSPECT : {status_counts['SUSPECT']}")
    print(f"   DEAD    : {status_counts['DEAD']}")

    # Save to file
    out_dir = ROOT / "reports" / "primitives"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "death_ledger.json"
    out_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"\n Ledger saved to: {out_path}")
    print(f"========================================================")


if __name__ == "__main__":
    run()
