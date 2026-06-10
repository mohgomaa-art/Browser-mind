"""
Phase V1 -- Task Value / Capability Value Audit
Classifies opportunities by web capability (not role) and reports acceptance rates.
Writes reports/value_audit.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.capability_taxonomy import classify_capability, load_taxonomy

BOUNDARY_LOW = 0.40
BOUNDARY_HIGH = 0.50


def _load_candidates() -> List[Dict[str, Any]]:
    cache = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    if os.path.isfile(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(
        "Run quality_sensitivity.py first to build reports/_quality_candidates_cache.json"
    )


def _row_from_candidate(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "target": r.get("target", r.get("name", "")),
        "url": r.get("url", ""),
        "role": r.get("role", ""),
        "state_family": r.get("state_family", ""),
        "quality_score": r.get("quality_score", 0),
        "capability": classify_capability(
            r.get("target", r.get("name", "")),
            r.get("role", ""),
            r.get("state_family", ""),
        ),
    }


def _stats_for_bucket(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(items)
    if n == 0:
        return {
            "count": 0,
            "accepted": 0,
            "near_miss": 0,
            "rejected": 0,
            "acceptance_rate": 0.0,
            "near_miss_rate": 0.0,
            "rejection_rate": 0.0,
        }
    accepted = sum(1 for i in items if i["quality_score"] >= MIN_QUALITY_SCORE)
    near = sum(
        1
        for i in items
        if BOUNDARY_LOW <= i["quality_score"] < MIN_QUALITY_SCORE
    )
    rejected = n - accepted
    return {
        "count": n,
        "accepted": accepted,
        "near_miss": near,
        "rejected": rejected,
        "acceptance_rate": round(accepted / n, 4),
        "near_miss_rate": round(near / n, 4),
        "rejection_rate": round(rejected / n, 4),
    }


def build_report(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [_row_from_candidate(r) for r in candidates]
    by_cap: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cap[row["capability"]].append(row)

    capability_stats = {
        cap: _stats_for_bucket(items) for cap, items in sorted(by_cap.items())
    }

    # High-value near-miss review set
    review_path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "high_value_near_miss_review.json"
    )
    review_examples: Dict[str, List[Dict[str, Any]]] = {
        cap: [] for cap in load_taxonomy()["capabilities"]
    }
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as f:
            review = json.load(f)
        for r in review.get("rows", []):
            cap = classify_capability(
                r.get("target", ""),
                r.get("role", ""),
                r.get("state_family", ""),
            )
            review_examples.setdefault(cap, []).append(
                {
                    "target": r["target"],
                    "url": r["url"],
                    "role": r["role"],
                    "current_score": r["current_score"],
                    "capability": cap,
                }
            )

    # Role vs capability cross-tab for near-miss band
    near_miss = [
        r for r in rows if BOUNDARY_LOW <= r["quality_score"] < MIN_QUALITY_SCORE
    ]
    near_by_cap = Counter(r["capability"] for r in near_miss)
    accepted_by_cap = Counter(
        r["capability"] for r in rows if r["quality_score"] >= MIN_QUALITY_SCORE
    )

    high_value_caps = ("auth_recovery", "search", "upload", "filter", "settings")
    hv_near = sum(near_by_cap.get(c, 0) for c in high_value_caps)
    legal_near = near_by_cap.get("legal", 0) + near_by_cap.get("marketing", 0)

    return {
        "schema": "browsermind.value_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "V1.1_capability_taxonomy",
        "taxonomy_path": "training/capability_taxonomy_v1.json",
        "sample_size": len(rows),
        "threshold": MIN_QUALITY_SCORE,
        "near_miss_band": [BOUNDARY_LOW, BOUNDARY_HIGH],
        "verdict": {
            "role_blind_to_capability": True,
            "high_value_near_miss_vs_legal_marketing": {
                "high_value_capability_near_miss": hv_near,
                "legal_marketing_near_miss": legal_near,
                "interpretation": (
                    "If high_value near-miss >> legal/marketing, quality cannot distinguish "
                    "task types -- supports Task Value Modeling layer."
                    if hv_near > legal_near
                    else "Mixed -- human review still required."
                ),
            },
        },
        "capability_stats": capability_stats,
        "near_miss_by_capability": dict(near_by_cap.most_common()),
        "accepted_by_capability": dict(accepted_by_cap.most_common()),
        "high_value_near_miss_by_capability": review_examples,
        "cto_notes": {
            "quality_collapse": "Quality ~= learnability ~= role; links 0% pass rate.",
            "next_layer": "task_value estimation before quality composition",
            "rarity_status": "constant 1.0 -- remove or wire to live coverage DB",
            "task_relevance_status": "weak separator (pass 1.0 vs fail 0.84)",
        },
    }


def main():
    candidates = _load_candidates()
    report = build_report(candidates)
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "value_audit.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("========== VALUE AUDIT (by capability) ==========")
    for cap, st in report["capability_stats"].items():
        if st["count"] == 0:
            continue
        print(
            f"  {cap:<16} n={st['count']:>4}  "
            f"accept={st['acceptance_rate']:.1%}  near_miss={st['near_miss_rate']:.1%}"
        )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
