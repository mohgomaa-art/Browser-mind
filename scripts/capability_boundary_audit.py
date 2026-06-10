"""
Phase V1.25 -- Capability Boundary Audit
Static boundaries + empirical distribution after v1.25 classifier.
Writes reports/capability_boundary_audit.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.capability_taxonomy import export_boundary_audit_table, rank_capabilities

OVERLAP_RATIO = 0.72


def _load_candidates() -> list:
    path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _empirical_confusions(candidates: list) -> dict:
    overlap_counts: dict = defaultdict(Counter)
    distribution: Counter = Counter()
    ambiguous = 0
    conf_sum: dict = defaultdict(float)
    conf_n: dict = defaultdict(int)

    for r in candidates:
        target = r.get("target", r.get("name", ""))
        role = r.get("role", "")
        sf = r.get("state_family", "")
        ranked = rank_capabilities(target, role=role, state_family=sf)
        best_id, best_s, conf = ranked[0]
        distribution[best_id] += 1
        conf_sum[best_id] += conf
        conf_n[best_id] += 1

        if len(ranked) > 1 and ranked[1][1] >= best_s * OVERLAP_RATIO:
            ambiguous += 1
            a, b = sorted([best_id, ranked[1][0]])
            overlap_counts[a][b] += 1

    n = len(candidates)
    return {
        "sample_size": n,
        "capability_distribution": dict(distribution.most_common()),
        "capability_unknown_rate": round(distribution.get("other", 0) / n, 4) if n else 0,
        "ambiguous_rate": round(ambiguous / n, 4) if n else 0,
        "capability_confidence_avg": {
            k: round(conf_sum[k] / conf_n[k], 4) for k in conf_n
        },
        "empirical_overlap_pairs": [
            {"a": a, "b": b, "count": c}
            for a, ctr in overlap_counts.items()
            for b, c in ctr.most_common(10)
        ],
        "targets": {
            "other_lt_10pct": distribution.get("other", 0) / n < 0.10 if n else False,
            "unknown_lt_15pct": distribution.get("other", 0) / n < 0.15 if n else False,
            "ambiguous_lt_20pct": ambiguous / n < 0.20 if n else False,
        },
    }


def main():
    static_table = export_boundary_audit_table()
    candidates = _load_candidates()
    empirical = _empirical_confusions(candidates)

    # Merge static confusions_with vs empirical top overlaps
    for cap_id, row in static_table.items():
        row["empirical_count"] = empirical["capability_distribution"].get(cap_id, 0)

    report = {
        "schema": "browsermind.capability_boundary_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "V1.25",
        "taxonomy_version": "1.25",
        "capabilities": static_table,
        "empirical_after_v125": empirical,
        "gate_readiness": empirical["targets"],
    }

    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "capability_boundary_audit.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("========== V1.25 BOUNDARY AUDIT ==========")
    print(f"other rate:      {empirical['capability_unknown_rate']:.1%}")
    print(f"ambiguous rate:  {empirical['ambiguous_rate']:.1%}")
    print(f"gate readiness:  {empirical['targets']}")
    print(f"\nTop distribution: {list(empirical['capability_distribution'].items())[:8]}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
