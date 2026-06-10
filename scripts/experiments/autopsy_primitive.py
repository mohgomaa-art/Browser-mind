"""P5F.0 — OPEN_OBJECT Autopsy.

OPEN_OBJECT is a dead primitive. This tool performs a post-mortem.

For each instance of OPEN_OBJECT, we ask ONE question only:
    What state transition happened?

We do NOT impose a taxonomy. We annotate each instance with a candidate
transition derived purely from available signals (target_name, position,
followed_by), then let the human observer decide if natural clusters emerge.

Usage:
    python scripts/experiments/autopsy_primitive.py
"""
import sys
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
    """
    Infers a candidate state transition from available signals.
    This is a HEURISTIC annotation only — not a taxonomy.
    
    We are asking: what changed in the world as a result of this action?
    """
    name = target_name.lower()

    # Completion signals
    if any(x in name for x in ["finish", "complete", "done", "order confirm", "thank you", "back home"]):
        return "??? -> GOAL_ACHIEVED"

    # Workflow progression
    if any(x in name for x in ["continue", "next", "proceed", "submit order"]):
        return "STEP_N -> STEP_N+1"

    # Entering a sub-flow
    if any(x in name for x in ["checkout", "cart", "payment", "shipping"]):
        return "BROWSING -> TRANSACTION_FLOW"

    # Mutation (adding/removing something)
    if any(x in name for x in ["add to cart", "add to bag", "remove", "delete"]):
        return "ENTITY_ABSENT -> ENTITY_IN_CART"

    # Form / Information provision
    if target_role in ("textbox", "input") or any(
            x in name for x in ["first name", "last name", "zip", "postal", "email", "password"]):
        return "NO_DATA -> DATA_PROVIDED"

    # Entity navigation (specific named entity — link or card)
    if target_role in ("link", "article", "card"):
        short = target_name.strip()[:40]
        return f"UNKNOWN_ENTITY -> {short!r}"

    # Cancel / reset
    if any(x in name for x in ["cancel", "back", "reset"]):
        return "CURRENT_STATE -> PREVIOUS_STATE"

    # Late-position unknowns are likely closing actions
    if position > 0.85 and followed_by == "(end)":
        return "PENULTIMATE -> TERMINAL"

    # Fallback — unknown transition
    return "? -> ?"


def run():
    harness = ReplayExperimentHarness(headless=True)
    normalizer = PrimitiveNormalizer(collapse_level=0)
    TARGET = "OPEN_OBJECT"

    all_templates = harness.kernel.workflow_store.list_templates()
    raw_groups = defaultdict(list)
    for t_meta in all_templates:
        name = t_meta["name"]
        if name.startswith("var_"):
            parts = name.rsplit("_", 1)
            if len(parts) == 2:
                raw_groups[parts[0]].append(name)

    print(f"\n========================================================")
    print(f" P5F.0: OPEN_OBJECT AUTOPSY")
    print(f" Question: What state transition happened?")
    print(f"========================================================\n")

    by_family = defaultdict(list)

    for group_key, template_names in sorted(raw_groups.items()):
        family = get_candidate_family(group_key)
        for t_name in sorted(template_names):
            template = harness.load_template(t_name)
            steps = template.steps
            intent_seq = []
            raw_seq = []
            for step in steps:
                action_type = step.get("action_type", "")
                if action_type in ("session", "navigate"):
                    continue
                role = step.get("target_role", "")
                raw_name = step.get("target_name", "")
                intent = normalizer.normalize(action_type, role, raw_name)
                intent_seq.append(intent)
                raw_seq.append({
                    "action_type": action_type,
                    "target_role": role,
                    "target_name": raw_name.strip()[:45].replace("\n", " "),
                    "intent": intent
                })

            for idx, (intent, raw) in enumerate(zip(intent_seq, raw_seq)):
                if intent != TARGET:
                    continue
                preceded_by = intent_seq[idx - 1] if idx > 0 else "(start)"
                followed_by = intent_seq[idx + 1] if idx < len(intent_seq) - 1 else "(end)"
                pos = round(idx / max(len(intent_seq) - 1, 1), 2)
                transition = infer_transition(
                    raw["target_name"], raw["target_role"], followed_by, pos)

                by_family[family].append({
                    "group": group_key[-8:],
                    "demo": t_name[-1],
                    "role": raw["target_role"],
                    "name": raw["target_name"],
                    "preceded_by": preceded_by,
                    "followed_by": followed_by,
                    "pos": pos,
                    "transition": transition,
                })

    # Print grouped by family, sorted by inferred transition
    for family in sorted(by_family):
        instances = sorted(by_family[family], key=lambda x: x["transition"])
        print(f" [{family}]  —  {len(instances)} instances")
        print(f" {'Role':<12} {'Target Name':<46} {'Pos':>5}  Candidate State Transition")
        print(f" {'-'*120}")

        prev_trans = None
        for inst in instances:
            if inst["transition"] != prev_trans:
                if prev_trans is not None:
                    print()
                prev_trans = inst["transition"]

            print(f" {inst['role']:<12} {inst['name']:<46} {inst['pos']:>5.2f}  {inst['transition']}")

        print()

    print(f"========================================================")
    print(f" EMERGING QUESTIONS FOR THE HUMAN OBSERVER:")
    print(f"  - Do the '? -> ?' instances have something in common?")
    print(f"  - Are any 'transitions' actually the same across DISCOVERY and TRANSACTION?")
    print(f"  - How many distinct transition types genuinely appear?")
    print(f"========================================================")


if __name__ == "__main__":
    run()
