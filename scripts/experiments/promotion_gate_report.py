"""P5G — Promotion Gate Report.

Standalone report that reads the Birth Ledger and evaluates every candidate
against the formal promotion rules. Prints the full gate status table.

This script is the single source of truth for promotion status.
Run it after any Birth Ledger update.
"""
import sys
import json
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.representation.promotion_rules import (
    evaluate_candidate, PromotionTier, PromotionThresholds
)

# ---------------------------------------------------------------------------
# Candidate state — updated manually after each stress test or analysis.
# source_diversity = number of DISTINCT platforms/families that independently
#                   surfaced this transition. GitHub x5 = diversity of 1.
# ---------------------------------------------------------------------------
CANDIDATE_STATE = [
    {
        "candidate": "DATA_PROVISION",
        "rediscovery_count": 3,
        "semantic_cohesion": 0.95,
        "source_diversity": 3,        # TRANSACTION (SauceDemo), DISCOVERY (GitHub), ONBOARDING (HuggingFace)
        "stress_test_passed": True,   # Survived Field Research Round 1
        "prediction": "First Primitive Candidate to reach ELIGIBLE_FOR_REVIEW",
    },
    {
        "candidate": "AUTHENTICATE",
        "rediscovery_count": 1,
        "semantic_cohesion": 0.00,    # DEAD: Swallowed by DATA_PROVISION (n=102 dominant is NO_DATA -> DATA_PROVIDED)
        "source_diversity": 2,
        "stress_test_passed": False,
        "prediction": "DEAD. Heuristic engine classified AUTHENTICATE actions as DATA_PROVISION.",
    },
    {
        "candidate": "ENTITY_RESOLUTION",
        "rediscovery_count": 1,
        "semantic_cohesion": 1.00,
        "source_diversity": 1,        # DISCOVERY only
        "stress_test_passed": False,
        "prediction": None,
    },
    {
        "candidate": "QUERY_ENTRY",
        "rediscovery_count": 1,
        "semantic_cohesion": 0.95,
        "source_diversity": 1,        # DISCOVERY only
        "stress_test_passed": False,
        "prediction": None,
    },
    {
        "candidate": "FLOW_ENTRY",
        "rediscovery_count": 1,
        "semantic_cohesion": 0.92,
        "source_diversity": 1,        # TRANSACTION only
        "stress_test_passed": False,
        "prediction": None,
    },
    {
        "candidate": "GOAL_COMPLETION",
        "rediscovery_count": 1,
        "semantic_cohesion": 1.00,
        "source_diversity": 1,        # TRANSACTION only
        "stress_test_passed": False,
        "prediction": "May be universal — every goal-directed workflow terminates somewhere.",
    },
    {
        "candidate": "WORKFLOW_STEP",
        "rediscovery_count": 1,
        "semantic_cohesion": 1.00,
        "source_diversity": 1,        # TRANSACTION only
        "stress_test_passed": False,
        "prediction": "May merge with GOAL_COMPLETION under a broader PROGRESS primitive.",
    },
]


TIER_ICONS = {
    PromotionTier.ELIGIBLE_FOR_REVIEW: "📋",
    PromotionTier.STRONG_CANDIDATE:    "⬆️ ",
    PromotionTier.CANDIDATE:           "🔬",
}


def run():
    t = PromotionThresholds()

    print(f"\n========================================================")
    print(f" P5G: PROMOTION GATE REPORT")
    print(f"========================================================")
    print(f" Thresholds for ELIGIBLE_FOR_REVIEW:")
    print(f"   rediscovery    >= {t.review_rediscovery}")
    print(f"   cohesion       >= {t.review_cohesion:.0%}")
    print(f"   source_diversity >= {t.review_source_diversity}  (distinct platforms/families)")
    print(f"   stress_test    = passed")
    print(f"\n NOTE: ELIGIBLE_FOR_REVIEW requires human evidence review.")
    print(f"       Numbers qualify. They do not grant citizenship.")
    print(f"========================================================\n")

    results = []
    for c in CANDIDATE_STATE:
        result = evaluate_candidate(
            candidate=c["candidate"],
            rediscovery_count=c["rediscovery_count"],
            semantic_cohesion=c["semantic_cohesion"],
            source_diversity=c["source_diversity"],
            stress_test_passed=c["stress_test_passed"],
        )
        results.append((result, c))

    # Header
    print(f" {'':2} {'Candidate':<22} {'Tier':<22} {'Rediscov':>8} {'Diversity':>9} {'Cohesion':>8} {'Stress':>6}")
    print(f" {'-'*88}")

    for result, c in results:
        icon = TIER_ICONS[result.current_tier]
        print(f" {icon} {result.candidate:<22} {result.current_tier.value:<22}"
              f" {result.rediscovery:>4}/{t.review_rediscovery:<3}"
              f" {result.source_diversity:>5}/{t.review_source_diversity:<3}"
              f" {result.cohesion:>7.0%}"
              f" {'YES' if result.stress_test else 'NO':>6}")

        if result.missing_for_review:
            print(f"    \u2514 Missing: {', '.join(result.missing_for_review)}")
        if c.get("prediction"):
            print(f"    \u2514 Prediction: {c['prediction']}")
        print()

    # Gate summary
    eligible  = sum(1 for r, _ in results if r.current_tier == PromotionTier.ELIGIBLE_FOR_REVIEW)
    strong    = sum(1 for r, _ in results if r.current_tier == PromotionTier.STRONG_CANDIDATE)
    candidate = sum(1 for r, _ in results if r.current_tier == PromotionTier.CANDIDATE)

    print(f"========================================================")
    print(f" GATE SUMMARY")
    print(f"   ELIGIBLE_FOR_REVIEW : {eligible}")
    print(f"   STRONG_CANDIDATE    : {strong}")
    print(f"   CANDIDATE           : {candidate}")
    print(f"\n No candidate is currently eligible for review.")
    print(f" The Birth Ledger exists to track births. Not to declare citizenship.")
    print(f"========================================================")

    # Save
    out_dir = ROOT / "reports" / "primitives"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "promotion_gate.json"
    out_data = [
        {
            "candidate": r.candidate,
            "tier": r.current_tier.value,
            "rediscovery": r.rediscovery,
            "source_diversity": r.source_diversity,
            "cohesion": r.cohesion,
            "stress_test": r.stress_test,
            "missing_for_review": r.missing_for_review,
            "prediction": c.get("prediction"),
        }
        for r, c in results
    ]
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n Report saved to: {out_path}")

    # --- Append to candidate_history.json ---
    # Every run is a timestamped data point.
    # Produces the Trajectory for the paper: "How did candidates evolve under pressure?"
    from datetime import date as _date
    history_path = out_dir / "candidate_history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {}

    today = str(_date.today())
    changed = False
    for r, c in results:
        name = r.candidate
        snapshots = history.get(name, [])
        last = snapshots[-1] if snapshots else {}
        snapshot = {
            "date": today,
            "rediscovery": r.rediscovery,
            "source_diversity": r.source_diversity,
            "cohesion": r.cohesion,
            "tier": r.current_tier.value,
        }
        # Only append if something changed since last snapshot
        if (last.get("rediscovery") != snapshot.get("rediscovery")
                or last.get("source_diversity") != snapshot.get("source_diversity")
                or last.get("cohesion") != snapshot.get("cohesion")
                or last.get("tier") != snapshot.get("tier")):
            history.setdefault(name, []).append(snapshot)
            changed = True

    if changed:
        history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f" History updated  : {history_path}")
    else:
        print(f" History unchanged: no new data points since last run.")


if __name__ == "__main__":
    run()
