#!/usr/bin/env python3
"""
Experiment 3: Human Variance Analyzer

IMPORTANT: This script does NOT record sessions. It only analyzes them.

Human Variance cannot be measured from simulated noise or automated runs.
Real human operators must record distinct sessions manually before this
script can produce meaningful results.

Input:  N workflow template names (pre-recorded by different human operators)
Output: Distance matrix + Variance report -> reports/survivability/variance/

Distance Metrics:
  Action Distance:     Edit distance on sequence of action_types only
                       (ignores what was acted upon)
  Semantic Distance:   Edit distance on (action_type, role, name) tuples
                       (full semantic identity)
  Capability Distance: Edit distance on (action_type, role) pairs
                       (ignores specific element names)

Interpretation:
  Action == 0, Semantic > 0  → Same action sequence, different targets
  Action > 0                 → Different strategy (real Human Variance)
  Capability == 0, Action > 0 → Same capabilities used, different execution path
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import KernelSession, DEFAULT_STORE


# ---------------------------------------------------------------------------
# Levenshtein distance for sequence comparison
# ---------------------------------------------------------------------------

def levenshtein(s1: list, s2: list) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = range(len(s2) + 1)
    for c1 in s1:
        curr = [prev[0] + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def avg_pairwise(sequences: list) -> float:
    n = len(sequences)
    total, pairs = 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            total += levenshtein(sequences[i], sequences[j])
            pairs += 1
    return total / pairs if pairs > 0 else 0.0


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def load_template_signatures(kernel: KernelSession, template_name: str):
    """
    Load a template from the store and extract three signature views.
    Returns (action_sig, semantic_sig, capability_sig).
    """
    entry = kernel.workflow_store.lookup_template(template_name)
    if not entry:
        print(f"  [WARN] Template '{template_name}' not found in store — skipping.")
        return None, None, None

    tpl = kernel.workflow_store.get_template(entry["id"])

    action_sig     = []
    semantic_sig   = []
    capability_sig = []

    for step in tpl.steps:
        action = step.get("action_type", "?")
        role   = step.get("target_role", "?")
        name   = step.get("target_name", "?")

        action_sig.append(action)
        semantic_sig.append(f"{action}:{role}:{name}")
        capability_sig.append(f"{action}:{role}")

    return action_sig, semantic_sig, capability_sig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Human Variance Analyzer — analysis only, no recording"
    )
    parser.add_argument(
        "--templates",
        nargs="+",
        required=True,
        help="Names of pre-recorded templates to compare (e.g. operator_A_login operator_B_login)",
    )
    parser.add_argument("--label", default="variance", help="Label for the output file")
    args = parser.parse_args()

    print(f"=== Human Variance Analyzer ===")
    print(f"Templates: {args.templates}")
    print(f"Count: {len(args.templates)} recordings\n")

    if len(args.templates) < 2:
        print("[ERROR] Need at least 2 templates to compute variance.")
        sys.exit(1)

    kernel = KernelSession(DEFAULT_STORE)

    action_sigs     = []
    semantic_sigs   = []
    capability_sigs = []
    loaded_names    = []

    for tpl_name in args.templates:
        act, sem, cap = load_template_signatures(kernel, tpl_name)
        if act is not None:
            action_sigs.append(act)
            semantic_sigs.append(sem)
            capability_sigs.append(cap)
            loaded_names.append(tpl_name)
            print(f"  Loaded '{tpl_name}': {len(act)} steps")

    if len(action_sigs) < 2:
        print("[ERROR] Not enough templates loaded. Record more sessions first.")
        sys.exit(1)

    # Compute distances
    avg_action     = avg_pairwise(action_sigs)
    avg_semantic   = avg_pairwise(semantic_sigs)
    avg_capability = avg_pairwise(capability_sigs)

    print(f"\n=== Distance Results ({len(loaded_names)} recordings) ===")
    print(f"  Action Distance:     {avg_action:.2f}")
    print(f"  Semantic Distance:   {avg_semantic:.2f}")
    print(f"  Capability Distance: {avg_capability:.2f}")

    # Interpret
    if avg_action == 0:
        conclusion = "All humans used the identical action sequence. No variance detected."
    elif avg_capability == 0:
        conclusion = "Same capabilities used across humans but execution paths differ. Workflow is capability-stable."
    elif avg_semantic == 0:
        conclusion = "Same semantic targets used but action order varies. Semantic abstraction is stable."
    else:
        conclusion = f"True human variance detected. Semantic Distance={avg_semantic:.2f} — multiple strategies observed."

    print(f"\n  [Conclusion] {conclusion}")

    # Output
    out_dir = ROOT / "reports" / "survivability" / "variance"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.label}_human_variance.json"

    results = {
        "label": args.label,
        "templates_compared": loaded_names,
        "recording_count": len(loaded_names),
        "action_distance": avg_action,
        "semantic_distance": avg_semantic,
        "capability_distance": avg_capability,
        "conclusion": conclusion,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n  Metrics → {out_file}")


if __name__ == "__main__":
    main()
