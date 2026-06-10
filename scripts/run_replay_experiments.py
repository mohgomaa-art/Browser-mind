#!/usr/bin/env python3
"""
Replay Validation Experiment Runner.

Record -> compile -> replay across the fixed site set and collect empirical evidence.
No new architecture. No learning. No agents.

Usage:
  python scripts/run_replay_experiments.py run --site static_baseline
  python scripts/run_replay_experiments.py run --all
  python scripts/run_replay_experiments.py replay --site saucedemo --template exp_saucedemo_checkout
  python scripts/run_replay_experiments.py report --dir reports/replay_experiments/latest
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.report_generator import write_summary_report
from browsermind_core.experiments.sites import EXPERIMENT_SITES, GATE_MIN_RESOLUTION, GATE_SITES, site_keys


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "reports" / "replay_experiments" / stamp


def _write_latest_pointer(output_dir: Path) -> None:
    latest = ROOT / "reports" / "replay_experiments" / "latest"
    latest.write_text(str(output_dir.resolve()), encoding="utf-8")


async def _run_sites(args) -> int:
    harness = ReplayExperimentHarness(
        store_dir=args.store,
        headless=args.headless,
        persona_id=args.persona,
    )
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    sites = site_keys() if args.all else [args.site]

    if not args.all and not args.site:
        print("Specify --site <key> or --all", file=sys.stderr)
        return 2

    results = []
    for site_key in sites:
        try:
            if args.replay_only:
                site = next(s for s in EXPERIMENT_SITES if s.key == site_key)
                template_name = args.template or site.suggested_workflow
                template = harness.load_template(template_name)
                report = await harness.replay(site, template)
                result = harness.result_from_report(site=site, template=template, report=report)
            else:
                result = await harness.run_full(
                    site_key,
                    template_name=args.template,
                    skip_record=False,
                )
            path = harness.save_result(result, output_dir)
            print(json.dumps(result.model_dump(mode="json"), indent=2))
            print(f"Saved: {path}")
            results.append(result)

            if args.all and not args.force_continue and site_key in GATE_SITES:
                if result.resolution_rate < GATE_MIN_RESOLUTION:
                    print(
                        f"\n[GATE STOP] {site_key} resolution "
                        f"{result.resolution_rate * 100:.1f}% < {GATE_MIN_RESOLUTION * 100:.0f}%",
                        file=sys.stderr,
                    )
                    print("Investigate engine/recorder before continuing.", file=sys.stderr)
                    print("Use --force-continue to override.", file=sys.stderr)
                    break
        except Exception as exc:
            print(f"[ERROR] {site_key}: {exc}", file=sys.stderr)
            if args.fail_fast:
                return 1

    if results:
        json_path, md_path = write_summary_report(results, output_dir)
        _write_latest_pointer(output_dir)
        print(f"\nSummary JSON: {json_path}")
        print(f"Summary Markdown: {md_path}")

    failures = sum(1 for r in results if not r.replay_success)
    return 1 if failures and args.fail_fast else 0


def _report(args) -> int:
    report_dir = Path(args.dir)
    if not report_dir.exists():
        latest_ptr = ROOT / "reports" / "replay_experiments" / "latest"
        if latest_ptr.exists():
            report_dir = Path(latest_ptr.read_text(encoding="utf-8").strip())
        else:
            print(f"Report directory not found: {args.dir}", file=sys.stderr)
            return 2

    harness = ReplayExperimentHarness(store_dir=args.store)
    results = harness.load_results(report_dir)
    if not results:
        print(f"No result files in {report_dir}", file=sys.stderr)
        return 2

    json_path, md_path = write_summary_report(results, report_dir)
    print(f"Updated {json_path}")
    print(f"Updated {md_path}")
    print(md_path.read_text(encoding="utf-8"))
    return 0


def _list_sites(_args) -> int:
    for site in EXPERIMENT_SITES:
        print(f"{site.key:16}  {site.label:24}  template={site.suggested_workflow}")
        print(f"{'':16}  {site.operator_hint}")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BrowserMind replay validation experiments")
    parser.add_argument("--store", default=str(Path.home() / ".browsermind"))
    parser.add_argument("--persona", default="validator")
    parser.add_argument("--headless", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Record, compile, and replay")
    run_p.add_argument("--site", choices=site_keys())
    run_p.add_argument("--all", action="store_true")
    run_p.add_argument("--template")
    run_p.add_argument("--output-dir")
    run_p.add_argument("--fail-fast", action="store_true")
    run_p.add_argument("--force-continue", action="store_true", help="Ignore resolution gates when running --all")
    run_p.set_defaults(replay_only=False, command="run")

    replay_p = sub.add_parser("replay", help="Replay an existing compiled template")
    replay_p.add_argument("--site", required=True, choices=site_keys())
    replay_p.add_argument("--template")
    replay_p.add_argument("--output-dir")
    replay_p.add_argument("--fail-fast", action="store_true")
    replay_p.set_defaults(replay_only=True, all=False, command="replay")

    report_p = sub.add_parser("report", help="Regenerate summary from saved results")
    report_p.add_argument("--dir", default="reports/replay_experiments/latest")

    sub.add_parser("sites", help="List experiment sites").set_defaults(func=_list_sites)

    args = parser.parse_args()
    if args.command == "report":
        return _report(args)
    if args.command == "sites":
        return _list_sites(args)
    return asyncio.run(_run_sites(args))


if __name__ == "__main__":
    raise SystemExit(main())
