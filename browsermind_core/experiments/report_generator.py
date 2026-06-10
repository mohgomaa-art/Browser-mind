"""Summary report generator for replay validation experiments."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional

from browsermind_core.experiments.replay_result import ReplayResult
from browsermind_core.experiments.sites import EXPERIMENT_SITES, GATE_MIN_RESOLUTION, GATE_SITES


def _site_resolution(results: Iterable[ReplayResult], site: str) -> Optional[float]:
    rows = [r for r in results if r.site == site]
    if not rows:
        return None
    return sum(r.resolution_rate for r in rows) / len(rows)


def evaluate_decision_thresholds(results: Iterable[ReplayResult]) -> dict:
    """
    Apply fixed decision rules to accumulated evidence.

    Uses resolution_rate only — not workflow success.
    """
    rows = list(results)
    by_site = {site.key: _site_resolution(rows, site.key) for site in EXPERIMENT_SITES}

    decisions: list[dict] = []
    stop = False
    stop_reason: Optional[str] = None

    baseline = by_site.get("static_baseline")
    if baseline is not None and baseline < GATE_MIN_RESOLUTION:
        stop = True
        stop_reason = (
            f"static_baseline resolution {baseline * 100:.1f}% < {GATE_MIN_RESOLUTION * 100:.0f}% — "
            "replay may be broken; investigate engine/recorder before hard sites"
        )
        decisions.append({"rule": "static_baseline_gate", "passed": False, "detail": stop_reason})

    saucedemo = by_site.get("saucedemo")
    if saucedemo is not None and saucedemo < GATE_MIN_RESOLUTION:
        stop = True
        stop_reason = (
            f"saucedemo resolution {saucedemo * 100:.1f}% < {GATE_MIN_RESOLUTION * 100:.0f}% — "
            "stop; investigate engine/recorder"
        )
        decisions.append({"rule": "saucedemo_gate", "passed": False, "detail": stop_reason})
    elif saucedemo is not None:
        decisions.append({"rule": "saucedemo_gate", "passed": True, "detail": f"resolution {saucedemo * 100:.1f}%"})

    demoqa = by_site.get("demoqa")
    if saucedemo is not None and demoqa is not None:
        engine_valid = saucedemo >= 0.90 and demoqa >= GATE_MIN_RESOLUTION
        decisions.append(
            {
                "rule": "replay_engine_likely_valid",
                "passed": engine_valid,
                "detail": (
                    f"saucedemo={saucedemo * 100:.1f}%, demoqa={demoqa * 100:.1f}% "
                    f"(needs saucedemo >= 90%, demoqa >= {GATE_MIN_RESOLUTION * 100:.0f}%)"
                ),
            }
        )

    github = by_site.get("github")
    if github is not None and saucedemo is not None:
        survivability_gap = saucedemo >= 0.95 and github < 0.30
        decisions.append(
            {
                "rule": "semantic_survivability_bottleneck",
                "passed": survivability_gap,
                "detail": (
                    f"saucedemo={saucedemo * 100:.1f}%, github={github * 100:.1f}% "
                    "(saucedemo >= 95% and github < 30% implies site difficulty, not engine failure)"
                ),
            }
        )

    dominant_category = None
    category_totals = Counter(
        r.failure_category.value for r in rows if r.failure_category is not None
    )
    if category_totals:
        name, count = category_totals.most_common(1)[0]
        share = count / sum(category_totals.values())
        if share >= 0.75:
            dominant_category = {
                "category": name,
                "share": round(share, 4),
                "implication": _category_implication(name),
            }

    return {
        "stop_recommended": stop,
        "stop_reason": stop_reason,
        "resolution_by_site": {k: v for k, v in by_site.items() if v is not None},
        "decisions": decisions,
        "dominant_failure_category": dominant_category,
    }


def _category_implication(category: str) -> str:
    return {
        # No semantic identifier at all — icon-only button, empty element.
        "NO_VISIBLE_SIGNAL": "Measure prevalence — may justify CSS/visual fallback long-term",
        # Human-visible label exists but DOM broke the binding.
        "ORPHANED_SEMANTIC_SIGNAL": "Measure prevalence — environmental failure, not a BrowserMind bug",
        "AMBIGUOUS_TARGET": "Improve Resolver",
        "TARGET_CHANGED": "Improve Resolver",
        "ENVIRONMENT_FAILURE": "Improve Runtime",
        "UNKNOWN": "Collect more evidence before acting",
    }.get(category, "Collect more evidence before acting")


def generate_summary_report(results: Iterable[ReplayResult]) -> dict:
    """Aggregate replay evidence into a summary dict."""
    rows = list(results)
    total_runs = len(rows)

    if total_runs == 0:
        return {
            "total_runs": 0,
            "message": "No replay results to summarize.",
        }

    avg_resolution = sum(r.resolution_rate for r in rows) / total_runs
    workflow_failures = sum(1 for r in rows if r.workflow_failed)
    high_resolution_workflow_failures = [
        {
            "site": r.site,
            "resolution_rate": r.resolution_rate,
            "resolved_steps": r.resolved_steps,
            "total_steps": r.total_steps,
            "failure_category": r.failure_category.value if r.failure_category else None,
        }
        for r in rows
        if r.workflow_failed and r.resolution_rate >= 0.80
    ]

    by_site: dict[str, dict] = {}
    for result in rows:
        bucket = by_site.setdefault(
            result.site,
            {
                "runs": 0,
                "workflow_failures": 0,
                "resolution_rates": [],
                "failure_categories": Counter(),
            },
        )
        bucket["runs"] += 1
        if result.workflow_failed:
            bucket["workflow_failures"] += 1
        bucket["resolution_rates"].append(result.resolution_rate)
        if result.failure_category:
            bucket["failure_categories"][result.failure_category.value] += 1

    site_summary = {}
    for site_key, bucket in by_site.items():
        rates = bucket["resolution_rates"]
        site_summary[site_key] = {
            "runs": bucket["runs"],
            "avg_resolution_rate": round(sum(rates) / len(rates), 4),
            "workflow_failures": bucket["workflow_failures"],
            "failure_categories": dict(bucket["failure_categories"]),
        }

    category_totals = Counter(
        r.failure_category.value
        for r in rows
        if r.failure_category is not None
    )

    failures = [
        {
            "site": r.site,
            "template_name": r.template_name,
            "failed_step": r.failed_step,
            "failure_category": r.failure_category.value if r.failure_category else None,
            "failure_reason": r.failure_reason,
            "resolution_rate": r.resolution_rate,
            "resolved_steps": r.resolved_steps,
            "total_steps": r.total_steps,
            "workflow_failed": r.workflow_failed,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
        if r.workflow_failed
    ]

    # ── Step-level ledger — counts each outcome across ALL steps in ALL runs ──
    # This is the signal-availability census: how often is each failure class
    # actually encountered at the step level (not just the workflow level).
    step_ledger: Counter = Counter()
    for r in rows:
        for s in r.step_outcomes:
            step_ledger[s["outcome"]] += 1
    # For runs that predate step_outcomes, fall back to workflow-level counts.
    if not step_ledger:
        for r in rows:
            if r.replay_success:
                step_ledger["RESOLVED"] += r.resolved_steps
            else:
                step_ledger["RESOLVED"] += r.resolved_steps
                if r.failure_category:
                    step_ledger[r.failure_category.value] += 1

    return {
        "total_runs": total_runs,
        "primary_kpi": {
            "avg_resolution_rate": round(avg_resolution, 4),
        },
        "secondary_kpi": {
            "workflow_failures": workflow_failures,
            "workflow_failure_rate": round(workflow_failures / total_runs, 4),
        },
        "step_ledger": dict(step_ledger),
        "high_resolution_workflow_failures": high_resolution_workflow_failures,
        "failure_category_totals": dict(category_totals),
        "by_site": site_summary,
        "failures": failures,
        "decision_thresholds": evaluate_decision_thresholds(rows),
    }


def write_summary_report(results: List[ReplayResult], output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown summaries. Returns (json_path, markdown_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = generate_summary_report(results)

    json_path = output_dir / "summary.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_path = output_dir / "summary.md"
    md_path.write_text(_render_markdown(summary, results), encoding="utf-8")
    return json_path, md_path


def _render_markdown(summary: dict, results: List[ReplayResult]) -> str:
    if summary.get("total_runs", 0) == 0:
        return "# Replay Validation Summary\n\nNo results recorded.\n"

    primary = summary["primary_kpi"]
    secondary = summary["secondary_kpi"]
    thresholds = summary.get("decision_thresholds") or {}

    lines = [
        "# Replay Validation Summary",
        "",
        "## Primary KPI — Resolution Rate",
        "",
        f"- **Average resolution rate:** {primary['avg_resolution_rate'] * 100:.1f}%",
        f"- **Total runs:** {summary['total_runs']}",
        "",
        "## Secondary KPI — Workflow Completion",
        "",
        f"- **Workflow failures:** {secondary['workflow_failures']} "
        f"({secondary['workflow_failure_rate'] * 100:.1f}%)",
        "",
    ]

    split_failures = summary.get("high_resolution_workflow_failures") or []
    if split_failures:
        lines.extend(["### High resolution, workflow failed", ""])
        for row in split_failures:
            lines.append(
                f"- **{row['site']}**: resolution {row['resolution_rate'] * 100:.1f}% "
                f"({row['resolved_steps']}/{row['total_steps']} steps resolved)"
            )
        lines.append("")

    lines.extend(["## Failure Categories", ""])
    categories = summary.get("failure_category_totals") or {}
    if categories:
        for name, count in sorted(categories.items()):
            lines.append(f"- `{name}`: {count}")
    else:
        lines.append("- None recorded")

    dominant = thresholds.get("dominant_failure_category")
    if dominant:
        lines.extend(
            [
                "",
                f"**Dominant category:** `{dominant['category']}` ({dominant['share'] * 100:.0f}%)",
                f"→ {dominant['implication']}",
            ]
        )

    # Step-level ledger
    ledger = summary.get("step_ledger") or {}
    if ledger:
        total_steps_observed = sum(ledger.values())
        lines.extend(["", "## Step Ledger (signal-availability census)", ""])
        lines.append(f"_Total steps observed across all runs: {total_steps_observed}_")
        lines.append("")
        order = [
            "RESOLVED",
            "NO_VISIBLE_SIGNAL",
            "ORPHANED_SEMANTIC_SIGNAL",
            "TARGET_CHANGED",
            "AMBIGUOUS_TARGET",
            "ENVIRONMENT_FAILURE",
            "SKIPPED",
            "UNKNOWN",
        ]
        for key in order:
            if key in ledger:
                pct = ledger[key] / total_steps_observed * 100
                lines.append(f"- `{key}`: {ledger[key]} ({pct:.1f}%)")
        for key in sorted(ledger):
            if key not in order:
                pct = ledger[key] / total_steps_observed * 100
                lines.append(f"- `{key}`: {ledger[key]} ({pct:.1f}%)")

    lines.extend(["", "## By Site (resolution first)", ""])
    site_order = [s.key for s in EXPERIMENT_SITES]
    by_site = summary.get("by_site") or {}
    for site_key in site_order:
        if site_key not in by_site:
            continue
        data = by_site[site_key]
        lines.append(f"### {site_key}")
        lines.append(f"- Avg resolution rate: **{data['avg_resolution_rate'] * 100:.1f}%**")
        lines.append(f"- Runs: {data['runs']}")
        lines.append(f"- Workflow failures: {data['workflow_failures']}")
        if data.get("failure_categories"):
            cats = ", ".join(f"`{k}`={v}" for k, v in sorted(data["failure_categories"].items()))
            lines.append(f"- Failure categories: {cats}")
        lines.append("")

    lines.extend(["## Decision Thresholds", ""])
    if thresholds.get("stop_recommended"):
        lines.append(f"**STOP recommended:** {thresholds.get('stop_reason')}")
    else:
        lines.append("No stop gate triggered.")
    for decision in thresholds.get("decisions") or []:
        mark = "PASS" if decision.get("passed") else "—"
        lines.append(f"- `{decision['rule']}` [{mark}]: {decision['detail']}")

    lines.extend(["", "## Runs", ""])
    for result in results:
        wf = "WORKFLOW_FAIL" if result.workflow_failed else "WORKFLOW_OK"
        lines.append(
            f"- **{result.site}** resolution={result.resolution_rate * 100:.1f}% "
            f"({result.resolved_steps}/{result.total_steps}) [{wf}]"
        )
        if result.failure_category:
            lines.append(
                f"  - step {result.failed_step}: `{result.failure_category.value}` — {result.failure_reason}"
            )

    lines.append("")
    return "\n".join(lines)
