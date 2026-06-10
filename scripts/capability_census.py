"""
Phase COV-1 -- Capability Census
Counts classified opportunities per capability (not per domain).

Writes reports/capability_census.json
Optional: --update-cache merges rows into reports/_quality_candidates_cache.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.cov1_coverage_targets import (
    CAPABILITY_CENSUS_TARGETS,
    CORE_CURRICULUM_CAPS,
    resolve_targets,
)
from training.graph_builder import build_graph_from_page
from training.compiler import StateFamilyBuilder
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.capability_taxonomy import rank_capabilities
from training.task_value_estimator import compose_quality_score, estimate_task_value

INTERACTION_ROLES = frozenset(
    {"button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem"}
)
EXTRACTION_ROLES = frozenset({"article", "list", "table", "row", "heading", "main"})


def _actionability(name: str, opportunity_type: str) -> float:
    if opportunity_type == "extraction":
        return 0.85 if len(name) < 60 else 0.35
    return 0.9 if len(name) < 40 else 0.25


def enumerate_opportunities(
    ax_graph: Dict[str, Any],
    *,
    url: str,
    bucket: str,
    source: str,
    intended: List[str],
    state_family: str,
    family_confidence: float,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for node in ax_graph.get("nodes", []):
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        node_idx = node.get("idx")
        if node_idx is None or not name:
            continue
        if role not in INTERACTION_ROLES and role not in EXTRACTION_ROLES:
            continue

        opp_type = "interaction" if role in INTERACTION_ROLES else "extraction"
        ranked = rank_capabilities(name, role=role, state_family=state_family, opportunity_type=opp_type)
        cap_id, strength, cap_conf = ranked[0]

        tv = estimate_task_value(
            name, role=role, state_family=state_family, opportunity_type=opp_type
        )
        actionability = _actionability(name, opp_type)
        rarity = 1.0
        quality = compose_quality_score(
            tv["task_value"],
            actionability=actionability,
            confidence=family_confidence,
            rarity=rarity,
        )

        rows.append(
            {
                "url": url,
                "bucket": bucket,
                "source": source,
                "intended_capabilities": intended,
                "target": name,
                "role": role,
                "node_idx": node_idx,
                "opportunity_type": opp_type,
                "state_family": state_family,
                "family_confidence": family_confidence,
                "capability": cap_id,
                "capability_match_strength": strength,
                "capability_confidence": cap_conf,
                "task_value": tv["task_value"],
                "learning_stage": tv["learning_stage"],
                "quality_score_v12": round(quality, 4),
                "v12_pass": quality >= MIN_QUALITY_SCORE,
            }
        )
    return rows


def _gap_analysis(counts: Dict[str, int]) -> Dict[str, Any]:
    gaps = []
    met = []
    for cap, target in sorted(CAPABILITY_CENSUS_TARGETS.items(), key=lambda x: -x[1]):
        have = counts.get(cap, 0)
        if have < target:
            gaps.append(
                {
                    "capability": cap,
                    "have": have,
                    "target": target,
                    "deficit": target - have,
                }
            )
        else:
            met.append({"capability": cap, "have": have, "target": target})
    core = {c: counts.get(c, 0) for c in CORE_CURRICULUM_CAPS}
    core_nonzero = {k: v for k, v in core.items() if v > 0}
    return {
        "aspirational_targets": CAPABILITY_CENSUS_TARGETS,
        "capabilities_below_target": gaps[:15],
        "capabilities_at_target": met,
        "core_curriculum_exposure": core,
        "core_curriculum_all_nonzero": len(core_nonzero) == len(CORE_CURRICULUM_CAPS),
        "cov1_ready_for_v13_gate": all(core.get(c, 0) > 0 for c in ("upload", "search", "auth_recovery")),
    }


def _bucket_intent_hits(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_bucket: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("source") != "cov1":
            continue
        by_bucket[r["bucket"]].append(r)

    out: Dict[str, Any] = {}
    for bucket, bucket_rows in by_bucket.items():
        intended = bucket_rows[0].get("intended_capabilities", []) if bucket_rows else []
        cap_dist = Counter(r["capability"] for r in bucket_rows)
        hits = {cap: cap_dist.get(cap, 0) for cap in intended}
        out[bucket] = {
            "urls_in_bucket": len({r["url"] for r in bucket_rows}),
            "candidates": len(bucket_rows),
            "capability_distribution": dict(cap_dist.most_common()),
            "intended_capabilities": intended,
            "intended_hits": hits,
            "intended_any_hit": any(v > 0 for v in hits.values()) if intended else None,
        }
    return out


def build_report(rows: List[Dict[str, Any]], *, mode: str, errors: List[Dict[str, str]]) -> Dict[str, Any]:
    all_caps = Counter(r["capability"] for r in rows)
    non_other = Counter(r["capability"] for r in rows if r["capability"] != "other")
    accepted = Counter(r["capability"] for r in rows if r["v12_pass"])
    by_source = defaultdict(Counter)
    for r in rows:
        by_source[r["source"]][r["capability"]] += 1

    return {
        "schema": "browsermind.capability_census.v1",
        "phase": "COV-1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "urls_attempted": len({r["url"] for r in rows}) + len(errors),
        "urls_ok": len({r["url"] for r in rows}),
        "urls_failed": len(errors),
        "crawl_errors": errors,
        "total_opportunities": len(rows),
        "capability_counts": dict(all_caps.most_common()),
        "capability_counts_excluding_other": dict(non_other.most_common()),
        "capability_counts_v12_accepted": dict(accepted.most_common()),
        "capability_counts_by_source": {
            src: dict(cnt.most_common()) for src, cnt in by_source.items()
        },
        "cov1_bucket_intent": _bucket_intent_hits(rows),
        "gap_analysis": _gap_analysis(dict(all_caps)),
        "diagnosis": {
            "primary_blocker": (
                "corpus_coverage"
                if not _gap_analysis(dict(all_caps))["cov1_ready_for_v13_gate"]
                else "approaching_coverage_targets"
            ),
            "note": (
                "Capability census measures AX exposure per capability, not domains. "
                "Compare capability_counts to CAPABILITY_CENSUS_TARGETS for corpus planning."
            ),
        },
    }


async def run_census(
    mode: str,
    *,
    timeout_ms: int = 22000,
) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    targets = resolve_targets(mode)
    builder = StateFamilyBuilder()
    all_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for spec in targets:
            url = spec["url"]
            bucket = spec["bucket"]
            source = spec.get("source", "cov1")
            intended = list(spec.get("intended") or [])
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

                fam = builder.identify_family(ax)
                sf = fam["state_family"]
                conf = float(fam.get("confidence", 0.9))
                rows = enumerate_opportunities(
                    ax,
                    url=url,
                    bucket=bucket,
                    source=source,
                    intended=intended,
                    state_family=sf,
                    family_confidence=conf,
                )
                all_rows.extend(rows)
                top = Counter(r["capability"] for r in rows).most_common(3)
                print(f"OK  {source:<8} {bucket:<18} {len(rows):>3} opps  {top}  {url[:56]}")
            except Exception as e:
                errors.append({"url": url, "bucket": bucket, "source": source, "error": str(e)[:200]})
                print(f"ERR {source:<8} {bucket:<18}       {url[:48]}  {e}")
        await browser.close()

    return all_rows, errors


def _merge_cache(rows: List[Dict[str, Any]]) -> None:
    cache_path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    existing: List[Dict[str, Any]] = []
    if os.path.isfile(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            existing = json.load(f)

    seen = {(r["url"], r["node_idx"], r["role"]) for r in existing}
    added = 0
    for r in rows:
        key = (r["url"], r["node_idx"], r["role"])
        if key in seen:
            continue
        seen.add(key)
        existing.append(
            {
                "url": r["url"],
                "category": r["bucket"],
                "state_family": r["state_family"],
                "family_confidence": r["family_confidence"],
                "target": r["target"],
                "role": r["role"],
                "node_idx": r["node_idx"],
                "opportunity_type": r["opportunity_type"],
                "quality_score": r["quality_score_v12"],
                "rejection_reason": "accepted" if r["v12_pass"] else "quality_below_threshold",
                "factors": {
                    "task_value": r["task_value"],
                    "rarity": 1.0,
                    "family_confidence": r["family_confidence"],
                },
                "penalties": [],
                "semantic_tags": {},
                "distance_to_threshold": round(r["quality_score_v12"] - MIN_QUALITY_SCORE, 4),
                "capability": r["capability"],
                "cov1": True,
            }
        )
        added += 1

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False)
    print(f"Cache: +{added} rows (total {len(existing)}) -> {cache_path}")


async def main_async(args: argparse.Namespace) -> None:
    rows, errors = await run_census(args.mode, timeout_ms=args.timeout_ms)
    report = build_report(rows, mode=args.mode, errors=errors)

    out = os.path.join(os.path.dirname(__file__), "..", "reports", "capability_census.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n========== CAPABILITY CENSUS ==========")
    print(json.dumps(
        {
            "mode": report["mode"],
            "total_opportunities": report["total_opportunities"],
            "capability_counts": report["capability_counts"],
            "v12_accepted": report["capability_counts_v12_accepted"],
            "cov1_ready": report["gap_analysis"]["cov1_ready_for_v13_gate"],
            "core_exposure": report["gap_analysis"]["core_curriculum_exposure"],
        },
        indent=2,
        ensure_ascii=False,
    ))
    print(f"\nWrote {out}")

    if args.update_cache and rows:
        _merge_cache(rows)


def main():
    ap = argparse.ArgumentParser(description="COV-1 Capability Census")
    ap.add_argument(
        "--mode",
        choices=("cov1", "baseline", "full"),
        default="full",
        help="cov1=expansion URLs only; baseline=36 URLs; full=both",
    )
    ap.add_argument("--update-cache", action="store_true", help="Append new rows to quality cache")
    ap.add_argument("--timeout-ms", type=int, default=22000)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
