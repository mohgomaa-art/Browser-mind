"""
Phase DISC-2.5 / DISC-2.6 -- Capability Competition + Death Report

DISC-2.5: per-zone score competition (no classifier override) + lost_to_* aggregates
DISC-2.6: death_stage per capability + checkout value autopsy

Writes reports/capability_competition_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.capability_discoverability import (
    boundary_passed,
    capabilities_for_url,
    discovery_signal_detected,
    unique_seed_url_list,
)
from training.capability_taxonomy import (
    MIN_MATCH_STRENGTH,
    build_zone_text_map,
    competition_scores,
    competition_winner,
    rank_capabilities,
    zone_competition_scores,
)
from training.compiler import CoverageGates, OpportunityGraphGenerator, StateFamilyBuilder
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.graph_builder import build_graph_from_page

INTERACTION_ROLES = frozenset(
    {"button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem"}
)
EXTRACTION_ROLES = frozenset({"article", "list", "table", "row", "heading", "main"})

FOCAL_CAPS = (
    "upload",
    "job_application",
    "checkout",
    "content_creation",
)

COMPETITOR_CAPS = (
    "upload",
    "job_application",
    "checkout",
    "content_creation",
    "search",
    "auth_recovery",
    "navigation",
    "multi_field_form",
    "marketing",
    "legal",
    "settings",
    "filter",
    "account_creation",
)


def _death_stage(
    signal: int,
    boundary: int,
    classified: int,
    accepted: int,
) -> str:
    if signal == 0:
        return "discovery"
    if boundary == 0:
        return "boundary"
    if classified == 0:
        return "classification"
    if accepted == 0:
        return "quality"
    return "healthy"


def analyze_page(
    url: str,
    ax_graph: Dict[str, Any],
    *,
    zone_samples: List[Dict[str, Any]],
    lost_to: Dict[str, Counter],
    lost_to_competition: Dict[str, Counter],
    funnel: Dict[str, Dict[str, int]],
    checkout_rejects: List[Dict[str, Any]],
) -> None:
    builder = StateFamilyBuilder()
    family_data = builder.identify_family(ax_graph)
    state_family = family_data["state_family"]
    confidence = float(family_data.get("confidence", 0.9))
    zones = builder.identify_zones(ax_graph).get("zones", [])
    zone_text_by_idx = build_zone_text_map(ax_graph, zones)
    nodes_by_idx = {n["idx"]: n for n in ax_graph.get("nodes", []) if n.get("idx") is not None}

    gates = CoverageGates()
    gen = OpportunityGraphGenerator(gates)
    headings = gen._heading_context(ax_graph)
    generated = gen.generate(ax_graph, family_data)
    accepted_keys = set()
    for opp in generated.get("interaction_opportunities", []):
        accepted_keys.add((url, opp["node"], opp.get("role", "")))
    for opp in generated.get("extraction_opportunities", []):
        for nid in opp.get("node_ids", []):
            accepted_keys.add((url, nid, opp.get("role", "")))

    # Zone-level competition samples (cap at 40 total)
    for zi, zone in enumerate(zones):
        if len(zone_samples) >= 40:
            break
        zone_nodes = [
            nodes_by_idx[i]
            for i in zone.get("node_idxs", [])
            if i in nodes_by_idx
        ]
        texts = [
            n.get("name", "").strip()
            for n in zone_nodes
            if n.get("name", "").strip()
        ]
        if not texts:
            continue
        scores = zone_competition_scores(
            zone_texts=texts,
            state_family=zone.get("family", state_family),
            nodes=zone_nodes,
            heading_context=headings,
        )
        if not scores:
            continue
        winner, w_score = competition_winner(scores)
        top = dict(sorted(scores.items(), key=lambda x: -x[1])[:6])
        zone_samples.append(
            {
                "url": url,
                "zone_index": zi,
                "zone_family": zone.get("family", state_family),
                "scores": top,
                "winner": winner,
                "winner_score": round(w_score, 4),
                "seed_capabilities": capabilities_for_url(url),
            }
        )

    for node in ax_graph.get("nodes", []):
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        node_idx = node.get("idx")
        if node_idx is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        opp_type = "interaction" if role in INTERACTION_ROLES else "extraction"
        zone_texts = zone_text_by_idx.get(node_idx, [])
        key = (url, node_idx, role)

        comp = competition_scores(
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opp_type,
            heading_context=headings,
            zone_texts=zone_texts,
        )
        comp_winner, comp_score = competition_winner(comp)

        ranked = rank_capabilities(
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opp_type,
            heading_context=headings,
            zone_texts=zone_texts,
        )
        clf_winner = ranked[0][0]

        scored = gen._score_opportunity(
            role=role,
            name=name,
            state_family=state_family,
            confidence=confidence,
            scarcity=gates.calculate_scarcity(
                state_family,
                f"{state_family}_{role}"
                if opp_type == "interaction"
                else f"{state_family}_{role}_extraction",
            ),
            opportunity_type=opp_type,
            node=node,
            ax_graph=ax_graph,
            heading_context=headings,
            zone_texts=zone_texts,
        )
        accepted = key in accepted_keys and clf_winner == scored.get("capability")

        for cap in FOCAL_CAPS:
            sig = discovery_signal_detected(cap, name, role=role, state_family=state_family)
            bnd = boundary_passed(
                cap,
                name,
                role=role,
                state_family=state_family,
                opportunity_type=opp_type,
                heading_context=headings,
                zone_texts=zone_texts,
            )
            if sig:
                funnel[cap]["signal"] += 1
            if bnd:
                funnel[cap]["boundary"] += 1
            if clf_winner == cap:
                funnel[cap]["classified"] += 1
            if accepted and clf_winner == cap:
                funnel[cap]["accepted"] += 1

            # Competition loss: had boundary/signal but classifier picked another cap
            if (sig or bnd) and clf_winner != cap:
                lost_to[cap][clf_winner] += 1

            # Pure score competition loss (no inference)
            focal_score = comp.get(cap, 0.0)
            if focal_score >= MIN_MATCH_STRENGTH and comp_winner != cap:
                lost_to_competition[cap][comp_winner] += 1

        if clf_winner == "checkout" and not accepted:
            checkout_rejects.append(
                {
                    "url": url,
                    "target": name[:80],
                    "role": role,
                    "quality_score": scored.get("quality_score"),
                    "task_value": scored.get("task_value"),
                    "learning_stage": scored.get("learning_stage"),
                    "task_value_factors": scored.get("task_value_factors"),
                    "actionability": scored.get("actionability"),
                    "competition_scores": {
                        k: comp[k]
                        for k in sorted(comp, key=lambda c: -comp[c])[:5]
                    },
                    "competition_winner": comp_winner,
                    "classifier_winner": clf_winner,
                }
            )


def _avg_factor(rows: List[Dict[str, Any]], path: str) -> float:
    vals = []
    for r in rows:
        if path == "quality_score":
            v = r.get("quality_score")
        elif path == "task_value":
            v = r.get("task_value")
        else:
            v = (r.get("task_value_factors") or {}).get(path)
        if v is not None:
            vals.append(float(v))
    return round(sum(vals) / len(vals), 4) if vals else 0.0


async def run_report(timeout_ms: int = 22000) -> Dict[str, Any]:
    urls = unique_seed_url_list()
    zone_samples: List[Dict[str, Any]] = []
    lost_to: Dict[str, Counter] = {c: Counter() for c in FOCAL_CAPS}
    lost_to_competition: Dict[str, Counter] = {c: Counter() for c in FOCAL_CAPS}
    funnel: Dict[str, Dict[str, int]] = {
        c: {"signal": 0, "boundary": 0, "classified": 0, "accepted": 0} for c in FOCAL_CAPS
    }
    checkout_rejects: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await asyncio.sleep(2)
                ax = await build_graph_from_page(page)
                await context.close()
                analyze_page(
                    url,
                    ax,
                    zone_samples=zone_samples,
                    lost_to=lost_to,
                    lost_to_competition=lost_to_competition,
                    funnel=funnel,
                    checkout_rejects=checkout_rejects,
                )
                print(f"OK  {url[:58]}")
            except Exception as e:
                errors.append({"url": url, "error": str(e)[:200]})
                print(f"ERR {url[:48]}  {e}")
        await browser.close()

    death_report: Dict[str, Any] = {}
    for cap in FOCAL_CAPS:
        f = funnel[cap]
        death_report[cap] = {
            "death_stage": _death_stage(
                f["signal"], f["boundary"], f["classified"], f["accepted"]
            ),
            "funnel": f,
            "lost_to_classifier": dict(lost_to[cap].most_common()),
            "lost_to_competition": dict(lost_to_competition[cap].most_common()),
        }

    checkout_autopsy = {
        "classified_not_accepted_count": len(checkout_rejects),
        "threshold": MIN_QUALITY_SCORE,
        "avg_quality_score": _avg_factor(checkout_rejects, "quality_score"),
        "avg_task_value": _avg_factor(checkout_rejects, "task_value"),
        "avg_factors": {
            "capability_prior": _avg_factor(checkout_rejects, "capability_prior"),
            "workflow_potential": _avg_factor(checkout_rejects, "workflow_potential"),
            "cross_site_value": _avg_factor(checkout_rejects, "cross_site_value"),
            "completion_probability": _avg_factor(checkout_rejects, "completion_probability"),
        },
        "diagnosis": (
            "If avg_quality < threshold -> quality gate; "
            "if task_value high but quality low -> actionability/confidence/rarity; "
            "if learning_stage=skip -> deprioritized capability."
        ),
        "sample_rejects": checkout_rejects[:15],
    }

    return {
        "schema": "browsermind.capability_competition_report.v1",
        "phase": "DISC-2.5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": (
            "Competition uses competition_scores() -- no force_capability override. "
            "Classifier path uses rank_capabilities() for lost_to_classifier."
        ),
        "urls_attempted": len(urls),
        "urls_failed": len(errors),
        "crawl_errors": errors,
        "zone_competition_samples": zone_samples,
        "competition_losses": {
            cap: {
                "lost_to_classifier": dict(lost_to[cap].most_common()),
                "lost_to_competition": dict(lost_to_competition[cap].most_common()),
            }
            for cap in FOCAL_CAPS
        },
        "death_report": death_report,
        "checkout_value_autopsy": checkout_autopsy,
        "lifecycle_summary": {
            cap: death_report[cap]["death_stage"] for cap in FOCAL_CAPS
        },
    }


async def main_async(args: argparse.Namespace) -> None:
    report = await run_report(timeout_ms=args.timeout_ms)
    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "capability_competition_report.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== DISC-2.6 DEATH REPORT ==========")
    print(json.dumps(report["lifecycle_summary"], indent=2))
    print("\n========== DISC-2.5 JOB APPLICATION LOSSES ==========")
    ja = report["competition_losses"]["job_application"]
    print("classifier:", ja["lost_to_classifier"])
    print("competition:", ja["lost_to_competition"])
    print("\n========== CHECKOUT AUTOPSY ==========")
    ca = report["checkout_value_autopsy"]
    print(
        f"n={ca['classified_not_accepted_count']} "
        f"avg_q={ca['avg_quality_score']} avg_tv={ca['avg_task_value']} "
        f"factors={ca['avg_factors']}"
    )
    print(f"\nWrote {out}")


def main():
    ap = argparse.ArgumentParser(description="DISC-2.5 Capability Competition Report")
    ap.add_argument("--timeout-ms", type=int, default=22000)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
