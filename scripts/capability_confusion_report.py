"""
Capability Confusion Report -- overlap matrix before V1.2 recompile.
Writes reports/capability_confusion_report.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.capability_taxonomy import load_taxonomy, rank_capabilities
from training.task_value_estimator import learning_stage

OVERLAP_RATIO = 0.70  # runner-up within this fraction of best -> ambiguous pair


def _load_candidates() -> List[Dict[str, Any]]:
    path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_report(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    tax = load_taxonomy()
    cap_ids = [c for c in tax["capabilities"] if c != "other"]

    distribution: Counter = Counter()
    confidence_sum: Dict[str, float] = defaultdict(float)
    confidence_count: Dict[str, int] = defaultdict(int)
    overlap_counts: Dict[str, Counter] = defaultdict(Counter)
    ambiguous = 0

    for r in candidates:
        target = r.get("target", r.get("name", ""))
        role = r.get("role", "")
        sf = r.get("state_family", "")
        ranked = rank_capabilities(target, role=role, state_family=sf)
        best_id, best_str, conf = ranked[0]
        distribution[best_id] += 1
        confidence_sum[best_id] += conf
        confidence_count[best_id] += 1

        if best_id == "other":
            continue

        if len(ranked) > 1 and ranked[1][1] >= best_str * OVERLAP_RATIO:
            ambiguous += 1
            second_id = ranked[1][0]
            pair = tuple(sorted([best_id, second_id]))
            overlap_counts[pair[0]][pair[1]] += 1
            overlap_counts[pair[1]][pair[0]] += 1

    n = len(candidates)
    unknown_rate = distribution.get("other", 0) / n if n else 0.0

    capability_confidence = {
        cap: round(confidence_sum[cap] / confidence_count[cap], 4)
        for cap in confidence_count
    }

    # Normalize overlap matrix to percentages per row
    overlap_matrix: Dict[str, Dict[str, float]] = {}
    for a in cap_ids:
        row_total = sum(overlap_counts[a].values()) or 1
        overlap_matrix[a] = {
            b: round(overlap_counts[a][b] / row_total, 4)
            for b in cap_ids
            if overlap_counts[a][b] > 0 and a != b
        }

    # High-overlap pairs (>30% of ambiguous cases involving either cap)
    hot_pairs = []
    for a in cap_ids:
        for b, pct in overlap_matrix.get(a, {}).items():
            if pct >= 0.3:
                hot_pairs.append({"a": a, "b": b, "overlap_rate": pct})

    learning_stage_dist = Counter()
    for cap, count in distribution.items():
        learning_stage_dist[learning_stage(cap)] += count

    return {
        "schema": "browsermind.capability_confusion_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": n,
        "overlap_threshold_ratio": OVERLAP_RATIO,
        "capability_distribution": dict(distribution.most_common()),
        "capability_distribution_pct": {
            k: round(v / n, 4) for k, v in distribution.items()
        },
        "capability_confidence": capability_confidence,
        "capability_unknown_rate": round(unknown_rate, 4),
        "ambiguous_classification_count": ambiguous,
        "ambiguous_classification_rate": round(ambiguous / n, 4) if n else 0.0,
        "capability_overlap_matrix": overlap_matrix,
        "high_overlap_pairs": sorted(hot_pairs, key=lambda x: -x["overlap_rate"])[:20],
        "learning_stage_distribution": dict(learning_stage_dist),
        "taxonomy_maturity": {
            "mature": unknown_rate < 0.15 and ambiguous / n < 0.25 if n else False,
            "notes": (
                "If job_application<->account_creation or signup<->multi_field_form >30%, "
                "refine classification_order and signals before curriculum scaling."
            ),
        },
    }


def main():
    candidates = _load_candidates()
    report = build_report(candidates)
    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "capability_confusion_report.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps(
        {
            "unknown_rate": report["capability_unknown_rate"],
            "ambiguous_rate": report["ambiguous_classification_rate"],
            "top_capabilities": list(report["capability_distribution"].items())[:8],
            "high_overlap_pairs": report["high_overlap_pairs"][:6],
        },
        indent=2,
    ))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
