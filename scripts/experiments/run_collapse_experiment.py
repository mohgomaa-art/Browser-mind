"""P5C — Multi-Level Primitive Collapse Experiment.

Runs the Invariant Compiler at abstraction Level 0, 1, and 2 across ALL
existing variance groups and measures the Convergence Rate at each level.

The verdict:
  - Convergence climbs significantly (37% -> 70%+): Primitives were too shallow.
  - Convergence stays flat (37% -> 35-40%): Capability Families are the correct layer.
"""
import sys
import json
import statistics
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import EXPERIMENT_SITES
from browsermind_core.experiments.convergence_metrics import calculate_node_convergence, calculate_edge_convergence
from browsermind_core.representation.invariant_compiler import InvariantCompiler


def load_all_variance_groups(harness: ReplayExperimentHarness):
    """Finds all var_* templates and groups them by group prefix."""
    all_templates = harness.kernel.workflow_store.list_templates()
    groups = {}
    for t_meta in all_templates:
        name = t_meta["name"]
        if not name.startswith("var_"):
            continue
        # e.g. var_github_412506f8_1 -> group key: var_github_412506f8
        parts = name.rsplit("_", 1)
        if len(parts) == 2:
            group_key = parts[0]
            groups.setdefault(group_key, []).append(name)
    return groups


def compute_convergence_at_level(harness: ReplayExperimentHarness, groups: dict, level: int):
    """Compiles all groups at a given collapse level, returns (graphs, node_conv, edge_conv, global_nodes)."""
    compiler = InvariantCompiler(variant_threshold=0.2, collapse_level=level)
    graphs = []

    for group_key, template_names in sorted(groups.items()):
        templates = [harness.load_template(n) for n in sorted(template_names)]
        graph = compiler.compile_from_templates(goal_id=group_key, templates=templates)
        graphs.append(graph)

    M = len(graphs)
    if M < 2:
        return graphs, 0.0, 0.0, []

    node_vals, edge_vals = [], []
    for i in range(M):
        for j in range(i + 1, M):
            node_vals.append(calculate_node_convergence(graphs[i].invariants, graphs[j].invariants))
            edge_vals.append(calculate_edge_convergence(
                graphs[i].partial_order_edges, graphs[j].partial_order_edges))

    avg_node = statistics.mean(node_vals) if node_vals else 0.0
    avg_edge = statistics.mean(edge_vals) if edge_vals else 0.0

    # Global Invariants (present in >= 70% of goals as full Invariants)
    intent_counts = {}
    for g in graphs:
        for node in g.invariants:
            intent_counts[node] = intent_counts.get(node, 0) + 1
    global_nodes = sorted(n for n, c in intent_counts.items() if (c / M) >= 0.7)

    return graphs, avg_node, avg_edge, global_nodes


def run():
    harness = ReplayExperimentHarness(headless=True)
    groups = load_all_variance_groups(harness)

    if not groups:
        print("No variance groups found. Run record_variance.py first.")
        return

    print(f"\n========================================================")
    print(f" P5C: PRIMITIVE COLLAPSE EXPERIMENT")
    print(f" Variance Groups Found: {len(groups)}")
    for gk in sorted(groups):
        print(f"   - {gk} ({len(groups[gk])} demos)")
    print(f"========================================================\n")

    level_names = {0: "Fine-Grained (L0)", 1: "Merged (L1)", 2: "Abstract (L2)"}
    results = []

    for level in [0, 1, 2]:
        _, node_conv, edge_conv, global_nodes = compute_convergence_at_level(harness, groups, level)
        results.append((level, node_conv, edge_conv, global_nodes))

    # Print results table
    print(f"{'Level':<6} {'Vocabulary':<22} {'Node Conv':>12} {'Edge Conv':>12}  Global Invariants")
    print("-" * 90)
    for level, node_conv, edge_conv, global_nodes in results:
        nodes_str = ", ".join(global_nodes) if global_nodes else "(none)"
        print(f"  L{level}   {level_names[level]:<22} {node_conv:>10.2%}   {edge_conv:>10.2%}   {nodes_str}")

    print(f"\n========================================================")
    # Verdict
    l0_node = results[0][1]
    l1_node = results[1][1]
    l2_node = results[2][1]
    delta_l1 = l1_node - l0_node
    delta_l2 = l2_node - l0_node

    if delta_l1 > 0.3:
        print(" => [VOCABULARY WAS TOO SHALLOW]")
        print("    Merging primitives significantly increases convergence.")
        print("    LOCATE and SELECT are candidates for the real primitive layer.")
    elif delta_l1 > 0.1:
        print(" => [PARTIAL COLLAPSE]")
        print("    Some abstraction helps, but domain-specific patterns persist.")
    else:
        print(" => [CAPABILITY-SCOPED PRIMITIVES ARE CORRECT]")
        print("    Merging does not help. No Universal Primitive exists.")
        print("    The correct granularity is Capability Families.")

    print(f"========================================================")


if __name__ == "__main__":
    run()
