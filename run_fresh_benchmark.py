"""
Fresh Benchmark — Phase A / B / C / D

Run after recorder fixes. Produces:
  reports/fresh_benchmark/recorder_integrity.json  (Phase A)
  reports/fresh_benchmark/summary.json             (Phase B/C/D)
  reports/fresh_benchmark/summary.md               (Phase B/C/D)

Usage:
  python run_fresh_benchmark.py

Environment variables (optional):
  BM_SITES        comma-separated site keys (default: saucedemo,static_baseline,demoqa,aria_internet)
  BM_HEADLESS     1 to run headless (default: 0 — browser visible so operator can record)
  BM_PERSONA      persona name (default: pilot)
  BM_STORE        path to store dir (default: browsermind_core default)
  BM_SKIP_RECORD  1 to skip recording and reuse existing templates (default: 0)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# -- Site targets --------------------------------------------------------------

DEFAULT_SITES = ["saucedemo", "static_baseline", "demoqa", "aria_internet"]
SITES = [s.strip() for s in os.environ.get("BM_SITES", ",".join(DEFAULT_SITES)).split(",") if s.strip()]
HEADLESS = os.environ.get("BM_HEADLESS", "0") == "1"
PERSONA = os.environ.get("BM_PERSONA", "pilot")
SKIP_RECORD = os.environ.get("BM_SKIP_RECORD", "0") == "1"

try:
    from browsermind_core.console.session import DEFAULT_STORE
    STORE = os.environ.get("BM_STORE", DEFAULT_STORE)
except Exception:
    STORE = os.environ.get("BM_STORE", ".browsermind")

OUT_DIR = Path("reports/fresh_benchmark")
# Convention: per-site ground-truth dataset at ground_truth/<site_key>.json.
# Each file is the JSON-serialised form of GroundTruthDataset.
GROUND_TRUTH_DIR = Path(os.environ.get("BM_GROUND_TRUTH_DIR", "ground_truth"))


def _load_ground_truth(site_key: str):
    """Load a GroundTruthDataset for a site, or None if no file exists.

    The loader does not invent annotations. Any I/O or validation error is
    surfaced to the operator rather than swallowed — a stale/invalid ground
    truth file must not be silently treated as "no ground truth".
    """
    from browsermind_core.experiments.ground_truth import GroundTruthDataset

    path = GROUND_TRUTH_DIR / f"{site_key}.json"
    if not path.exists():
        return None
    return GroundTruthDataset.model_validate_json(path.read_text(encoding="utf-8"))


# -- Phase A: Recorder integrity check -----------------------------------------

def check_recorder_integrity(session) -> dict:
    """
    Examine a fresh DemonstrationSession for known recorder corruption patterns.

    Returns a dict with:
      passed: bool
      violations: list of {step_seq, violation_type, detail}
    """
    violations = []

    for step in session.actions:
        if step.action_type == "session":
            continue

        role = (step.target_role or "").strip().lower()
        name = (step.target_name or "").strip()
        value = (step.value or "").strip()

        # Violation 1: RECORDER_MISMATCH — name equals typed value
        # After the fix, text inputs should use placeholder/label, not the typed value.
        # Heuristic: if action is fill AND name == value AND len(name) > 3, flag it.
        if step.action_type == "fill" and value and name and name == value and len(name) > 3:
            violations.append({
                "step_seq": step.seq,
                "violation_type": "RECORDER_MISMATCH",
                "detail": f"target_name '{name}' equals typed value — recorder captured input content as identity",
                "role": role,
                "name": name,
                "value": value,
            })

        # Violation 2: NO_VISIBLE_SIGNAL — submit/click with form role and empty name
        if step.action_type in ("submit", "click") and role == "form" and not name:
            violations.append({
                "step_seq": step.seq,
                "violation_type": "NO_VISIBLE_SIGNAL",
                "detail": f"submit action recorded on form element with empty name — submit button not resolved",
                "role": role,
                "name": name,
            })

        # Violation 3: ROLE_DRIFT — HTML tag names recorded as role (not ARIA role)
        HTML_TAG_ROLES = {"span", "div", "input", "h1", "h2", "h3", "h4", "h5", "h6",
                          "p", "ul", "ol", "li", "section", "article", "header", "footer"}
        if role in HTML_TAG_ROLES and role not in {"input"}:
            violations.append({
                "step_seq": step.seq,
                "violation_type": "ROLE_DRIFT",
                "detail": f"role='{role}' is an HTML tag, not an ARIA role — Playwright get_by_role will fail",
                "role": role,
                "name": name,
            })

        # Violation 4: GENERIC_ROLE — role=generic or role='' with no name
        if role in ("generic", "") and not name:
            violations.append({
                "step_seq": step.seq,
                "violation_type": "EMPTY_SEMANTICS",
                "detail": f"role='{role}' with empty name — no usable semantic identifier",
                "role": role,
                "name": name,
            })

    return {
        "site": getattr(session, "environment_family", ""),
        "demonstration_id": str(session.id),
        "total_steps": len([a for a in session.actions if a.action_type != "session"]),
        "violations": violations,
        "passed": len(violations) == 0,
        "violation_count": len(violations),
    }


# -- Navigation gap check ------------------------------------------------------

def check_navigation_gaps(session) -> list[dict]:
    """
    Check for navigation gaps — URL changes not captured as navigate steps.
    After the compiler fix, these should be injected. This checks the raw session.
    """
    gaps = []
    last_url = getattr(session, "start_url", "") or ""
    for step in session.actions:
        if step.action_type == "session":
            continue
        current_url = (step.url or "").strip()
        if not current_url:
            continue
        if step.action_type != "navigate" and last_url:
            from urllib.parse import urlparse
            p_cur = urlparse(current_url)
            p_last = urlparse(last_url)
            if p_cur.netloc == p_last.netloc and p_cur.path.rstrip("/") != p_last.path.rstrip("/"):
                gaps.append({
                    "step_seq": step.seq,
                    "action_type": step.action_type,
                    "from_url": last_url,
                    "to_url": current_url,
                    "note": "URL path changed without navigate step — compiler will inject one",
                })
        if current_url:
            last_url = current_url
    return gaps


# -- Main benchmark loop -------------------------------------------------------

async def run_benchmark():
    from browsermind_core.experiments.harness import ReplayExperimentHarness
    from browsermind_core.experiments.sites import get_site
    from browsermind_core.experiments.report_generator import write_summary_report

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    harness = ReplayExperimentHarness(STORE, headless=HEADLESS, persona_id=PERSONA)
    all_results = []
    integrity_reports = []

    for site_key in SITES:
        print(f"\n{'='*60}")
        print(f"SITE: {site_key}")
        print(f"{'='*60}")

        try:
            site = get_site(site_key)
        except KeyError:
            print(f"  ERROR: site '{site_key}' not found in registry. Skipping.")
            continue

        # Phase A + B: Record fresh (unless skipping)
        if not SKIP_RECORD:
            print(f"\n[PHASE A] Recording fresh demonstration for {site_key}")
            print(f"  Hint: {site.operator_hint}")
            try:
                session = await harness.record(site)
            except Exception as e:
                print(f"  RECORD FAILED: {e}")
                continue

            # Recorder integrity check
            integrity = check_recorder_integrity(session)
            nav_gaps = check_navigation_gaps(session)
            integrity["navigation_gaps"] = nav_gaps
            integrity_reports.append(integrity)

            if not integrity["passed"]:
                print(f"\n  [PHASE A] INTEGRITY VIOLATIONS ({integrity['violation_count']}):")
                for v in integrity["violations"]:
                    print(f"    step {v['step_seq']}: [{v['violation_type']}] {v['detail']}")
                print(f"  WARNING: Recording has violations. Replay may fail for non-genuine reasons.")
                print(f"  Continuing with replay to measure actual failure modes.")
            else:
                print(f"  [PHASE A] PASS — no recorder integrity violations.")
                if nav_gaps:
                    print(f"  Navigation gaps detected ({len(nav_gaps)}) — compiler will inject navigate steps:")
                    for g in nav_gaps:
                        print(f"    step {g['step_seq']}: {g['from_url']} → {g['to_url']}")

            # Compile — use a timestamped name to avoid unique-name constraint on re-runs
            fresh_template_name = f"{site.suggested_workflow}_fresh_{ts}"
            try:
                template = harness.compile(session, fresh_template_name)
            except Exception as e:
                print(f"  COMPILE FAILED: {e}")
                continue
        else:
            print(f"\n[PHASE B] Using existing template for {site_key} (skip_record=True)")
            session = None
            integrity_reports.append({"site": site_key, "passed": None, "note": "skip_record — not checked"})
            try:
                template = harness.load_template(site.suggested_workflow)
            except Exception as e:
                print(f"  LOAD TEMPLATE FAILED: {e}")
                continue

        # Phase B: Replay
        print(f"\n[PHASE B] Replaying {site_key}...")
        try:
            report = await harness.replay(site, template)
            ground_truth = _load_ground_truth(site_key)
            if ground_truth is not None:
                print(f"  Ground truth loaded: {ground_truth.dataset_id} ({len(ground_truth.annotations)} annotations)")
            result = harness.result_from_report(
                site=site,
                template=template,
                report=report,
                demonstration_id=session.id if session else None,
                ground_truth=ground_truth,
            )
            all_results.append(result)

            # Per-run console output
            wf = "WORKFLOW_OK" if result.replay_success else "WORKFLOW_FAIL"
            print(f"  Resolution: {result.resolution_rate * 100:.1f}%  "
                  f"({result.resolved_steps}/{result.total_steps} steps)  [{wf}]")
            if result.failure_category:
                print(f"  Failure: step {result.failed_step} — "
                      f"[{result.failure_category.value}] {result.failure_reason}")

            # Step-level breakdown
            if result.step_outcomes:
                counts = Counter(s["outcome"] for s in result.step_outcomes)
                print(f"  Step outcomes: {dict(counts)}")

        except Exception as e:
            print(f"  REPLAY FAILED: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Phase C/D: Write reports
    print(f"\n{'='*60}")
    print(f"PHASE C/D — FAILURE TAXONOMY & DISTRIBUTION")
    print(f"{'='*60}")

    # Write integrity report
    integrity_path = OUT_DIR / "recorder_integrity.json"
    integrity_path.write_text(
        json.dumps({
            "timestamp": ts,
            "sites_checked": SITES,
            "reports": integrity_reports,
            "overall_passed": all(r.get("passed", False) for r in integrity_reports if r.get("passed") is not None),
        }, indent=2),
        encoding="utf-8",
    )
    print(f"\nRecorder integrity: {integrity_path}")

    if not all_results:
        print("\nNo replay results produced. Check errors above.")
        return

    # Write summary report (includes step ledger = failure distribution)
    json_path, md_path = write_summary_report(all_results, OUT_DIR)
    print(f"Summary JSON:       {json_path}")
    print(f"Summary Markdown:   {md_path}")

    # BC gate — only meaningful when at least one run had ground-truth
    # judged outcomes. Otherwise FPR is None and the gate would always fail
    # for non-substantive reasons.
    from browsermind_core.experiments.reliability_metrics import evaluate_bc_gate

    judged_runs = [
        r for r in all_results
        if r.reliability_metrics
        and r.reliability_metrics.get("false_positive_resolution_rate") is not None
    ]
    gate_path = OUT_DIR / "bc_gate.json"
    if judged_runs:
        # Aggregate across judged runs: weight FPR/RR by judged or attempted step
        # counts, average task_completion_rate. This avoids needing a new
        # aggregation primitive while still producing a per-benchmark verdict.
        total_judged = 0
        total_resolved = 0
        total_attempted = 0
        weighted_fp = 0
        weighted_correct = 0
        task_rates = []
        for r in judged_runs:
            m = r.reliability_metrics
            judged = m.get("resolved_correct_steps", 0) + m.get("resolved_incorrect_steps", 0)
            total_judged += judged
            weighted_fp += m.get("resolved_incorrect_steps", 0)
            weighted_correct += m.get("resolved_correct_steps", 0)
            total_resolved += m.get("resolved_steps", 0)
            total_attempted += m.get("attempted_steps", 0)
            tcr = m.get("task_completion_rate")
            if tcr is not None:
                task_rates.append(tcr)

        agg = {
            "resolution_rate": round(total_resolved / total_attempted, 4) if total_attempted else 0.0,
            "false_positive_resolution_rate": round(weighted_fp / total_judged, 4) if total_judged else None,
            "resolution_accuracy": round(weighted_correct / total_judged, 4) if total_judged else None,
            "task_completion_rate": round(sum(task_rates) / len(task_rates), 4) if task_rates else None,
        }
        gate = evaluate_bc_gate(agg)
        gate_payload = {
            "schema": "browsermind.bc_gate.benchmark.v1",
            "evaluated": True,
            "judged_runs": len(judged_runs),
            "total_runs": len(all_results),
            "aggregated_metrics": agg,
            "gate": gate,
        }
        print(f"\n  BC GATE: {'PASS' if gate['passed'] else 'FAIL'}  "
              f"(judged_runs={len(judged_runs)}/{len(all_results)})")
        for name, ok in gate["checks"].items():
            print(f"    {name:<35} {'PASS' if ok else 'FAIL'}")
    else:
        gate_payload = {
            "schema": "browsermind.bc_gate.benchmark.v1",
            "evaluated": False,
            "reason": "no ground-truth judged metrics available; supply ground_truth/<site>.json to enable",
            "judged_runs": 0,
            "total_runs": len(all_results),
        }
        print("\n  BC GATE: SKIPPED — no ground-truth judged outcomes "
              f"(supply {GROUND_TRUTH_DIR}/<site>.json to enable)")
    gate_path.write_text(json.dumps(gate_payload, indent=2), encoding="utf-8")
    print(f"BC gate result:     {gate_path}")

    # Phase D: Print dominant bottleneck to stdout
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"\n{'='*60}")
    print(f"FAILURE DISTRIBUTION (step-level)")
    print(f"{'='*60}")
    ledger = summary.get("step_ledger", {})
    total_steps = sum(ledger.values())
    if total_steps:
        order = ["RESOLVED_CORRECT", "RESOLVED_UNJUDGED", "RESOLVED_INCORRECT",
                 "NO_VISIBLE_SIGNAL", "ORPHANED_SEMANTIC_SIGNAL",
                 "TARGET_CHANGED", "AMBIGUOUS_TARGET",
                 "AMBIGUOUS_IDENTITY", "ENVIRONMENT_FAILURE", "SKIPPED", "UNKNOWN"]
        for key in order:
            if key in ledger:
                pct = ledger[key] / total_steps * 100
                bar = "#" * int(pct / 2)
                print(f"  {key:<35} {ledger[key]:>4} ({pct:5.1f}%)  {bar}")
        for key in sorted(ledger):
            if key not in order:
                pct = ledger[key] / total_steps * 100
                bar = "#" * int(pct / 2)
                print(f"  {key:<35} {ledger[key]:>4} ({pct:5.1f}%)  {bar}")
        print(f"\n  Total steps observed: {total_steps}")

    dom = summary.get("decision_thresholds", {}).get("dominant_failure_category")
    if dom:
        print(f"\n  DOMINANT BOTTLENECK: [{dom['category']}] ({dom['share']*100:.0f}% of failures)")
        print(f"  IMPLICATION: {dom['implication']}")
    else:
        print(f"\n  No dominant bottleneck (>75% share) detected.")
        print(f"  Failure categories:")
        for cat, count in sorted(summary.get("failure_category_totals", {}).items(),
                                  key=lambda x: -x[1]):
            share = count / max(1, len(all_results))
            print(f"    [{cat}]: {count} runs ({share*100:.0f}%)")

    thresholds = summary.get("decision_thresholds", {})
    if thresholds.get("stop_recommended"):
        print(f"\n  STOP GATE TRIGGERED: {thresholds['stop_reason']}")
    else:
        print(f"\n  No stop gate triggered. Proceed with bottleneck analysis.")

    print(f"\nDone. Reports in: {OUT_DIR.resolve()}")

    # M5+M6+M7: end-of-batch session cleanup. The harness keeps each
    # AuthSession alive across replays for continuity; close them now.
    await harness.aclose()


if __name__ == "__main__":
    asyncio.run(run_benchmark())
