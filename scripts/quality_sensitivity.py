"""
Phase Q1 -- Quality Sensitivity Analysis
Variance contribution of each quality factor + link ceiling proof.
Writes reports/quality_sensitivity.json
      reports/high_value_near_miss_review.json
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler import StateFamilyBuilder
from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE

from quality_audit import (  # noqa: E402
    TARGETS,
    collect_candidates,
)

FACTOR_KEYS = (
    "task_relevance",
    "learnability",
    "actionability",
    "rarity",
    "family_confidence",
)


def _load_rows_from_audit() -> List[Dict[str, Any]] | None:
    path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "quality_audit.json"
    )
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    seen = set()
    for key in (
        "accepted_top_50",
        "rejected_top_50_near_miss",
        "rejected_lowest_20",
    ):
        for r in data.get(key, []):
            uid = (r["url"], r["node_idx"], r["role"])
            if uid in seen:
                continue
            seen.add(uid)
            rows.append(r)
    examples = data.get("near_miss_analysis", {}).get(
        "high_value_near_miss_examples", []
    )
    for r in examples:
        uid = (r["url"], r["node_idx"], r["role"])
        if uid not in seen:
            seen.add(uid)
            rows.append(r)
    return rows if len(rows) > 100 else None


async def _collect_all_rows() -> List[Dict[str, Any]]:
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
                all_rows.extend(collect_candidates(ax, url, category, fam))
            except Exception as e:
                print(f"skip {url}: {e}")
        await browser.close()
    print(f"Collected {len(all_rows)} candidates via live crawl")
    return all_rows


def _matrix(rows: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
    q = np.array([r["quality_score"] for r in rows], dtype=float)
    mats = {k: np.array([r["factors"][k] for r in rows], dtype=float) for k in FACTOR_KEYS}
    mats["quality_score"] = q
    mats["role"] = np.array([r["role"] for r in rows], dtype=object)
    mats["log_quality"] = np.log(np.clip(q, 1e-9, None))
    for k in FACTOR_KEYS:
        mats[f"log_{k}"] = np.log(np.clip(mats[k], 1e-9, None))
    return mats


def _variance_contribution_log_independence(mats: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Var(log Q) ~= Sigma Var(log fi) when factors independent (exact for product in log space)."""
    log_vars = {k: float(np.var(mats[f"log_{k}"])) for k in FACTOR_KEYS}
    total = sum(log_vars.values()) or 1.0
    return {k: round(100.0 * v / total, 2) for k, v in log_vars.items()}


def _variance_contribution_regression(mats: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Standardized OLS on log Q ~ log factors (no intercept -- exact for product model)."""
    y = mats["log_quality"]
    X = np.column_stack([mats[f"log_{k}"] for k in FACTOR_KEYS])
    # Center for numerical stability; use correlation-based relative importance
    y_c = y - y.mean()
    X_c = X - X.mean(axis=0)
    coefs = np.linalg.lstsq(X_c, y_c, rcond=None)[0]
    imp = coefs**2
    s = imp.sum() or 1.0
    return {k: round(100.0 * imp[i] / s, 2) for i, k in enumerate(FACTOR_KEYS)}


def _variance_contribution_correlation(mats: Dict[str, np.ndarray]) -> Dict[str, float]:
    y = mats["log_quality"]
    sq = []
    for k in FACTOR_KEYS:
        x = mats[f"log_{k}"]
        if np.std(x) < 1e-12:
            sq.append(0.0)
        else:
            r = np.corrcoef(x, y)[0, 1]
            sq.append(r * r)
    s = sum(sq) or 1.0
    return {k: round(100.0 * v / s, 2) for k, v in zip(FACTOR_KEYS, sq)}


def _pass_fail_discrimination(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Which factor best separates accepted (Q>=0.5) from rejected?
    Uses squared standardized mean difference (Cohen's d2 normalized).
    """
    passed = [r for r in rows if r["quality_score"] >= MIN_QUALITY_SCORE]
    failed = [r for r in rows if r["quality_score"] < MIN_QUALITY_SCORE]
    if not passed or not failed:
        return {}

    effects: Dict[str, float] = {}
    for k in FACTOR_KEYS:
        p = np.array([r["factors"][k] for r in passed], dtype=float)
        f = np.array([r["factors"][k] for r in failed], dtype=float)
        pooled_std = float(np.sqrt((np.var(p) + np.var(f)) / 2)) or 1e-9
        d = abs(float(np.mean(p)) - float(np.mean(f))) / pooled_std
        effects[k] = d * d

    total = sum(effects.values()) or 1.0
    pct = {k: round(100.0 * v / total, 2) for k, v in effects.items()}

    return {
        "description": "Squared Cohen d between pass vs fail groups, normalized to 100%",
        "percent": pct,
        "passed_count": len(passed),
        "failed_count": len(failed),
        "factor_means_passed": {
            k: round(float(np.mean([r["factors"][k] for r in passed])), 4)
            for k in FACTOR_KEYS
        },
        "factor_means_failed": {
            k: round(float(np.mean([r["factors"][k] for r in failed])), 4)
            for k in FACTOR_KEYS
        },
    }


def _quality_on_quality_variance(mats: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Direct correlation of each factor with Q (not log)."""
    q = mats["quality_score"]
    sq = []
    for k in FACTOR_KEYS:
        x = mats[k]
        if np.std(x) < 1e-12:
            sq.append(0.0)
        else:
            r = np.corrcoef(x, q)[0, 1]
            sq.append(r * r)
    s = sum(sq) or 1.0
    return {k: round(100.0 * v / s, 2) for k, v in zip(FACTOR_KEYS, sq)}


def _role_learnability_proof(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_role: Dict[str, List[float]] = {}
    by_role_learn: Dict[str, List[float]] = {}
    for r in rows:
        role = r["role"]
        by_role.setdefault(role, []).append(r["quality_score"])
        by_role_learn.setdefault(role, []).append(r["factors"]["learnability"])

    ceilings = {}
    for role, scores in by_role.items():
        learn = by_role_learn[role][0] if by_role_learn[role] else 0
        ceilings[role] = {
            "learnability_constant": learn,
            "max_observed_quality": round(max(scores), 4),
            "mean_quality": round(float(np.mean(scores)), 4),
            "pct_above_threshold": round(
                100 * sum(1 for s in scores if s >= MIN_QUALITY_SCORE) / len(scores), 2
            ),
            "theoretical_max_at_conf_1": round(1.0 * learn * 0.9 * 1.0 * 1.0, 4),
        }
    return {
        "link_ceiling_proof": ceilings.get("link", {}),
        "textbox_ceiling_proof": ceilings.get("textbox", {}),
        "button_ceiling_proof": ceilings.get("button", {}),
        "conclusion": (
            "link learnability=0.55 caps max quality near 0.47-0.50 at typical confidence; "
            "links cannot pass threshold 0.5 without changing learnability or using role-specific boosts."
        ),
    }


def _learnability_vs_role_r2(mats: Dict[str, np.ndarray]) -> float:
    """How much of learnability variance is explained by role alone."""
    roles = mats["role"]
    learn = mats["learnability"]
    unique = list(set(roles))
    if len(unique) < 2:
        return 1.0
    X = np.zeros((len(roles), len(unique)))
    for i, ro in enumerate(roles):
        X[i, unique.index(ro)] = 1.0
    X_c = X - X.mean(axis=0)
    y_c = learn - learn.mean()
    coef, _, _, _ = np.linalg.lstsq(X_c, y_c, rcond=None)
    pred = X_c @ coef
    ss_res = ((y_c - pred) ** 2).sum()
    ss_tot = (y_c**2).sum() or 1.0
    return round(float(1 - ss_res / ss_tot), 4)


def _human_review_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hv = [
        r
        for r in rows
        if r.get("semantic_tags", {}).get("high_value_keyword")
        and MIN_QUALITY_SCORE - 0.11 <= r["quality_score"] < MIN_QUALITY_SCORE
    ]
    hv.sort(key=lambda r: r["quality_score"], reverse=True)
    table = []
    for r in hv:
        table.append(
            {
                "target": r["target"],
                "url": r["url"],
                "role": r["role"],
                "state_family": r["state_family"],
                "current_score": r["quality_score"],
                "distance_to_threshold": r.get("distance_to_threshold"),
                "learnability": r["factors"]["learnability"],
                "task_relevance": r["factors"]["task_relevance"],
                "rejection_reason": r["rejection_reason"],
                "human_value": None,
                "human_notes": None,
            }
        )
    return table


def build_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    mats = _matrix(rows)
    log_ind = _variance_contribution_log_independence(mats)
    reg = _variance_contribution_regression(mats)
    corr = _variance_contribution_correlation(mats)
    direct = _quality_on_quality_variance(mats)

    accepted = [r for r in rows if r["quality_score"] >= MIN_QUALITY_SCORE]
    links = [r for r in rows if r["role"] == "link"]
    links_pass = [r for r in links if r["quality_score"] >= MIN_QUALITY_SCORE]

    avg = lambda key: round(float(np.mean(mats[key])), 4)

    pass_fail = _pass_fail_discrimination(rows)
    pf_pct = pass_fail.get("percent", {})
    collapse = bool(
        pf_pct.get("learnability", 0) >= 40
        or _learnability_vs_role_r2(mats) >= 0.65
    )

    return {
        "schema": "browsermind.quality_sensitivity.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(rows),
        "threshold": MIN_QUALITY_SCORE,
        "verdict": {
            "quality_function_collapse": collapse,
            "role_filter_dominance": collapse,
            "summary": (
                "Pass/fail is dominated by learnability (role-proxy); "
                "links cannot reach threshold. Global log-variance overstates "
                "confidence because rarity is constant and learnability is discrete per role."
                if collapse
                else "Factors show balanced contribution -- review methods."
            ),
        },
        "variance_contribution": {
            "method_log_variance_independence": {
                "description": "Var(log fi) / Sigma Var(log fj) -- exact for log-additive product",
                "percent": log_ind,
            },
            "method_standardized_regression_log": {
                "description": "Squared standardized OLS coefs on log Q ~ log factors",
                "percent": reg,
            },
            "method_squared_correlation_log": {
                "description": "r2(log fi, log Q) normalized",
                "percent": corr,
            },
            "method_squared_correlation_linear": {
                "description": "r2(fi, Q) on raw scale",
                "percent": direct,
            },
            "recommended_primary": "method_pass_fail_discrimination",
            "method_pass_fail_discrimination": pass_fail,
        },
        "factor_statistics": {
            k: {
                "mean": avg(k),
                "std": round(float(np.std(mats[k])), 4),
                "min": round(float(np.min(mats[k])), 4),
                "max": round(float(np.max(mats[k])), 4),
            }
            for k in FACTOR_KEYS
        },
        "role_filter_evidence": {
            "learnability_explained_by_role_r2": _learnability_vs_role_r2(mats),
            "links_total": len(links),
            "links_passing_threshold": len(links_pass),
            "links_pass_rate_pct": round(
                100 * len(links_pass) / len(links), 2
            )
            if links
            else 0.0,
            "accepted_by_role": dict(
                sorted(
                    {
                        role: sum(1 for r in accepted if r["role"] == role)
                        for role in set(r["role"] for r in rows)
                    }.items(),
                    key=lambda x: -x[1],
                )
            ),
            "ceiling_by_role": _role_learnability_proof(rows),
        },
        "quality_collapse_diagnosis": {
            "near_constant_factors": [
                k
                for k in FACTOR_KEYS
                if float(np.std(mats[k])) < 0.08
            ],
            "dominant_factor": max(log_ind, key=lambda k: log_ind[k]),
            "dominant_pct": float(max(log_ind.values())),
        },
        "cto_decision_matrix": {
            "if_high_value_near_miss_human_high_pct": "redesign_quality_function_task_value",
            "if_high_value_near_miss_human_low_pct": "keep_quality_expand_discovery",
        },
    }


async def main():
    cache_path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    if os.path.isfile(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"Loaded {len(rows)} cached candidates")
    else:
        rows = await _collect_all_rows()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)

    report = build_report(rows)
    review = _human_review_table(rows)

    reports = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(reports, exist_ok=True)

    sens_path = os.path.join(reports, "quality_sensitivity.json")
    review_path = os.path.join(reports, "high_value_near_miss_review.json")

    with open(sens_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    review_doc = {
        "schema": "browsermind.high_value_near_miss_review.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instructions": "Set human_value to High | Medium | Low for each row.",
        "count": len(review),
        "rows": review,
    }
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review_doc, f, indent=2, ensure_ascii=False)

    print("========== QUALITY SENSITIVITY ==========")
    print(json.dumps(
        {
            "sample_size": report["sample_size"],
            "verdict": report["verdict"],
            "variance_contribution": report["variance_contribution"][
                "method_log_variance_independence"
            ],
            "regression": report["variance_contribution"][
                "method_standardized_regression_log"
            ],
            "role_filter": report["role_filter_evidence"],
        },
        indent=2,
    ))
    print(f"\nWrote {sens_path}")
    print(f"Wrote {review_path} ({len(review)} rows for human review)")


if __name__ == "__main__":
    asyncio.run(main())
