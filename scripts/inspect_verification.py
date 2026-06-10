"""One-shot diagnostic: replay each benchmark site and print the verification
fields produced by ReplayResult. Reads the same templates run_fresh_benchmark
uses. Not part of the benchmark -- purely for reporting Patch 1 + 2 effects."""
from __future__ import annotations
import asyncio
import json
import os
import sys

os.environ.setdefault("BM_HEADLESS", "1")

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site
from browsermind_core.experiments.reliability_metrics import evaluate_bc_gate

SITES = ["saucedemo", "static_baseline", "demoqa", "aria_internet"]
STORE = os.environ.get("BM_STORE", os.path.expanduser("~/.browsermind"))


async def main():
    harness = ReplayExperimentHarness(STORE, headless=True, persona_id="pilot")
    rows = []
    for site_key in SITES:
        site = get_site(site_key)
        try:
            template = harness.load_template(site.suggested_workflow)
        except Exception as e:
            print(f"[{site_key}] load_template failed: {e}", file=sys.stderr)
            continue
        try:
            report = await harness.replay(site, template)
        except Exception as e:
            print(f"[{site_key}] replay failed: {e}", file=sys.stderr)
            continue
        result = harness.result_from_report(
            site=site, template=template, report=report,
            demonstration_id=None, ground_truth=None,
        )
        rows.append((site_key, result, report))

    print()
    print("=" * 78)
    print("PATCH 1 + 2 -- VERIFICATION RESULTS")
    print("=" * 78)
    print()

    fmt = "{:<18} {:<12} {:<14} {:<20} {:<12}"
    print(fmt.format("site", "state_match", "verifier_result", "task_completion_rate", "task_completed"))
    print(fmt.format("-" * 18, "-" * 12, "-" * 14, "-" * 20, "-" * 12))
    for site_key, result, report in rows:
        vr = result.verification_report or {}
        print(fmt.format(
            site_key,
            str(vr.get("state_match")),
            str(vr.get("verifier_result")),
            str(result.task_completion_rate),
            str(result.task_completed),
        ))

    print()
    print("BC GATE INPUTS (per-site reliability_metrics)")
    print("-" * 78)
    for site_key, result, report in rows:
        m = result.reliability_metrics or {}
        print(f"{site_key}:")
        print(f"  resolution_rate:                  {m.get('resolution_rate')}")
        print(f"  false_positive_resolution_rate:   {m.get('false_positive_resolution_rate')}")
        print(f"  resolution_accuracy:              {m.get('resolution_accuracy')}")
        print(f"  task_completion_rate:             {m.get('task_completion_rate')}")
        print(f"  gate_ready:                       {m.get('gate_ready')}")

    print()
    print("BC GATE (per-site)")
    print("-" * 78)
    for site_key, result, _ in rows:
        gate = evaluate_bc_gate(result.reliability_metrics or {})
        print(f"{site_key}: passed={gate['passed']} checks={gate['checks']}")

    print()
    print("verification_report CONTENTS (full)")
    print("-" * 78)
    for site_key, result, _ in rows:
        print(f"--- {site_key} ---")
        print(json.dumps(result.verification_report, indent=2, default=str))
        print()

    print("verification_error CONTENTS (any failures)")
    print("-" * 78)
    for site_key, result, _ in rows:
        if result.verification_error:
            print(f"--- {site_key} ---")
            print(json.dumps(result.verification_error, indent=2, default=str))


asyncio.run(main())
