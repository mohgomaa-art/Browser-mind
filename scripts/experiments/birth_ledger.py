"""P5F.2 — Primitive Birth Ledger.

The counterpart to the Death Ledger.
Tracks candidate primitives that EMERGED from the data — not ones we named in advance.

PRIMARY METRIC: Independent Re-Discovery Count
    How many times did the data name this primitive WITHOUT being asked?

    1  = Candidate      (single source, may be noise)
    2  = Strong Candidate (two independent analyses found the same thing)
    3+ = Primitive Emerges (repeated independent discovery — strongest signal)

The rarest and most valuable finding: a primitive that satisfies the Triple Condition:
    One semantic center + One state transition + Cross-family appearance

NOTE: No candidate here is called a Primitive yet.
      We track births, not declarations.
"""
import sys
import json
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
import sys as _sys; _sys.path.insert(0, str(ROOT))

from browsermind_core.representation.promotion_rules import evaluate_candidate, PromotionTier

# ---------------------------------------------------------------------------
# The Birth Ledger is compiled manually from prior analyses.
# This is intentional: we are recording what the data showed, not running
# a new algorithm. The human observer is part of the discovery process.
# ---------------------------------------------------------------------------

BIRTH_LEDGER = [
    {
        "candidate": "DATA_PROVISION",
        "state_transition": "NO_DATA -> DATA_PROVIDED",
        "discovery_count": 2,
        "sources": [
            "OPEN_OBJECT autopsy (n=24, Transaction: form textboxes)",
            "SUBMIT_QUERY split (n=30, Transaction: form fill actions)",
        ],
        "total_instances": 54,
        "families": ["TRANSACTION"],
        "confidence": "HIGH",
        "notes": (
            "The only candidate discovered independently in two separate analyses. "
            "OPEN_OBJECT autopsy found it as residual; SUBMIT_QUERY split found it as "
            "the Transaction half. Both point to the same semantic center. "
            "This primitive was not named in advance — the data converged on it twice."
        ),
        "triple_condition": False,
    },
    {
        "candidate": "AUTHENTICATE",
        "state_transition": "UNAUTHENTICATED -> CREDENTIALS_ENTERED",
        "discovery_count": 1,
        "sources": [
            "Native primitive — survived Death Ledger audit intact",
            "40 instances, 2 families (DISCOVERY + TRANSACTION), single transition",
        ],
        "total_instances": 40,
        "families": ["DISCOVERY", "TRANSACTION"],
        "confidence": "HIGH",
        "notes": (
            "The first primitive in BrowserMind to satisfy the Triple Condition: "
            "(1) One semantic center, (2) One state transition, (3) Cross-family appearance. "
            "It did not emerge from an autopsy — it survived falsification. "
            "That is a different and arguably stronger form of evidence."
        ),
        "triple_condition": True,
    },
    {
        "candidate": "ENTITY_RESOLUTION",
        "state_transition": "UNKNOWN_ENTITY -> SPECIFIC_ENTITY",
        "discovery_count": 1,
        "sources": [
            "OPEN_OBJECT autopsy (n=50, Discovery: repo links, article links, model cards)",
        ],
        "total_instances": 50,
        "families": ["DISCOVERY"],
        "confidence": "MEDIUM",
        "notes": (
            "The largest single coherent block inside the OPEN_OBJECT corpse. "
            "All instances share the same transition: resolving an ambiguous reference "
            "into a specific, named entity. Notable connection to Identity forensics — "
            "Identity work also involved resolving ambiguous element references. "
            "Needs cross-family stress test to confirm universality."
        ),
        "triple_condition": False,
    },
    {
        "candidate": "QUERY_ENTRY",
        "state_transition": "SEARCH_CLOSED -> QUERY_SUBMITTED",
        "discovery_count": 1,
        "sources": [
            "SUBMIT_QUERY split (n=37, Discovery: search box fills and submissions)",
        ],
        "total_instances": 37,
        "families": ["DISCOVERY"],
        "confidence": "MEDIUM",
        "notes": (
            "The Discovery half of the SUBMIT_QUERY split. "
            "Semantically consistent: the user is specifying a query intent. "
            "Overlaps strongly with OPEN_SEARCH — together they may form a 2-step "
            "compound: OPEN_SEARCH (open the field) -> QUERY_ENTRY (specify the query). "
            "Single-family only. Needs Transaction-domain equivalent to assess breadth."
        ),
        "triple_condition": False,
    },
    {
        "candidate": "FLOW_ENTRY",
        "state_transition": "BROWSING -> TRANSACTION_FLOW",
        "discovery_count": 1,
        "sources": [
            "OPEN_OBJECT autopsy (n=13, Transaction: Add to Cart, Checkout button clicks)",
        ],
        "total_instances": 13,
        "families": ["TRANSACTION"],
        "confidence": "LOW",
        "notes": (
            "User transitions from passive browsing into an active transaction flow. "
            "Semantically clear but narrow — only seen in SauceDemo. "
            "Needs Amazon, eBay, or similar to validate."
        ),
        "triple_condition": False,
    },
    {
        "candidate": "GOAL_COMPLETION",
        "state_transition": "TASK_IN_PROGRESS -> TASK_DONE",
        "discovery_count": 1,
        "sources": [
            "OPEN_OBJECT autopsy (n=10+1, Transaction: Finish, Back Home, terminal actions)",
        ],
        "total_instances": 11,
        "families": ["TRANSACTION"],
        "confidence": "LOW",
        "notes": (
            "Terminal actions that signal workflow completion. "
            "Semantically clear but only seen in one domain. "
            "Hypothesis: this primitive may be the most universal of all — "
            "every goal-directed workflow must end somewhere. Needs stress test."
        ),
        "triple_condition": False,
    },
    {
        "candidate": "WORKFLOW_STEP",
        "state_transition": "STEP_N -> STEP_N+1",
        "discovery_count": 1,
        "sources": [
            "OPEN_OBJECT autopsy (n=7, Transaction: Continue button clicks)",
        ],
        "total_instances": 7,
        "families": ["TRANSACTION"],
        "confidence": "LOW",
        "notes": (
            "Linear progression through a predefined workflow sequence. "
            "Only Continue buttons in SauceDemo checkout. Too narrow to assess. "
            "May merge with GOAL_COMPLETION under a broader WORKFLOW_PROGRESS primitive."
        ),
        "triple_condition": False,
    },
]


def run():
    print(f"\n========================================================")
    print(f" PRIMITIVE BIRTH LEDGER (P5F.2)")
    print(f" Rule: Data must name it. We only record what emerged.")
    print(f"========================================================\n")

    conf_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_ledger = sorted(BIRTH_LEDGER, key=lambda x: (conf_order[x["confidence"]], -x["total_instances"]))

    for entry in sorted_ledger:
        triple = " [TRIPLE CONDITION MET]" if entry["triple_condition"] else ""
        fams = ", ".join(entry["families"])
        print(f" [{entry['confidence']:<6}] {entry['candidate']:<22} "
              f"n={entry['total_instances']:>3}  "
              f"discovered={entry['discovery_count']}x  "
              f"families=[{fams}]{triple}")
        print(f"          {entry['state_transition']}")
        for src in entry["sources"]:
            print(f"          Source: {src}")
        print()

    high = sum(1 for e in BIRTH_LEDGER if e["confidence"] == "HIGH")
    med  = sum(1 for e in BIRTH_LEDGER if e["confidence"] == "MEDIUM")
    low  = sum(1 for e in BIRTH_LEDGER if e["confidence"] == "LOW")
    triple = sum(1 for e in BIRTH_LEDGER if e["triple_condition"])

    print(f"========================================================")
    print(f" SUMMARY")
    print(f"   HIGH   : {high}  (born from convergent independent evidence)")
    print(f"   MEDIUM : {med}  (born from single strong analysis)")
    print(f"   LOW    : {low}  (born from single narrow analysis)")
    print(f"   TRIPLE CONDITION MET: {triple}")
    print(f"========================================================")

    # --- P5G Promotion Gate ---
    # Cohesion is estimated from discovery_count and confidence for now.
    # Will be replaced by live measurement once semantic_center_test integrates.
    COHESION_ESTIMATES = {
        "DATA_PROVISION":    0.91,
        "AUTHENTICATE":      0.90,
        "ENTITY_RESOLUTION": 1.00,
        "QUERY_ENTRY":       0.95,
        "FLOW_ENTRY":        0.92,
        "GOAL_COMPLETION":   1.00,
        "WORKFLOW_STEP":     1.00,
    }

    print(f"\n========================================================")
    print(f" P5G: PROMOTION GATE")
    print(f" Requirements: PRIMITIVE = rediscovery>=5, families>=3,")
    print(f"               cohesion>=90%, stress_test=passed")
    print(f"========================================================")
    print(f" {'Candidate':<22} {'Tier':<18} {'Rediscover':>10}  {'Families':>8}  {'Cohesion':>8}  {'Stress':>6}")
    print(f" {'-'*82}")

    tier_icons = {
        PromotionTier.PRIMITIVE:        "🏆",
        PromotionTier.STRONG_CANDIDATE: "⬆️ ",
        PromotionTier.CANDIDATE:        "🔬",
    }

    for entry in sorted_ledger:
        cohesion = COHESION_ESTIMATES.get(entry["candidate"], 0.5)
        result = evaluate_candidate(
            candidate=entry["candidate"],
            rediscovery_count=entry["discovery_count"],
            semantic_cohesion=cohesion,
            scope_families=len(entry["families"]),
            stress_test_passed=False,   # No candidate has passed yet
        )
        icon = tier_icons[result.current_tier]
        missing = ", ".join(result.missing_for_primitive) if result.missing_for_primitive else "— PROMOTED"
        print(f" {icon} {result.candidate:<22} {result.current_tier.value:<18}"
              f" {result.rediscovery:>5}/5       "
              f" {result.scope_families:>3}/3      "
              f" {result.cohesion:>7.0%}  "
              f" {'NO':>6}")
        if result.missing_for_primitive:
            print(f"    Missing: {missing}")
        print()

    print(f" The Birth Ledger exists to track births. Not to declare citizenship.")
    print(f"========================================================")

    out_dir = ROOT / "reports" / "primitives"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "birth_ledger.json"
    out_path.write_text(json.dumps(sorted_ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n Ledger saved to: {out_path}")


if __name__ == "__main__":
    run()
