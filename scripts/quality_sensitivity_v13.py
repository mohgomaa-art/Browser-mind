"""
Phase V1.3 -- Value Model Sensitivity
Re-scores cached candidates with V1.2 quality (task_value x actionability x confidence x rarity).

Analysis A: Pass / Fail factor contribution
Analysis B: Accepted capability distribution
Analysis C: Role independence (Quality ~= Role collapse test)

Writes reports/quality_sensitivity_v13.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.compiler.opportunity_graph_generator import MIN_QUALITY_SCORE
from training.task_value_estimator import compose_quality_score, estimate_task_value

# V1.2 quality factors (not legacy learnability)
V12_FACTOR_KEYS = (
    "task_value",
    "actionability",
    "confidence",
    "rarity",
    "capability_prior",
    "workflow_potential",
    "cross_site_value",
    "completion_probability",
)

CORE_CAPABILITY_GATE = ("search", "auth_recovery", "upload")

GATE_TASK_VALUE_CONTRIB_PCT = 35.0
GATE_ROLE_CONTRIB_PCT = 20.0


def _actionability(name: str, opportunity_type: str) -> float:
    if opportunity_type == "extraction":
        return 0.85 if len(name) < 60 else 0.35
    return 0.9 if len(name) < 40 else 0.25


def rescore_row_v12(row: Dict[str, Any]) -> Dict[str, Any]:
    target = row.get("target", row.get("name", ""))
    role = row.get("role", "")
    state_family = row.get("state_family", "")
    opp_type = row.get("opportunity_type", "interaction")
    confidence = float(row.get("family_confidence", row.get("factors", {}).get("family_confidence", 0.9)))
    rarity = float(row.get("factors", {}).get("rarity", 1.0))

    tv = estimate_task_value(
        target,
        role=role,
        state_family=state_family,
        opportunity_type=opp_type,
    )
    actionability = _actionability(target, opp_type)
    quality = compose_quality_score(
        tv["task_value"],
        actionability=actionability,
        confidence=confidence,
        rarity=rarity,
    )
    factors = {
        "task_value": tv["task_value"],
        "actionability": round(actionability, 4),
        "confidence": round(confidence, 4),
        "rarity": round(rarity, 4),
        **tv["task_value_factors"],
        "capability_confidence": tv["capability_confidence"],
    }
    passed = quality >= MIN_QUALITY_SCORE
    return {
        **row,
        "quality_score_v12": round(quality, 4),
        "v12_pass": passed,
        "capability": tv["capability"],
        "learning_stage": tv["learning_stage"],
        "task_value": tv["task_value"],
        "task_value_factors": tv["task_value_factors"],
        "factors_v12": factors,
        "rejection_reason_v12": "accepted" if passed else "quality_below_threshold",
    }


def _cohen_d_squared(pass_vals: np.ndarray, fail_vals: np.ndarray) -> float:
    if len(pass_vals) == 0 or len(fail_vals) == 0:
        return 0.0
    pooled = float(np.sqrt((np.var(pass_vals) + np.var(fail_vals)) / 2)) or 1e-9
    d = abs(float(np.mean(pass_vals)) - float(np.mean(fail_vals))) / pooled
    return d * d


def analysis_a_pass_fail(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    passed = [r for r in rows if r["v12_pass"]]
    failed = [r for r in rows if not r["v12_pass"]]
    if not passed or not failed:
        return {"error": "insufficient_pass_or_fail_split"}

    effects: Dict[str, float] = {}
    for k in V12_FACTOR_KEYS:
        p = np.array([r["factors_v12"][k] for r in passed], dtype=float)
        f = np.array([r["factors_v12"][k] for r in failed], dtype=float)
        effects[k] = _cohen_d_squared(p, f)

    # Role: eta2 for binary pass ~ role (between-role pass-rate variance)
    roles = [r["role"] for r in rows]
    y = np.array([1.0 if r["v12_pass"] else 0.0 for r in rows], dtype=float)
    p_global = float(y.mean())
    ss_total = float(((y - p_global) ** 2).sum()) or 1e-9
    ss_between = 0.0
    for role in set(roles):
        mask = np.array([ro == role for ro in roles])
        n_i = mask.sum()
        if n_i == 0:
            continue
        p_i = float(y[mask].mean())
        ss_between += n_i * (p_i - p_global) ** 2
    effects["role"] = ss_between / ss_total

    total = sum(effects.values()) or 1.0
    percent = {k: round(100.0 * float(v) / total, 2) for k, v in effects.items()}

    return {
        "description": "Squared Cohen d2 (continuous factors) + eta2 (role) normalized to 100%",
        "passed_count": len(passed),
        "failed_count": len(failed),
        "pass_rate_pct": round(100.0 * len(passed) / len(rows), 2),
        "percent": percent,
        "task_value_contribution_pct": percent.get("task_value", 0.0),
        "role_contribution_pct": percent.get("role", 0.0),
        "factor_means_passed": {
            k: round(float(np.mean([r["factors_v12"][k] for r in passed])), 4)
            for k in V12_FACTOR_KEYS
        },
        "factor_means_failed": {
            k: round(float(np.mean([r["factors_v12"][k] for r in failed])), 4)
            for k in V12_FACTOR_KEYS
        },
    }


def _upload_like_in_sample(rows: List[Dict[str, Any]]) -> int:
    terms = ("upload", "resume", "attach", "choose file", "browse file")
    return sum(
        1
        for r in rows
        if any(t in r.get("target", "").lower() for t in terms)
    )


def analysis_b_accepted_capabilities(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    accepted = [r for r in rows if r["v12_pass"]]
    dist = Counter(r["capability"] for r in accepted)
    core = {cap: dist.get(cap, 0) for cap in CORE_CAPABILITY_GATE}
    return {
        "accepted_count": len(accepted),
        "capability_distribution": dict(dist.most_common()),
        "capability_distribution_sorted": dict(sorted(dist.items(), key=lambda x: -x[1])),
        "core_capability_counts": core,
        "core_capabilities_non_zero": bool(all(v > 0 for v in core.values())),
        "upload_like_candidates_in_sample": _upload_like_in_sample(rows),
        "learning_stage_distribution": dict(
            Counter(r["learning_stage"] for r in accepted).most_common()
        ),
    }


def _r2_categorical(y: np.ndarray, groups: List[str]) -> float:
    unique = list(set(groups))
    if len(unique) < 2:
        return 0.0
    y_mean = float(y.mean())
    ss_tot = float(((y - y_mean) ** 2).sum()) or 1e-9
    ss_between = 0.0
    for g in unique:
        mask = np.array([gr == g for gr in groups])
        if not mask.any():
            continue
        yi = y[mask]
        ss_between += len(yi) * (float(yi.mean()) - y_mean) ** 2
    return round(float(ss_between / ss_tot), 4)


def analysis_c_role_independence(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    q = np.array([r["quality_score_v12"] for r in rows], dtype=float)
    tv = np.array([r["task_value"] for r in rows], dtype=float)
    roles = [r["role"] for r in rows]
    caps = [r["capability"] for r in rows]

    role_r2 = _r2_categorical(q, roles)
    cap_r2 = _r2_categorical(q, caps)

    if np.std(tv) < 1e-12:
        task_value_r2 = 0.0
    else:
        r = float(np.corrcoef(tv, q)[0, 1])
        task_value_r2 = round(r * r, 4)

    # Partial: role on residual after linear task_value
    if np.std(tv) >= 1e-12:
        coef = np.cov(tv, q)[0, 1] / (np.var(tv) or 1e-9)
        intercept = float(q.mean() - coef * tv.mean())
        residual = q - (intercept + coef * tv)
        role_r2_after_task_value = _r2_categorical(residual, roles)
    else:
        role_r2_after_task_value = role_r2

    log_q = np.log(np.clip(q, 1e-9, None))
    log_tv = np.log(np.clip(tv, 1e-9, None))
    if np.std(log_tv) < 1e-12:
        log_task_value_r2 = 0.0
    else:
        r = float(np.corrcoef(log_tv, log_q)[0, 1])
        log_task_value_r2 = round(r * r, 4)

    return {
        "description": "R2 of quality_score_v12 explained by role vs task_value",
        "role_explained_variance": role_r2,
        "role_explained_variance_pct": round(role_r2 * 100, 2),
        "task_value_explained_variance": task_value_r2,
        "task_value_explained_variance_pct": round(task_value_r2 * 100, 2),
        "capability_explained_variance": cap_r2,
        "role_explained_variance_after_task_value": role_r2_after_task_value,
        "role_explained_variance_after_task_value_pct": round(
            role_r2_after_task_value * 100, 2
        ),
        "log_task_value_explained_variance": log_task_value_r2,
        "quality_approx_role_collapse": bool(role_r2 >= 0.50),
        "value_model_independent_of_role": bool(role_r2 < GATE_ROLE_CONTRIB_PCT / 100.0),
    }


def _decision_gate(
    a: Dict[str, Any],
    b: Dict[str, Any],
    c: Dict[str, Any],
) -> Dict[str, Any]:
    tv_ok = a.get("task_value_contribution_pct", 0) >= GATE_TASK_VALUE_CONTRIB_PCT
    role_ok = a.get("role_contribution_pct", 100) < GATE_ROLE_CONTRIB_PCT
    role_r2_ok = c.get("role_explained_variance", 1.0) < GATE_ROLE_CONTRIB_PCT / 100.0
    core_ok = b.get("core_capabilities_non_zero", False)

    checks = {
        "task_value_contribution_gte_35pct": tv_ok,
        "role_pass_fail_contribution_lt_20pct": role_ok,
        "role_explained_variance_lt_20pct": role_r2_ok,
        "upload_auth_search_nonzero_accepted": core_ok,
    }
    phase_v = bool(all(checks.values()))
    checks = {k: bool(v) for k, v in checks.items()}

    corpus_blocked = not core_ok and b.get("upload_like_candidates_in_sample", 0) == 0
    return {
        "phase_v_successful": phase_v,
        "phase_v_blocked_by_corpus": bool(not phase_v and corpus_blocked),
        "checks": checks,
        "recommendation": (
            "Proceed: V1.3 Decision Gate -> Recompile V2 -> Gold V4 -> Human V4"
            if phase_v
            else (
                "Do NOT recompile yet. Expand capability corpus (COV-1), then re-run V1.3."
                if not phase_v
                else ""
            )
        ),
        "thresholds": {
            "task_value_contribution_pct_min": GATE_TASK_VALUE_CONTRIB_PCT,
            "role_contribution_pct_max": GATE_ROLE_CONTRIB_PCT,
            "role_explained_variance_max": GATE_ROLE_CONTRIB_PCT / 100.0,
            "core_capabilities": list(CORE_CAPABILITY_GATE),
        },
    }


def build_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    a = analysis_a_pass_fail(rows)
    b = analysis_b_accepted_capabilities(rows)
    c = analysis_c_role_independence(rows)
    gate = _decision_gate(a, b, c)

    legacy_pass = sum(1 for r in rows if r.get("quality_score", 0) >= MIN_QUALITY_SCORE)
    v12_pass = sum(1 for r in rows if r["v12_pass"])

    return {
        "schema": "browsermind.quality_sensitivity.v1.3",
        "phase": "V1.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(rows),
        "threshold": MIN_QUALITY_SCORE,
        "scoring_model": "V1.2 task_value x actionability x confidence x rarity",
        "taxonomy_version": "1.25",
        "pass_counts": {
            "legacy_quality_pass": legacy_pass,
            "v12_quality_pass": v12_pass,
            "legacy_pass_rate_pct": round(100 * legacy_pass / len(rows), 2) if rows else 0,
            "v12_pass_rate_pct": round(100 * v12_pass / len(rows), 2) if rows else 0,
        },
        "analysis_a_pass_fail_contribution": a,
        "analysis_b_accepted_capability_distribution": b,
        "analysis_c_role_independence": c,
        "decision_gate": gate,
        "verdict": {
            "phase_v_successful": gate["phase_v_successful"],
            "summary": gate["recommendation"],
        },
        "interpretation": {
            "quality_vs_role_broken": bool(
                a.get("task_value_contribution_pct", 0) >= GATE_TASK_VALUE_CONTRIB_PCT
                and c.get("role_explained_variance_after_task_value", 1.0)
                < GATE_ROLE_CONTRIB_PCT / 100.0
            ),
            "notes": [
                "Analysis A role % is pass/fail separation (eta2), not variance of Q.",
                "Analysis C role_explained_variance is R2(Q ~ role); after_task_value is the independence test.",
                "upload=0 accepted usually means corpus gap (few upload nodes in census URLs), not taxonomy.",
            ],
        },
    }


def _load_candidates() -> List[Dict[str, Any]]:
    path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "_quality_candidates_cache.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    raw = _load_candidates()
    rows = [rescore_row_v12(r) for r in raw]
    report = build_report(rows)

    out = os.path.join(
        os.path.dirname(__file__), "..", "reports", "quality_sensitivity_v13.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    a = report["analysis_a_pass_fail_contribution"]
    b = report["analysis_b_accepted_capability_distribution"]
    c = report["analysis_c_role_independence"]
    g = report["decision_gate"]

    print("========== V1.3 VALUE MODEL SENSITIVITY ==========")
    print(f"sample={report['sample_size']}  v12_pass={report['pass_counts']['v12_quality_pass']}")
    print("\n--- Analysis A (Pass/Fail) ---")
    print(f"  task_value: {a.get('task_value_contribution_pct')}%")
    print(f"  role:       {a.get('role_contribution_pct')}%")
    print(f"  full:       {a.get('percent')}")
    print("\n--- Analysis B (Accepted capabilities) ---")
    print(f"  accepted: {b.get('accepted_count')}")
    print(f"  dist:     {b.get('capability_distribution')}")
    print(f"  core:     {b.get('core_capability_counts')}")
    print("\n--- Analysis C (Role independence) ---")
    print(f"  role_explained_variance:      {c.get('role_explained_variance')} ({c.get('role_explained_variance_pct')}%)")
    print(f"  task_value_explained_variance: {c.get('task_value_explained_variance')} ({c.get('task_value_explained_variance_pct')}%)")
    print(f"  role after task_value:        {c.get('role_explained_variance_after_task_value')}")
    print("\n--- Decision Gate ---")
    print(f"  phase_v_successful: {g['phase_v_successful']}")
    print(f"  checks: {g['checks']}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
