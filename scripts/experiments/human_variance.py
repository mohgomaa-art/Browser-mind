#!/usr/bin/env python3
"""
Phase 6: Human Variance

Determines whether workflows are stable across multiple operators.
Reads 3 or more operator recordings for the same task and measures
the semantic similarity between their compiled workflow templates.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import Levenshtein

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness

def calculate_workflow_similarity(template1, template2):
    """
    Measures how similar two workflow templates are by looking at the sequences 
    of semantic actions and target roles.
    """
    def to_sequence(tpl):
        seq = []
        for step in tpl.steps:
            action = step.get("action_type", "")
            role = step.get("target_role", "")
            seq.append(f"{action}:{role}")
        return seq

    seq1 = to_sequence(template1)
    seq2 = to_sequence(template2)
    
    # Simple edit distance metric scaled to 0.0 - 1.0 (1.0 = identical)
    str1 = " ".join(seq1)
    str2 = " ".join(seq2)
    
    distance = Levenshtein.distance(str1, str2)
    max_len = max(len(str1), len(str2))
    
    if max_len == 0:
        return 1.0
        
    similarity = 1.0 - (distance / max_len)
    return max(0.0, similarity)

async def run_human_variance(template_names):
    harness = ReplayExperimentHarness()
    
    if len(template_names) < 2:
        print("Need at least 2 templates to compare variance.")
        return
        
    templates = []
    for name in template_names:
        try:
            tpl = harness.load_template(name)
            templates.append(tpl)
        except Exception as e:
            print(f"Error loading template {name}: {e}")
            return
            
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "human_variance" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=========================================")
    print(f"Human Variance Test")
    print(f"Comparing: {template_names}")
    print(f"=========================================\n")

    comparisons = []
    
    for i in range(len(templates)):
        for j in range(i+1, len(templates)):
            t1 = templates[i]
            t2 = templates[j]
            
            sim = calculate_workflow_similarity(t1, t2)
            
            comparisons.append({
                "template_A": t1.name,
                "template_B": t2.name,
                "similarity": round(sim, 4)
            })
            
            print(f"Similarity {t1.name} <-> {t2.name} = {sim*100:.1f}%")

    avg_similarity = sum(c["similarity"] for c in comparisons) / len(comparisons) if comparisons else 0

    print(f"\nAverage Similarity: {avg_similarity*100:.1f}%")

    summary = {
        "templates": template_names,
        "comparisons": comparisons,
        "average_similarity": avg_similarity
    }

    # Write summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved to: {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("templates", nargs="+", help="Names of templates to compare (min 2)")
    args = parser.parse_args()
    
    try:
        import Levenshtein
    except ImportError:
        print("This script requires the python-Levenshtein package.")
        print("Please install it using: pip install Levenshtein")
        sys.exit(1)
        
    try:
        asyncio.run(run_human_variance(args.templates))
    except KeyboardInterrupt:
        print("\nInterrupted.")
