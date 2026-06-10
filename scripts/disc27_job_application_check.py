#!/usr/bin/env python3
"""Quick DISC-2.7 check: job_application vs multi_field_form on hiring zone text."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.capability_taxonomy import competition_scores, rank_capabilities

HIRING_ZONE = [
    "apply now",
    "submit application",
    "work experience",
    "cover letter",
    "first name",
    "last name",
    "email address",
    "phone",
    "resume",
    "multi field form application",
]


def main():
    node_scores = competition_scores(
        "Apply now",
        role="button",
        state_family="multi_field_form",
        zone_texts=HIRING_ZONE,
    )
    ranked = rank_capabilities(
        "Apply now",
        role="button",
        state_family="multi_field_form",
        zone_texts=HIRING_ZONE,
    )
    winner = ranked[0][0] if ranked else "none"
    top_margin = 0.0
    if len(ranked) >= 2:
        top_margin = ranked[0][1] - ranked[1][1]

    report = {
        "schema": "browsermind.disc27_check.v1",
        "taxonomy_version": "1.27",
        "winner": winner,
        "top_margin": round(top_margin, 4),
        "ranked_top5": [(r[0], round(r[1], 4)) for r in ranked[:5]],
        "job_vs_multifield": {
            "job_application": node_scores.get("job_application", 0),
            "multi_field_form": node_scores.get("multi_field_form", 0),
        },
        "node_competition": {k: round(v, 4) for k, v in sorted(node_scores.items(), key=lambda x: -x[1])[:8]},
    }
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "disc27_job_application_check.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"winner={winner}  margin={top_margin:.3f}")
    print("top5:", ranked[:5])
    print(f"Wrote {out}")
    return 0 if winner == "job_application" else 1


if __name__ == "__main__":
    raise SystemExit(main())
