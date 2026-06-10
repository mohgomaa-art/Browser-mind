"""Invariant Discovery Harness (Refined).

Extracts an InvariantGraph from a set of human demonstrations grouped by a Variance Group ID,
printing Intents, Support Scores, and the Partial Order Graph.
"""
import asyncio
import argparse
import json
import sys
from pathlib import Path

# Fix for charmap errors on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site
from browsermind_core.representation.invariant_compiler import InvariantCompiler

async def discover_invariants(target: str, group_id: str):
    harness = ReplayExperimentHarness(headless=True)
    site = get_site(target)
    
    prefix = f"var_{target}_{group_id[:8]}"
    templates_meta = [t for t in harness.kernel.workflow_store.list_templates() if t["name"].startswith(prefix)]
    
    if not templates_meta:
        print(f"No templates found for group {group_id}")
        return
        
    print(f"\n========================================================")
    print(f" INVARIANT DISCOVERY ENGINE (P5A.3)")
    print(f" Target: {site.label} ({site.key})")
    print(f" Group ID: {group_id}")
    print(f" Demonstrations: {len(templates_meta)}")
    print(f"========================================================\n")

    templates = []
    for t_meta in templates_meta:
        t_name = t_meta["name"]
        templates.append(harness.load_template(t_name))
        
    compiler = InvariantCompiler(variant_threshold=0.2)
    graph = compiler.compile_from_templates(goal_id=f"{target}_{group_id[:8]}", templates=templates)
    
    # Save the output
    output_dir = ROOT / "reports" / "invariants"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"invariant_graph_{graph.goal_id}.json"
    
    out_path.write_text(json.dumps(graph.model_dump(), indent=2), encoding="utf-8")
    
    print(f" [INVARIANTS] Support Score = 1.0:")
    for p in graph.invariants:
        print(f"   -> {p}")
        
    print(f"\n [VARIANTS] Support Score >= 0.2:")
    for p in graph.variants:
        print(f"   -> {p} (Support: {graph.support_scores[p]:.2f})")
        
    print(f"\n [NOISE] Support Score < 0.2:")
    for p in graph.noise:
        print(f"   -> {p} (Support: {graph.support_scores[p]:.2f})")
        
    print(f"\n [PARTIAL ORDER GRAPH] Precedence Edges:")
    if not graph.partial_order_edges:
        print("   (No strict precedence found)")
    for a, b in graph.partial_order_edges:
        print(f"   {a}  --->  {b}")
        
    print(f"\n========================================================")
    print(f" Graph saved to: {out_path}")
    print(f"========================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P5A Invariant Discovery Engine")
    parser.add_argument("--target", required=True, help="Site key (e.g., github)")
    parser.add_argument("--group", required=True, help="Variance Group ID")
    args = parser.parse_args()
    asyncio.run(discover_invariants(args.target, args.group))
