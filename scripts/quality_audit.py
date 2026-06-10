"""
Phase Y2 -- Quality Audit
Scores every named opportunity with full factor breakdown.
Surfaces accepted top-N and rejected near-miss band (0.40-0.60).

Writes reports/quality_audit.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler import StateFamilyBuilder, CoverageGates
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.compiler.quality_scoring import score_extraction, score_interaction

TARGETS = [
    ("https://github.com/login", "auth"),
    ("https://www.reddit.com/login", "auth"),
    ("https://www.linkedin.com/login", "auth"),
    ("https://discord.com/login", "auth"),
    ("https://www.netflix.com/login", "auth"),
    ("https://slack.com/signin", "auth"),
    ("https://www.dropbox.com/login", "auth"),
    ("https://www.twitch.tv/login", "auth"),
    ("https://www.google.com", "search"),
    ("https://www.bing.com", "search"),
    ("https://duckduckgo.com", "search"),
    ("https://www.youtube.com", "search"),
    ("https://www.amazon.com", "search"),
    ("https://www.ebay.com", "search"),
    ("https://en.wikipedia.org/wiki/Python_(programming_language)", "article"),
    ("https://www.nytimes.com", "article"),
    ("https://www.bbc.com", "article"),
    ("https://news.ycombinator.com", "article"),
    ("https://www.python.org", "nav"),
    ("https://www.github.com", "nav"),
    ("https://www.apple.com", "nav"),
    ("https://www.microsoft.com", "nav"),
    ("https://stackoverflow.com", "nav"),
    ("https://www.walmart.com", "ecommerce"),
    ("https://www.target.com", "ecommerce"),
    ("https://www.imdb.com", "ecommerce"),
    ("https://www.zillow.com", "ecommerce"),
    ("https://github.com/settings/profile", "settings"),
    ("https://docs.python.org/3/", "docs"),
    ("https://developer.mozilla.org/en-US/", "docs"),
    ("https://pypi.org", "docs"),
    ("https://huggingface.co", "docs"),
    ("https://www.reddit.com", "feed"),
    ("https://news.google.com", "feed"),
    ("https://github.com/signup", "signup"),
    ("https://www.reddit.com/register", "signup"),
]
UNCLASSIFIED_FAMILIES = frozenset(
    {"generic_interactive", "generic_page", "empty_page", "root_fallback"}
)
INTERACTION_ROLES = frozenset(
    {"button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem"}
)
EXTRACTION_ROLES = frozenset({"article", "list", "table", "row", "heading", "main"})

BOUNDARY_LOW = 0.40
BOUNDARY_HIGH = 0.60
TOP_ACCEPTED = 50
TOP_REJECTED_NEAR = 50


def _rejection_reason(
    scored: Dict[str, Any],
    state_family: str,
    *,
    role_cap_blocked: bool = False,
) -> str:
    q = scored["quality_score"]
    if role_cap_blocked:
        return "role_cap_exceeded"
    if state_family in UNCLASSIFIED_FAMILIES:
        return "taxonomy_unclassified"
    if q < MIN_QUALITY_SCORE:
        tags = scored.get("semantic_tags", {})
        if tags.get("high_value_keyword") and q >= BOUNDARY_LOW:
            return "quality_below_threshold_high_value_near_miss"
        if tags.get("low_value_nav_keyword"):
            return "quality_below_threshold_low_value_nav"
        return "quality_below_threshold"
    return "accepted"


def _entry(
    url: str,
    category: str,
    state_family: str,
    family_confidence: float,
    node_id: int,
    role: str,
    name: str,
    opp_type: str,
    scored: Dict[str, Any],
    rejection_reason: str,
) -> Dict[str, Any]:
    return {
        "url": url,
        "category": category,
        "state_family": state_family,
        "family_confidence": family_confidence,
        "target": name,
        "role": role,
        "node_idx": node_id,
        "opportunity_type": opp_type,
        "quality_score": scored["quality_score"],
        "rejection_reason": rejection_reason,
        "factors": scored["factors"],
        "penalties": scored["penalties"],
        "semantic_tags": scored["semantic_tags"],
        "distance_to_threshold": round(scored["quality_score"] - MIN_QUALITY_SCORE, 4),
    }


def collect_candidates(
    ax_graph: Dict[str, Any],
    url: str,
    category: str,
    family_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    gates = CoverageGates()
    state_family = family_data["state_family"]
    confidence = family_data.get("confidence", 1.0)
    rows: List[Dict[str, Any]] = []
    role_seen: Counter = Counter()

    for node in ax_graph.get("nodes", []):
        role = node.get("role", "").lower()
        name = node.get("name", "").strip()
        node_id = node.get("idx")
        if node_id is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        is_interaction = role in INTERACTION_ROLES
        budget_key = f"{state_family}:{role}" if is_interaction else f"{state_family}:{role}:extraction"
        role_cap_blocked = role_seen[budget_key] >= 3

        task_family = (
            f"{state_family}_{role}"
            if is_interaction
            else f"{state_family}_{role}_extraction"
        )
        scarcity = gates.calculate_scarcity(state_family, task_family)

        if is_interaction:
            scored = score_interaction(role, name, state_family, confidence, scarcity)
            opp_type = "interaction"
        else:
            scored = score_extraction(role, name, state_family, confidence, scarcity)
            opp_type = "extraction"

        reason = _rejection_reason(scored, state_family, role_cap_blocked=role_cap_blocked)
        if scored["passes_threshold"] and not role_cap_blocked and state_family not in UNCLASSIFIED_FAMILIES:
            reason = "accepted"

        rows.append(
            _entry(
                url,
                category,
                state_family,
                confidence,
                node_id,
                role,
                name,
                opp_type,
                scored,
                reason,
            )
        )
        if reason == "accepted":
            role_seen[budget_key] += 1

    return rows


async def run_quality_audit() -> Dict[str, Any]:
    builder = StateFamilyBuilder()
    all_rows: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url, category in TARGETS:
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                ax = await build_graph_from_page(page)
                await context.close()

                fam = builder.identify_family(ax)
                rows = collect_candidates(ax, url, category, fam)
                all_rows.extend(rows)
                acc = sum(1 for r in rows if r["rejection_reason"] == "accepted")
                near = sum(
                    1
                    for r in rows
                    if BOUNDARY_LOW <= r["quality_score"] < MIN_QUALITY_SCORE
                )
                print(f"{category:<10} {len(rows):>3} scored  {acc:>2} accepted  {near:>2} near-miss  {url[:48]}")
            except Exception as e:
                print(f"ERROR {url}: {e}")
        await browser.close()

    accepted = [r for r in all_rows if r["rejection_reason"] == "accepted"]
    accepted.sort(key=lambda r: r["quality_score"], reverse=True)

    near_miss = [
        r
        for r in all_rows
        if BOUNDARY_LOW <= r["quality_score"] < MIN_QUALITY_SCORE
    ]
    near_miss.sort(key=lambda r: r["quality_score"], reverse=True)

    boundary_band = [
        r for r in all_rows if BOUNDARY_LOW <= r["quality_score"] <= BOUNDARY_HIGH
    ]
    boundary_band.sort(key=lambda r: r["quality_score"], reverse=True)

    low_rejects = [r for r in all_rows if r["quality_score"] < BOUNDARY_LOW]
    low_rejects.sort(key=lambda r: r["quality_score"])

    # False-negative risk: high-value keyword in near-miss
    fn_risk = [r for r in near_miss if r["semantic_tags"].get("high_value_keyword")]

    # True rejects in near-miss: nav/legal keywords
    true_reject = [r for r in near_miss if r["semantic_tags"].get("low_value_nav_keyword")]

    by_role_accepted = Counter(r["role"] for r in accepted)
    by_role_near = Counter(r["role"] for r in near_miss)

    factor_avg_accepted = _avg_factors(accepted)
    factor_avg_near = _avg_factors(near_miss)

    histogram = Counter()
    for r in all_rows:
        bucket = int(r["quality_score"] * 20) / 20  # 0.05 bins
        histogram[f"{bucket:.2f}"] += 1

    report = {
        "schema": "browsermind.quality_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": MIN_QUALITY_SCORE,
        "boundary_band": [BOUNDARY_LOW, BOUNDARY_HIGH],
        "totals": {
            "candidates_scored": len(all_rows),
            "accepted": len(accepted),
            "rejected_quality": sum(
                1 for r in all_rows if r["quality_score"] < MIN_QUALITY_SCORE
            ),
            "near_miss_0_40_to_0_50": len(near_miss),
            "in_boundary_band_0_40_to_0_60": len(boundary_band),
            "low_score_below_0_40": len(low_rejects),
        },
        "near_miss_analysis": {
            "high_value_keyword_count": len(fn_risk),
            "low_value_nav_keyword_count": len(true_reject),
            "high_value_near_miss_examples": fn_risk[:15],
            "scenario_hint": (
                "scenario_b_likely"
                if len(fn_risk) > len(true_reject)
                else "scenario_a_likely"
                if len(true_reject) > len(fn_risk) * 2
                else "mixed_review_needed"
            ),
        },
        "role_distribution": {
            "accepted": dict(by_role_accepted.most_common()),
            "near_miss_rejected": dict(by_role_near.most_common()),
        },
        "factor_averages": {
            "accepted": factor_avg_accepted,
            "near_miss_rejected": factor_avg_near,
        },
        "histogram_0_05_bins": dict(sorted(histogram.items())),
        "accepted_top_50": accepted[:TOP_ACCEPTED],
        "rejected_top_50_near_miss": near_miss[:TOP_REJECTED_NEAR],
        "rejected_lowest_20": low_rejects[:20],
    }
    return report


def _avg_factors(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not rows:
        return {}
    keys = ("task_relevance", "learnability", "actionability", "rarity", "family_confidence")
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = round(sum(r["factors"][k] for r in rows) / len(rows), 4)
    return out


async def main():
    report = await run_quality_audit()
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "quality_audit.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== QUALITY AUDIT SUMMARY ==========")
    print(json.dumps(
        {
            "totals": report["totals"],
            "near_miss_analysis": {
                "high_value_keyword_count": report["near_miss_analysis"]["high_value_keyword_count"],
                "low_value_nav_keyword_count": report["near_miss_analysis"]["low_value_nav_keyword_count"],
                "scenario_hint": report["near_miss_analysis"]["scenario_hint"],
            },
            "role_distribution": report["role_distribution"],
            "factor_averages": report["factor_averages"],
        },
        indent=2,
    ))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
