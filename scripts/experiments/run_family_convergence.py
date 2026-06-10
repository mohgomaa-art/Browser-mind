"""P5D — Candidate Family Convergence Runner.

The decisive experiment: tests whether invariants converge WITHIN candidate
behavioral clusters but diverge ACROSS them.

Three outcomes are possible and ALL are scientifically valuable:
    1. Separability > 30%  -> Behavior Clusters exist. (families are real)
    2. Separability 10-30% -> Weak cluster signal. Partial structure.
    3. Separability < 10%  -> No cluster structure. Primitive space is flat.

NOTE: We use the term "Candidate Family" not "Capability Family" because
the labels (DISCOVERY, TRANSACTION) are hypotheses, not proven facts.
The Separability Score is what determines if they are real.
"""
import sys
import statistics
from collections import defaultdict
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.convergence_metrics import (
    calculate_node_convergence, calculate_edge_convergence
)
from browsermind_core.representation.invariant_compiler import InvariantCompiler
from browsermind_core.representation.candidate_families import get_candidate_family


def load_and_compile_groups(harness: ReplayExperimentHarness, collapse_level: int = 1):
    all_templates = harness.kernel.workflow_store.list_templates()
    raw_groups = defaultdict(list)
    for t_meta in all_templates:
        name = t_meta["name"]
        if not name.startswith("var_"):
            continue
        parts = name.rsplit("_", 1)
        if len(parts) == 2:
            raw_groups[parts[0]].append(name)

    compiler = InvariantCompiler(variant_threshold=0.2, collapse_level=collapse_level)
    compiled = []
    for group_key, template_names in sorted(raw_groups.items()):
        templates = [harness.load_template(n) for n in sorted(template_names)]
        graph = compiler.compile_from_templates(goal_id=group_key, templates=templates)
        family = get_candidate_family(group_key)
        compiled.append({"group_key": group_key, "family": family, "graph": graph})

    return compiled


def run():
    harness = ReplayExperimentHarness(headless=True)
    compiled = load_and_compile_groups(harness, collapse_level=1)

    print(f"\n========================================================")
    print(f" P5D: CANDIDATE FAMILY SEPARABILITY TEST")
    print(f" Vocabulary: L1 (LOCATE / SELECT)")
    print(f"========================================================\n")

    # Summary
    families = defaultdict(list)
    for c in compiled:
        families[c["family"]].append(c["group_key"])

    for fam in sorted(families):
        marker = "[CANDIDATE]" if fam != "UNKNOWN" else "[UNASSIGNED]"
        print(f" {marker} {fam}:")
        for k in families[fam]:
            print(f"     - {k}")
    print()

    # Pairwise comparisons
    within_pairs = []
    cross_pairs = []
    n = len(compiled)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = compiled[i], compiled[j]
            if "UNKNOWN" in (a["family"], b["family"]):
                continue
            nc = calculate_node_convergence(a["graph"].invariants, b["graph"].invariants)
            ec = calculate_edge_convergence(
                a["graph"].partial_order_edges, b["graph"].partial_order_edges)
            pair = (a["group_key"], b["group_key"], nc, ec, a["family"], b["family"])
            if a["family"] == b["family"]:
                within_pairs.append(pair)
            else:
                cross_pairs.append(pair)

    def avg(pairs, idx):
        vals = [p[idx] for p in pairs]
        return statistics.mean(vals) if vals else None

    # --- Print pair details ---
    print(f" WITHIN-CANDIDATE-FAMILY PAIRS:")
    if not within_pairs:
        print("   (None — need >= 2 groups in the same candidate family)")
    for a_key, b_key, nc, ec, fa, fb in within_pairs:
        print(f"   {fa}  {a_key[-8:]}  vs  {b_key[-8:]}  ->  Node={nc:.2%}  Edge={ec:.2%}")

    print(f"\n CROSS-CANDIDATE-FAMILY PAIRS:")
    if not cross_pairs:
        print("   (None — need >= 2 different candidate families)")
    for a_key, b_key, nc, ec, fa, fb in cross_pairs:
        print(f"   {fa} vs {fb}  {a_key[-8:]} vs {b_key[-8:]}  ->  Node={nc:.2%}  Edge={ec:.2%}")

    # --- Summary ---
    within_node = avg(within_pairs, 2)
    cross_node  = avg(cross_pairs, 2)
    within_edge = avg(within_pairs, 3)
    cross_edge  = avg(cross_pairs, 3)

    print(f"\n========================================================")
    print(f" MEASUREMENT SUMMARY")
    print(f"--------------------------------------------------------")
    w_str = f"{within_node:.2%}" if within_node is not None else "N/A"
    c_str = f"{cross_node:.2%}"  if cross_node  is not None else "N/A"
    we_str = f"{within_edge:.2%}" if within_edge is not None else "N/A"
    ce_str = f"{cross_edge:.2%}"  if cross_edge  is not None else "N/A"

    print(f" Within-Candidate Node Conv  : {w_str}")
    print(f" Cross-Candidate  Node Conv  : {c_str}")
    print(f" Within-Candidate Edge Conv  : {we_str}")
    print(f" Cross-Candidate  Edge Conv  : {ce_str}")
    print(f"--------------------------------------------------------")

    # --- Separability Score (the key metric) ---
    if within_node is not None and cross_node is not None:
        sep_node = within_node - cross_node
        sep_edge = (within_edge or 0) - (cross_edge or 0)
        print(f"\n FAMILY SEPARABILITY SCORE")
        print(f"   Node Separability : {sep_node:+.2%}")
        print(f"   Edge Separability : {sep_edge:+.2%}")
        print(f"\n--------------------------------------------------------")

        if sep_node > 0.30:
            print(" => [BEHAVIOR CLUSTERS EXIST]")
            print("    The candidate families correspond to real behavioral boundaries.")
            print("    Within-cluster invariants are significantly more similar.")
            print("    This supports the Capability Families hypothesis.")
        elif sep_node > 0.10:
            print(" => [WEAK CLUSTER SIGNAL]")
            print("    Some family structure exists, but the boundaries are fuzzy.")
            print("    The candidate family labels may need refinement.")
        else:
            print(" => [NO CLUSTER STRUCTURE]")
            print("    Within vs Cross convergence is indistinguishable.")
            print("    The candidate family labels do not reflect real behavioral boundaries.")
            print("    The primitive space is flat — no family-level ontology exists.")
    else:
        missing = []
        if within_node is None:
            missing.append(">= 2 groups in same candidate family (DISCOVERY has 3 — check labels)")
        if cross_node is None:
            missing.append(">= 2 different candidate families (record SauceDemo TRANSACTION data)")
        print(f"\n => [WAITING FOR DATA]")
        for m in missing:
            print(f"    - Need: {m}")
        print(f"\n    Next step:")
        print(f"    $env:BM_VAULT_SECRET='secret_sauce'")
        print(f"    python scripts/experiments/record_variance.py --target saucedemo --runs 5")

    print(f"========================================================")


if __name__ == "__main__":
    run()
