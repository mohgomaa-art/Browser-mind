from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import graph_edges, graph_nodes, iter_dataset_samples, rel


def _complexity(nodes: List[Dict], edges: List) -> str:
    interactive = sum(
        1
        for n in nodes
        if isinstance(n, dict)
        and n.get("role") in {"button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem"}
    )
    max_depth = max((int(n.get("depth", 0)) for n in nodes if isinstance(n, dict)), default=0)
    if len(nodes) >= 60 or interactive >= 25 or max_depth >= 12:
        return "hard"
    if len(nodes) >= 20 or interactive >= 8 or max_depth >= 6:
        return "medium"
    return "easy"


def observation_audit(paths: List[str] | None = None, max_examples: int = 25) -> Dict:
    total = 0
    failures = 0
    sparse_failures = 0
    node_total = 0
    edge_total = 0
    depth_total = 0
    density_total = 0.0
    complexity = Counter()
    examples = []

    for fp, loc, sample in iter_dataset_samples(paths):
        nodes = graph_nodes(sample)
        edges = graph_edges(sample)
        ax_nodes = len(nodes)
        edge_count = len(edges)
        max_depth = max((int(n.get("depth", 0)) for n in nodes if isinstance(n, dict)), default=0)
        density = edge_count / max(ax_nodes, 1)
        success = bool(sample.get("success", True))

        total += 1
        node_total += ax_nodes
        edge_total += edge_count
        depth_total += max_depth
        density_total += density
        complexity[_complexity(nodes, edges)] += 1

        if not success:
            failures += 1
            if ax_nodes < 10:
                sparse_failures += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "file": rel(fp),
                            "location": loc,
                            "goal": str(sample.get("goal", ""))[:120],
                            "url": str(sample.get("url", ""))[:160],
                            "ax_nodes": ax_nodes,
                            "edges": edge_count,
                            "max_depth": max_depth,
                        }
                    )

    return {
        "total_samples": total,
        "avg_ax_nodes": round(node_total / max(total, 1), 2),
        "avg_edges": round(edge_total / max(total, 1), 2),
        "avg_graph_density": round(density_total / max(total, 1), 4),
        "avg_graph_depth": round(depth_total / max(total, 1), 2),
        "failures": failures,
        "sparse_graph_failures": sparse_failures,
        "sparse_graph_failure_rate": round(sparse_failures / max(failures, 1), 4),
        "vision_gate": {
            "eligible": failures > 0 and sparse_failures / max(failures, 1) > 0.50,
            "rule": "Vision fallback is justified only if sparse graph failures exceed 50% of failures.",
        },
        "complexity_distribution": dict(complexity),
        "examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit AX-tree observation quality.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = observation_audit(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
