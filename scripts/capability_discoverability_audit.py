"""
Phase DISC-1 / DISC-3 -- Capability Discoverability Audit + Heatmap

Per capability funnel:
  signal_detected -> boundary_passed -> classified -> accepted

Writes reports/capability_discoverability_audit.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

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
    WORKFLOW_CAPABILITIES,
    build_zone_text_map,
    rank_capabilities,
    score_workflow_markers,
    workflow_capability_active,
)
from training.compiler import CoverageGates, OpportunityGraphGenerator, StateFamilyBuilder
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.graph_builder import build_graph_from_page

INTERACTION_ROLES = frozenset(
    {"button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem"}
)
EXTRACTION_ROLES = frozenset({"article", "list", "table", "row", "heading", "main"})

DISC_CAPS = (
    "upload",
    "job_application",
    "checkout",
    "content_creation",
    "settings",
    "search",
    "auth_recovery",
)


def _key(url: str, idx: int, role: str) -> Tuple[str, int, str]:
    return (url, idx, role)


def _empty_disc() -> Dict[str, Any]:
    return {
        "signal_detected": 0,
        "boundary_passed": 0,
        "classified": 0,
        "accepted": 0,
        "workflow_region_active": 0,
        "diagnostics": {
            "signal_only": 0,
            "boundary_only": 0,
            "classified_without_signal": 0,
            "lost_at_classification": 0,
        },
    }


def _sets() -> Dict[str, Dict[str, Set]]:
    return {
        cap: {
            "signal": set(),
            "boundary": set(),
            "classified": set(),
            "accepted": set(),
            "workflow_region": set(),
        }
        for cap in DISC_CAPS
    }


def audit_page(
    url: str,
    ax_graph: Dict[str, Any],
    counters: Dict[str, Dict[str, Set]],
) -> None:
    builder = StateFamilyBuilder()
    family_data = builder.identify_family(ax_graph)
    state_family = family_data["state_family"]
    confidence = float(family_data.get("confidence", 0.9))
    zones = builder.identify_zones(ax_graph).get("zones", [])
    zone_text_by_idx = build_zone_text_map(ax_graph, zones)

    gates = CoverageGates()
    gen = OpportunityGraphGenerator(gates)
    generated = gen.generate(ax_graph, family_data)
    accepted_keys: Set[Tuple[str, int, str]] = set()
    for opp in generated.get("interaction_opportunities", []):
        accepted_keys.add(_key(url, opp["node"], opp.get("role", "")))
    for opp in generated.get("extraction_opportunities", []):
        for nid in opp.get("node_ids", []):
            accepted_keys.add(_key(url, nid, opp.get("role", "")))

    headings = gen._heading_context(ax_graph)
    seed_caps = capabilities_for_url(url)

    for cap in WORKFLOW_CAPABILITIES:
        if cap not in counters:
            continue
        for _zi, zone in enumerate(zones):
            texts = [
                n.get("name", "").strip()
                for n in ax_graph.get("nodes", [])
                if n.get("idx") in zone.get("node_idxs", []) and n.get("name", "").strip()
            ]
            if workflow_capability_active(cap, texts):
                for idx in zone.get("node_idxs", []):
                    node = next(
                        (n for n in ax_graph.get("nodes", []) if n.get("idx") == idx),
                        None,
                    )
                    if node:
                        role = (node.get("role") or "").lower()
                        counters[cap]["workflow_region"].add(_key(url, idx, role))

    for node in ax_graph.get("nodes", []):
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        node_idx = node.get("idx")
        if node_idx is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        opp_type = "interaction" if role in INTERACTION_ROLES else "extraction"
        key = _key(url, node_idx, role)
        zone_texts = zone_text_by_idx.get(node_idx, [])

        ranked = rank_capabilities(
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opp_type,
            heading_context=headings,
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
        passes_q = scored["quality_score"] >= MIN_QUALITY_SCORE and scored.get("learning_stage") != "skip"

        caps_to_check = set(DISC_CAPS) | set(seed_caps) | {best_cap}
        for cap in caps_to_check:
            if cap not in counters:
                continue

            sig = discovery_signal_detected(
                cap, name, role=role, state_family=state_family
            )
            bnd = boundary_passed(
                cap,
                name,
                role=role,
                state_family=state_family,
                opportunity_type=opp_type,
                heading_context=headings,
                zone_texts=zone_texts,
            )
            if cap in WORKFLOW_CAPABILITIES and zone_texts:
                wf_score, matched = score_workflow_markers(cap, zone_texts)
                if wf_score >= 0.54:
                    sig = True
                if workflow_capability_active(cap, zone_texts):
                    counters[cap]["workflow_region"].add(key)

            if sig:
                counters[cap]["signal"].add(key)
            if bnd:
                counters[cap]["boundary"].add(key)
            if best_cap == cap:
                counters[cap]["classified"].add(key)
            if key in accepted_keys and best_cap == cap:
                counters[cap]["accepted"].add(key)


def finalize(counters: Dict[str, Dict[str, Set]]) -> Dict[str, Any]:
    funnels: Dict[str, Any] = {}
    heatmap: Dict[str, Any] = {}

    for cap in DISC_CAPS:
        fs = counters[cap]
        row = _empty_disc()
        row["signal_detected"] = len(fs["signal"])
        row["boundary_passed"] = len(fs["boundary"])
        row["classified"] = len(fs["classified"])
        row["accepted"] = len(fs["accepted"])
        row["workflow_region_active"] = len(fs["workflow_region"])

        signal_keys = fs["signal"]
        classified_keys = fs["classified"]
        row["diagnostics"]["signal_only"] = len(signal_keys - fs["boundary"])
        row["diagnostics"]["boundary_only"] = len(fs["boundary"] - signal_keys)
        row["diagnostics"]["classified_without_signal"] = len(classified_keys - signal_keys)
        row["diagnostics"]["lost_at_classification"] = len(signal_keys - classified_keys)

        if row["signal_detected"] == 0:
            row["primary_failure"] = "discovery"
        elif row["classified"] == 0 and row["boundary_passed"] > 0:
            row["primary_failure"] = "classification"
        elif row["classified"] == 0 and row["signal_detected"] > 0:
            row["primary_failure"] = "boundary_or_classification"
        elif row["accepted"] == 0 and row["classified"] > 0:
            row["primary_failure"] = "quality_or_coverage"
        else:
            row["primary_failure"] = "healthy"

        funnels[cap] = row
        heatmap[cap] = {
            "signal": row["signal_detected"],
            "boundary": row["boundary_passed"],
            "classified": row["classified"],
            "accepted": row["accepted"],
        }

    return funnels, heatmap


async def run_audit(timeout_ms: int = 22000) -> Dict[str, Any]:
    urls = unique_seed_url_list()
    counters = _sets()
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
                audit_page(url, ax, counters)
                print(f"OK  {url[:60]}")
            except Exception as e:
                errors.append({"url": url, "error": str(e)[:200]})
                print(f"ERR {url[:48]}  {e}")
        await browser.close()

    funnels, heatmap = finalize(counters)
    return {
        "schema": "browsermind.capability_discoverability_audit.v1",
        "phase": "DISC-1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "funnel_stages": ["signal_detected", "boundary_passed", "classified", "accepted"],
        "urls_attempted": len(urls),
        "urls_failed": len(errors),
        "crawl_errors": errors,
        "funnel_by_capability": funnels,
        "capability_heatmap": heatmap,
        "workflow_capabilities": list(WORKFLOW_CAPABILITIES),
        "diagnosis": {
            "p0": "capability_discoverability",
            "interpretation": {
                "discovery": "signal_detected == 0",
                "boundary": "signal > 0 but boundary_passed << signal",
                "classification": "signal > 0 but classified == 0 (lost_at_classification)",
                "acceptance": "classified > 0 but accepted == 0",
            },
        },
    }


async def main_async(args: argparse.Namespace) -> None:
    report = await run_audit(timeout_ms=args.timeout_ms)
    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "capability_discoverability_audit.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== DISC-1 SIGNAL FUNNEL ==========")
    for cap, row in report["funnel_by_capability"].items():
        if cap in ("upload", "job_application", "checkout", "content_creation", "search", "auth_recovery"):
            print(
                f"{cap:<18} sig={row['signal_detected']:<4} bnd={row['boundary_passed']:<4} "
                f"cls={row['classified']:<4} acc={row['accepted']:<4}  "
                f"[{row['primary_failure']}] lost_cls={row['diagnostics']['lost_at_classification']}"
            )
    print("\n========== DISC-3 HEATMAP ==========")
    print(json.dumps(report["capability_heatmap"], indent=2))
    print(f"\nWrote {out}")


def main():
    ap = argparse.ArgumentParser(description="DISC-1 Capability Discoverability Audit")
    ap.add_argument("--timeout-ms", type=int, default=22000)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
