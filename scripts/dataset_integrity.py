from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import (
    counter_to_sorted_dict,
    domain_from_url,
    extract_action_id_and_name,
    graph_nodes,
    graph_signature,
    iter_dataset_samples,
    load_json_file,
    rel,
    resolve_roots,
    sample_dedup_key,
    state_family_key,
    trajectory_signature,
)


def _depth_bucket(depth: int) -> str:
    if depth <= 3:
        return "0_3"
    if depth <= 7:
        return "4_7"
    if depth <= 12:
        return "8_12"
    return "13_plus"


def _size_bucket(size: int) -> str:
    if size < 10:
        return "lt_10"
    if size < 30:
        return "10_29"
    if size < 60:
        return "30_59"
    return "60_plus"


def _iter_trajectory_files(paths: List[str] | None):
    for root in resolve_roots(paths):
        files = [root] if root.is_file() else sorted(root.rglob("*.json"))
        for fp in files:
            data, _ = load_json_file(fp)
            if data is None:
                continue
            if isinstance(data, dict) and isinstance(data.get("samples"), list):
                samples = [s for s in data["samples"] if isinstance(s, dict)]
            elif isinstance(data, list):
                samples = [s for s in data if isinstance(s, dict)]
            elif isinstance(data, dict) and ("graph" in data or "expert_action" in data):
                samples = [data]
            else:
                samples = []
            if samples:
                yield fp, samples


def dataset_integrity(paths: List[str] | None = None, max_examples: int = 25) -> Dict:
    total = 0
    sample_keys = Counter()
    graph_keys = Counter()
    state_keys = Counter()
    goals = Counter()
    domains = Counter()
    families = Counter()
    actions = Counter()
    size_buckets = Counter()
    depth_buckets = Counter()
    duplicate_examples = []

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        key = sample_dedup_key(sample)
        graph_key = graph_signature(sample)
        family = state_family_key(sample)
        nodes = graph_nodes(sample)
        max_depth = max((int(n.get("depth", 0)) for n in nodes if isinstance(n, dict)), default=0)
        action_id, action_name, _ = extract_action_id_and_name(sample)

        sample_keys[key] += 1
        graph_keys[graph_key] += 1
        state_keys[graph_key] += 1
        families[family] += 1
        goals[str(sample.get("goal", "")).strip().lower()] += 1
        domains[domain_from_url(str(sample.get("url", "")))] += 1
        actions[action_name or str(action_id)] += 1
        size_buckets[_size_bucket(len(nodes))] += 1
        depth_buckets[_depth_bucket(max_depth)] += 1

        if sample_keys[key] == 2 and len(duplicate_examples) < max_examples:
            duplicate_examples.append({"file": rel(fp), "location": loc, "dedup_key": key})

    trajectory_keys = Counter()
    trajectory_examples = []
    trajectory_count = 0
    for fp, samples in _iter_trajectory_files(paths):
        trajectory_count += 1
        sig = trajectory_signature(samples)
        trajectory_keys[sig] += 1
        if trajectory_keys[sig] == 2 and len(trajectory_examples) < max_examples:
            trajectory_examples.append({"file": rel(fp), "trajectory_hash": sig})

    duplicate_samples = sum(c - 1 for c in sample_keys.values() if c > 1)
    duplicate_graphs = sum(c - 1 for c in graph_keys.values() if c > 1)
    duplicate_goals = sum(c - 1 for c in goals.values() if c > 1 and c > 0)
    duplicate_trajectories = sum(c - 1 for c in trajectory_keys.values() if c > 1)

    return {
        "total_samples": total,
        "unique_states": len(state_keys),
        "unique_graphs": len(graph_keys),
        "unique_goals": len([g for g in goals if g]),
        "unique_domains": len([d for d in domains if d and d != "unknown"]),
        "unique_trajectories": len(trajectory_keys),
        "duplicate_samples": duplicate_samples,
        "duplicate_graphs": duplicate_graphs,
        "duplicate_goals": duplicate_goals,
        "duplicate_trajectories": duplicate_trajectories,
        "duplicate_rate": round(duplicate_samples / max(total, 1), 4),
        "graph_duplicate_rate": round(duplicate_graphs / max(total, 1), 4),
        "trajectory_duplicate_rate": round(duplicate_trajectories / max(trajectory_count, 1), 4),
        "state_family_distribution": counter_to_sorted_dict(families),
        "action_distribution": counter_to_sorted_dict(actions),
        "domain_distribution_top": counter_to_sorted_dict(Counter(dict(domains.most_common(25)))),
        "graph_size_buckets": counter_to_sorted_dict(size_buckets),
        "graph_depth_buckets": counter_to_sorted_dict(depth_buckets),
        "duplicate_examples": duplicate_examples,
        "duplicate_trajectory_examples": trajectory_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit BrowserMind dataset integrity.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = dataset_integrity(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
