"""
Phase Y1 -- Opportunity Yield Audit
Per-URL funnel: candidates -> quality -> coverage -> validation -> accepted
Writes reports/yield_audit.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler import StateFamilyBuilder, OpportunityGraphGenerator, CoverageGates
from training.compiler.opportunity_graph_generator import (
    MAX_PER_STATE_FAMILY_ROLE,
    MIN_QUALITY_SCORE,
)
from training.compiler.difficulty_estimator import DifficultyEstimator
from training.compiler.task_template_library import TaskTemplateLibrary
from training.compiler.label_builder import LabelBuilder
from training.compiler.rejection_gates import RejectionGates
from training.compiler.state_family_builder import _PASSWORD_TERMS

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


def _has_password_textbox(ax_graph: Dict[str, Any]) -> bool:
    for n in ax_graph.get("nodes", []):
        if n.get("role") in ("textbox", "combobox", "searchbox"):
            name = n.get("name", "").lower()
            if any(t in name for t in _PASSWORD_TERMS):
                return True
    return False


def _count_named_candidates(ax_graph: Dict[str, Any]) -> int:
    n = 0
    for node in ax_graph.get("nodes", []):
        role = node.get("role", "").lower()
        if node.get("idx") is None:
            continue
        if not node.get("name", "").strip():
            continue
        if role in INTERACTION_ROLES or role in EXTRACTION_ROLES:
            n += 1
    return n


def _zero_yield_reason(row: Dict[str, Any]) -> Optional[str]:
    if row.get("error"):
        return "fetch_error"
    if row["opportunities_found"] == 0:
        if row.get("unnamed_interactive_nodes", 0) > 0:
            return "unnamed_nodes"
        return "no_named_candidates"
    if row["accepted"] > 0:
        return None
    if row.get("taxonomy_block"):
        return "taxonomy_unknown"
    if row.get("auth_missing_password"):
        return "missing_password"
    if row.get("bot_wall"):
        return "bot_wall"
    if row["rejected_quality"] > 0 and row["rejected_quality"] >= row["opportunities_found"]:
        return "quality"
    if row["rejected_role_cap"] > 0 and (
        row["rejected_quality"] + row["rejected_role_cap"] >= row["opportunities_found"]
    ):
        return "role_cap"
    if row["rejected_coverage"] > 0:
        return "coverage"
    if row["rejected_validation"] > 0:
        return "validation"
    return "unknown"


def audit_url(
    ax_graph: Dict[str, Any],
    url: str,
    category: str,
    *,
    cumulative_gates: Optional[CoverageGates] = None,
) -> Dict[str, Any]:
    builder = StateFamilyBuilder()
    zones_result = builder.identify_zones(ax_graph)
    family_data = builder.identify_family(ax_graph)
    state_family = family_data["state_family"]
    confidence = family_data.get("confidence", 1.0)

    # Per-URL isolated gates (intrinsic yield)
    gates = CoverageGates()
    gen = OpportunityGraphGenerator(gates)
    diff_est = DifficultyEstimator()
    templates = TaskTemplateLibrary()

    row: Dict[str, Any] = {
        "url": url,
        "category": category,
        "regions": len(zones_result.get("zones", [])),
        "state_family": state_family,
        "family_confidence": confidence,
        "ax_nodes": len(ax_graph.get("nodes", [])),
        "unnamed_interactive_nodes": 0,
        "opportunities_found": 0,
        "rejected_quality": 0,
        "rejected_coverage": 0,
        "rejected_role_cap": 0,
        "rejected_validation": 0,
        "rejected_taxonomy": 0,
        "accepted": 0,
        "accepted_isolated": 0,
        "accepted_cumulative": 0,
        "rejected_coverage_cumulative": 0,
        "taxonomy_block": state_family in UNCLASSIFIED_FAMILIES,
        "auth_missing_password": category == "auth" and not _has_password_textbox(ax_graph),
        "bot_wall": category == "auth"
        and state_family in UNCLASSIFIED_FAMILIES
        and not _has_password_textbox(ax_graph),
        "quality_scores_sample": [],
    }

    for node in ax_graph.get("nodes", []):
        role = node.get("role", "").lower()
        if role in INTERACTION_ROLES and node.get("idx") is not None:
            if not node.get("name", "").strip():
                row["unnamed_interactive_nodes"] += 1

    role_budget: Dict[str, int] = {}
    nodes = ax_graph.get("nodes", [])

    def _try_accept(opp: Dict[str, Any], opp_type: str) -> bool:
        if opp_type == "interaction":
            diff = diff_est.estimate(ax_graph, opp)
            goal = templates.generate_interaction_goal(opp)
            label = LabelBuilder.build_interaction_label(
                action="click", element_idx=opp["node"]
            )
            sample = {
                "id": str(uuid.uuid4()),
                "url": url,
                "state_family_data": family_data,
                "opportunity_data": opp,
                "task_type": "interaction",
                "goal": goal,
                "label": label,
                "difficulty": diff["difficulty"],
                "metrics": diff["metrics"],
                "ax_graph": ax_graph,
            }
        else:
            diff = diff_est.estimate(ax_graph, opp)
            goal = templates.generate_extraction_goal(opp)
            label = LabelBuilder.build_extraction_label(
                answers=[str(opp["node_ids"][0])], source_nodes=opp["node_ids"]
            )
            sample = {
                "id": str(uuid.uuid4()),
                "url": url,
                "state_family_data": family_data,
                "opportunity_data": opp,
                "task_type": "extraction",
                "goal": goal,
                "label": label,
                "difficulty": diff["difficulty"],
                "metrics": diff["metrics"],
                "ax_graph": ax_graph,
            }
        return RejectionGates.pass_all_gates(sample)

    for node in nodes:
        role = node.get("role", "").lower()
        name = node.get("name", "").strip()
        node_id = node.get("idx")
        if node_id is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        row["opportunities_found"] += 1
        is_interaction = role in INTERACTION_ROLES
        budget_key = f"{state_family}:{role}"
        if not is_interaction:
            budget_key = f"{state_family}:{role}:extraction"

        if role_budget.get(budget_key, 0) >= MAX_PER_STATE_FAMILY_ROLE:
            row["rejected_role_cap"] += 1
            continue

        task_family = (
            f"{state_family}_{role}"
            if is_interaction
            else f"{state_family}_{role}_extraction"
        )
        scarcity = gates.calculate_scarcity(state_family, task_family)
        if is_interaction:
            q = gen._interaction_quality(role, name, state_family, confidence, scarcity)
        else:
            q = gen._extraction_quality(role, name, state_family, confidence, scarcity)

        if len(row["quality_scores_sample"]) < 5:
            row["quality_scores_sample"].append(
                {"role": role, "name": name[:60], "quality": round(q, 3)}
            )

        if q < MIN_QUALITY_SCORE:
            row["rejected_quality"] += 1
            continue

        if state_family in UNCLASSIFIED_FAMILIES:
            row["rejected_taxonomy"] += 1
            continue

        if not gates.is_opportunity_allowed(state_family, task_family):
            row["rejected_coverage"] += 1
            continue

        opp: Dict[str, Any]
        if is_interaction:
            opp = {
                "node": node_id,
                "role": role,
                "name": name,
                "state_family": state_family,
                "family_hash": family_data["family_hash"],
                "opportunity_type": "interaction",
                "task_family": task_family,
                "quality_score": round(q, 3),
            }
        else:
            opp = {
                "node_ids": [node_id],
                "role": role,
                "name": name,
                "state_family": state_family,
                "family_hash": family_data["family_hash"],
                "opportunity_type": "extraction",
                "task_family": task_family,
                "quality_score": round(q, 3),
            }

        if not _try_accept(opp, "interaction" if is_interaction else "extraction"):
            row["rejected_validation"] += 1
            continue

        row["accepted"] += 1
        row["accepted_isolated"] += 1
        role_budget[budget_key] = role_budget.get(budget_key, 0) + 1
        gates.total_samples += 1
        gates.state_family_counts[state_family] += 1
        gates.task_family_counts[task_family] += 1

    # Cumulative coverage simulation (matches full recompile batch)
    if cumulative_gates is not None:
        gen_cum = OpportunityGraphGenerator(cumulative_gates)
        opps_cum = gen_cum.generate(ax_graph, family_data)
        all_cum = opps_cum["interaction_opportunities"] + opps_cum[
            "extraction_opportunities"
        ]
        row["accepted_cumulative"] = len(all_cum)
        row["rejected_coverage_cumulative"] = max(
            0, row["accepted_isolated"] - row["accepted_cumulative"]
        )

    row["zero_yield_reason"] = _zero_yield_reason(row)
    return row


async def run_yield_audit() -> Dict[str, Any]:
    per_url: List[Dict[str, Any]] = []
    cumulative = CoverageGates()
    errors = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url, category in TARGETS:
            row: Dict[str, Any] = {
                "url": url,
                "category": category,
                "error": None,
            }
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                ax_graph = await build_graph_from_page(page)
                await context.close()

                audited = audit_url(
                    ax_graph, url, category, cumulative_gates=cumulative
                )
                row = audited
                # Update cumulative counters as batch recompile would
                for _ in range(row["accepted_cumulative"]):
                    sf = row["state_family"]
                    cumulative.state_family_counts[sf] += 1
                    cumulative.total_samples += 1
            except Exception as e:
                row["error"] = str(e)[:300]
                row["zero_yield_reason"] = "fetch_error"
                errors += 1
            per_url.append(row)
            z = row.get("zero_yield_reason") or "ok"
            acc = row.get("accepted", 0)
            found = row.get("opportunities_found", 0)
            print(
                f"{category:<10} {acc:>2} accepted / {found:>3} found  [{z}]  {url[:50]}"
            )

        await browser.close()

    zero_domains = [r for r in per_url if r.get("accepted", 0) == 0 and not r.get("error")]
    reason_counter = Counter(r.get("zero_yield_reason") for r in zero_domains)

    category_breakdown = Counter()
    for r in zero_domains:
        reason = r.get("zero_yield_reason") or "unknown"
        if reason == "quality":
            category_breakdown["quality_reject"] += 1
        elif reason == "missing_password":
            category_breakdown["missing_password"] += 1
        elif reason == "bot_wall":
            category_breakdown["bot_wall"] += 1
        elif reason == "taxonomy_unknown":
            category_breakdown["taxonomy_unknown"] += 1
        elif reason == "coverage":
            category_breakdown["coverage_reject"] += 1
        elif reason in ("no_named_candidates", "unnamed_nodes"):
            category_breakdown["ax_sparse"] += 1
        elif reason == "role_cap":
            category_breakdown["role_cap"] += 1
        elif reason == "validation":
            category_breakdown["validation_reject"] += 1
        else:
            category_breakdown[reason] += 1

    totals = Counter()
    for r in per_url:
        if r.get("error"):
            continue
        for k in (
            "opportunities_found",
            "rejected_quality",
            "rejected_coverage",
            "rejected_role_cap",
            "rejected_taxonomy",
            "rejected_validation",
            "accepted",
            "accepted_isolated",
        ):
            totals[k] += r.get(k, 0)

    report = {
        "schema": "browsermind.yield_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "isolated_coverage_per_url + cumulative_simulation",
        "domains_targeted": len(TARGETS),
        "domains_ok": len(TARGETS) - errors,
        "domains_zero_yield": len(zero_domains),
        "zero_yield_rate": round(len(zero_domains) / len(TARGETS), 4),
        "samples_per_domain_avg": round(totals["accepted"] / len(TARGETS), 3),
        "samples_per_domain_isolated_avg": round(
            totals["accepted_isolated"] / len(TARGETS), 3
        ),
        "funnel_totals": dict(totals),
        "zero_yield_reasons": dict(reason_counter.most_common()),
        "zero_yield_category_breakdown": dict(category_breakdown.most_common()),
        "target_yield": {
            "samples_per_domain_min": 3,
            "samples_per_domain_target": 5,
            "projected_at_target": len(TARGETS) * 3,
        },
        "per_url": per_url,
    }
    return report


async def main():
    report = await run_yield_audit()
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "yield_audit.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== YIELD AUDIT SUMMARY ==========")
    print(json.dumps(
        {
            "zero_yield_rate": report["zero_yield_rate"],
            "samples_per_domain_avg": report["samples_per_domain_avg"],
            "samples_per_domain_isolated_avg": report["samples_per_domain_isolated_avg"],
            "funnel_totals": report["funnel_totals"],
            "zero_yield_category_breakdown": report["zero_yield_category_breakdown"],
        },
        indent=2,
    ))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
