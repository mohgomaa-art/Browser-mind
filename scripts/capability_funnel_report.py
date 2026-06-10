"""
Phase COV-2 -- Capability Funnel Report

Per capability: where coverage dies in the pipeline.
  pages_seen -> regions_seen -> candidates_seen -> classified -> quality_rejected -> coverage_rejected -> accepted

Uses capability_seeds.json (capability-driven URLs) + taxonomy discovery signals (no hardcoded ifs).

Writes reports/capability_funnel_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.capability_discoverability import (
    FUNNEL_CAPABILITIES,
    capabilities_for_url,
    discovery_signal_match,
    get_discovery_spec,
    load_capability_seeds,
    region_matches_capability,
    seed_urls_for_capability,
    unique_seed_url_list,
)
from training.capability_discoverability import (
    boundary_passed,
    discovery_signal_detected,
)
from training.capability_taxonomy import build_zone_text_map, rank_capabilities
from training.compiler import CoverageGates, OpportunityGraphGenerator, StateFamilyBuilder
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.graph_builder import build_graph_from_page
from training.task_value_estimator import compose_quality_score, learning_stage

INTERACTION_ROLES = frozenset(
    {"button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem"}
)
EXTRACTION_ROLES = frozenset({"article", "list", "table", "row", "heading", "main"})
UNCLASSIFIED = frozenset({"generic_interactive", "generic_page", "empty_page", "root_fallback"})

COV2_TARGETS = {
    "upload": 30,
    "job_application": 20,
    "checkout": 10,
}


def _empty_funnel() -> Dict[str, Any]:
    return {
        "pages_seen": 0,
        "regions_seen": 0,
        "candidates_seen": 0,
        "classified": 0,
        "quality_rejected": 0,
        "coverage_rejected": 0,
        "accepted": 0,
        "diagnostics": {
            "seed_page_named_nodes": 0,
            "signal_matched": 0,
            "signal_matched_misclassified": 0,
            "classified_without_signal": 0,
            "skip_stage_rejected": 0,
            "role_cap_rejected": 0,
        },
    }


def _funnel_sets() -> Dict[str, Dict[str, Set]]:
    return {
        cap: {
            "pages": set(),
            "regions": set(),
            "candidates": set(),
            "classified": set(),
            "quality_rejected": set(),
            "coverage_rejected": set(),
            "accepted": set(),
            "signal_matched": set(),
            "signal_misclassified": set(),
            "classified_no_signal": set(),
            "skip_rejected": set(),
            "role_cap": set(),
            "seed_nodes": set(),
        }
        for cap in FUNNEL_CAPABILITIES
    }


def _candidate_key(url: str, node_idx: int, role: str) -> Tuple[str, int, str]:
    return (url, node_idx, role)


def trace_page(
    *,
    url: str,
    ax_graph: Dict[str, Any],
    funnel_sets: Dict[str, Dict[str, Set]],
    seed_caps: List[str],
) -> List[Dict[str, Any]]:
    """Trace all candidates; return per-row trace records for debugging."""
    builder = StateFamilyBuilder()
    zones_result = builder.identify_zones(ax_graph)
    family_data = builder.identify_family(ax_graph)
    state_family = family_data["state_family"]
    confidence = float(family_data.get("confidence", 0.9))
    zones = zones_result.get("zones", [])
    zone_text_by_idx = build_zone_text_map(ax_graph, zones)

    caps_on_page = seed_caps or capabilities_for_url(url)

    for cap in caps_on_page:
        if cap in funnel_sets:
            funnel_sets[cap]["pages"].add(url)

    for zi, zone in enumerate(zones):
        zfam = zone.get("family", "")
        region_key = (url, zi, zfam)
        for cap in caps_on_page:
            if cap not in funnel_sets:
                continue
            spec = get_discovery_spec(cap)
            families = spec.get("required_context", {}).get("state_families", [])
            if not families or region_matches_capability(cap, zfam):
                funnel_sets[cap]["regions"].add(region_key)

    gates = CoverageGates()
    gen = OpportunityGraphGenerator(gates)
    generated = gen.generate(ax_graph, family_data)
    accepted_keys = set()
    for opp in generated.get("interaction_opportunities", []):
        accepted_keys.add(_candidate_key(url, opp["node"], opp.get("role", "")))
    for opp in generated.get("extraction_opportunities", []):
        for nid in opp.get("node_ids", []):
            accepted_keys.add(_candidate_key(url, nid, opp.get("role", "")))

    node_in_zone: Dict[int, str] = {}
    for zi, zone in enumerate(zones):
        for idx in zone.get("node_idxs", []):
            node_in_zone[idx] = zone.get("family", "")

    traces: List[Dict[str, Any]] = []
    role_budget: Dict[str, int] = defaultdict(int)
    headings = gen._heading_context(ax_graph)

    for node in ax_graph.get("nodes", []):
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        node_idx = node.get("idx")
        if node_idx is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        opp_type = "interaction" if role in INTERACTION_ROLES else "extraction"
        key = _candidate_key(url, node_idx, role)
        zone_family = node_in_zone.get(node_idx, state_family)

        zone_texts = zone_text_by_idx.get(node_idx, [])
        ranked = rank_capabilities(
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opp_type,
            zone_texts=zone_texts,
        )
        best_cap = ranked[0][0]

        scored = gen._score_opportunity(
            role=role,
            name=name,
            state_family=state_family,
            confidence=confidence,
            scarcity=gates.calculate_scarcity(
                state_family,
                f"{state_family}_{role}" if opp_type == "interaction" else f"{state_family}_{role}_extraction",
            ),
            opportunity_type=opp_type,
            node=node,
            ax_graph=ax_graph,
            heading_context=headings,
        )
        q = scored["quality_score"]
        stage = scored.get("learning_stage", learning_stage(best_cap))
        task_family = (
            f"{state_family}_{role}"
            if opp_type == "interaction"
            else f"{state_family}_{role}_extraction"
        )
        budget_key = f"{state_family}:{role}" if opp_type == "interaction" else f"{state_family}:{role}:extraction"

        relevant_caps = set(caps_on_page) | {best_cap}
        for cap in FUNNEL_CAPABILITIES:
            if cap not in relevant_caps and cap != best_cap:
                if cap not in caps_on_page and not discovery_signal_match(
                    cap, name, role=role, state_family=state_family
                ):
                    continue
            if cap not in funnel_sets:
                continue

            fs = funnel_sets[cap]
            if url in seed_urls_for_capability(cap) or cap in caps_on_page:
                fs["seed_nodes"].add(key)

            sig = discovery_signal_detected(
                cap, name, role=role, state_family=state_family
            )
            bnd = boundary_passed(
                cap,
                name,
                role=role,
                state_family=state_family,
                opportunity_type=opp_type,
            )
            if sig or bnd:
                fs["signal_matched"].add(key)
                fs["candidates"].add(key)
                if best_cap != cap and sig:
                    fs["signal_misclassified"].add(key)
            elif cap in caps_on_page and url in fs["pages"]:
                fs["candidates"].add(key)

            if best_cap == cap:
                fs["classified"].add(key)
                if not sig:
                    fs["classified_no_signal"].add(key)

            if best_cap != cap:
                continue

            if q < MIN_QUALITY_SCORE or stage == "skip":
                fs["quality_rejected"].add(key)
                if stage == "skip":
                    fs["skip_rejected"].add(key)
                continue

            if state_family in UNCLASSIFIED:
                fs["quality_rejected"].add(key)
                continue

            if role_budget.get(budget_key, 0) >= 3:
                fs["role_cap"].add(key)
                continue

            if not gates.is_opportunity_allowed(state_family, task_family):
                fs["coverage_rejected"].add(key)
                continue

            role_budget[budget_key] += 1

            if key in accepted_keys:
                fs["accepted"].add(key)

        traces.append(
            {
                "url": url,
                "target": name[:80],
                "role": role,
                "state_family": state_family,
                "zone_family": zone_family,
                "classified": best_cap,
                "quality_score": q,
                "task_value": scored.get("task_value"),
                "learning_stage": stage,
                "seed_capabilities": caps_on_page,
            }
        )

    return traces


def _finalize(funnel_sets: Dict[str, Dict[str, Set]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for cap, fs in funnel_sets.items():
        if cap == "other":
            continue
        row = _empty_funnel()
        row["pages_seen"] = len(fs["pages"])
        row["regions_seen"] = len(fs["regions"])
        row["candidates_seen"] = len(fs["candidates"])
        row["classified"] = len(fs["classified"])
        row["quality_rejected"] = len(fs["quality_rejected"])
        row["coverage_rejected"] = len(fs["coverage_rejected"])
        row["accepted"] = len(fs["accepted"])
        row["diagnostics"] = {
            "seed_page_named_nodes": len(fs["seed_nodes"]),
            "signal_matched": len(fs["signal_matched"]),
            "signal_matched_misclassified": len(fs["signal_misclassified"]),
            "classified_without_signal": len(fs["classified_no_signal"]),
            "skip_stage_rejected": len(fs["skip_rejected"]),
            "role_cap_rejected": len(fs["role_cap"]),
        }
        # Funnel health: where did we lose the most from previous stage?
        prev = row["pages_seen"]
        drops = []
        for stage, val in [
            ("regions_seen", row["regions_seen"]),
            ("candidates_seen", row["candidates_seen"]),
            ("classified", row["classified"]),
            ("accepted", row["accepted"]),
        ]:
            drops.append({"stage": stage, "count": val, "drop_from_prev": prev - val})
            prev = val
        row["funnel_drops"] = drops
        row["primary_bottleneck"] = _primary_bottleneck(row)
        out[cap] = row
    return out


def _primary_bottleneck(row: Dict[str, Any]) -> str:
    d = row["diagnostics"]
    if row["pages_seen"] == 0:
        return "no_seed_pages_loaded"
    if d["signal_matched"] == 0 and row["candidates_seen"] == 0:
        return "opportunity_discovery"
    if d["signal_matched_misclassified"] > d["signal_matched"] / 2 and d["signal_matched"] > 0:
        return "classification"
    if row["classified"] > 0 and row["quality_rejected"] >= row["classified"]:
        return "quality_gate"
    if row["coverage_rejected"] > row["accepted"] and row["classified"] > row["accepted"]:
        return "coverage_gate"
    if row["accepted"] == 0 and row["classified"] > 0:
        return "validation_or_role_cap"
    if row["accepted"] > 0:
        return "healthy"
    return "unknown"


def _cov2_readiness(funnels: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    checks = {}
    for cap, target in COV2_TARGETS.items():
        accepted = funnels.get(cap, {}).get("accepted", 0)
        checks[cap] = {
            "target": target,
            "accepted": accepted,
            "met": accepted >= target,
        }
    return {
        "targets": COV2_TARGETS,
        "checks": checks,
        "cov2_ready": all(c["met"] for c in checks.values()),
    }


async def run_report(*, timeout_ms: int = 22000) -> Dict[str, Any]:
    urls = unique_seed_url_list()
    funnel_sets = _funnel_sets()
    errors: List[Dict[str, str]] = []
    all_traces: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            seed_caps = capabilities_for_url(url)
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
                traces = trace_page(url=url, ax_graph=ax, funnel_sets=funnel_sets, seed_caps=seed_caps)
                all_traces.extend(traces[:3])  # sample only
                print(f"OK  {len(traces):>3} traced  seeds={seed_caps}  {url[:52]}")
            except Exception as e:
                errors.append({"url": url, "seed_capabilities": seed_caps, "error": str(e)[:200]})
                print(f"ERR       seeds={seed_caps}  {url[:48]}  {e}")
        await browser.close()

    funnels = _finalize(funnel_sets)
    # Compact table for CTO view
    health_table = []
    for cap in (
        "upload",
        "job_application",
        "checkout",
        "content_creation",
        "settings",
        "search",
        "auth_recovery",
    ):
        if cap not in funnels:
            continue
        f = funnels[cap]
        health_table.append(
            {
                "capability": cap,
                "pages_seen": f["pages_seen"],
                "regions_seen": f["regions_seen"],
                "candidates_seen": f["candidates_seen"],
                "classified": f["classified"],
                "quality_rejected": f["quality_rejected"],
                "coverage_rejected": f["coverage_rejected"],
                "accepted": f["accepted"],
                "bottleneck": f["primary_bottleneck"],
            }
        )

    return {
        "schema": "browsermind.capability_funnel_report.v1",
        "phase": "COV-2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection_mode": "capability_driven_seeds",
        "seeds_schema": load_capability_seeds().get("schema"),
        "urls_attempted": len(urls),
        "urls_failed": len(errors),
        "crawl_errors": errors,
        "funnel_by_capability": funnels,
        "funnel_health_table": health_table,
        "cov2_readiness": _cov2_readiness(funnels),
        "diagnosis": {
            "summary": (
                "Compare candidates_seen vs classified to separate Opportunity Discovery "
                "from Classification; signal_matched_misclassified flags taxonomy gaps."
            ),
            "domain_driven_vs_capability_driven": (
                "This report uses capability_seeds.json (capability-first URLs)."
            ),
        },
        "trace_samples": all_traces[:40],
    }


async def main_async(args: argparse.Namespace) -> None:
    report = await run_report(timeout_ms=args.timeout_ms)
    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "capability_funnel_report.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== CAPABILITY FUNNEL HEALTH ==========")
    for row in report["funnel_health_table"]:
        print(
            f"{row['capability']:<18} "
            f"P={row['pages_seen']:<3} R={row['regions_seen']:<4} "
            f"Cand={row['candidates_seen']:<4} Cls={row['classified']:<4} "
            f"Q-={row['quality_rejected']:<4} Cov-={row['coverage_rejected']:<3} "
            f"Acc={row['accepted']:<3}  [{row['bottleneck']}]"
        )
    print(f"\ncov2_ready: {report['cov2_readiness']['cov2_ready']}")
    print(f"Wrote {out}")


def main():
    ap = argparse.ArgumentParser(description="COV-2 Capability Funnel Report")
    ap.add_argument("--timeout-ms", type=int, default=22000)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
