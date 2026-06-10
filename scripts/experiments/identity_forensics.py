"""Identity Forensics — P4E Task 2.

Runs N replays and for every AMBIGUOUS_IDENTITY step dumps all candidate signals:
  - role, name, tag, nearest_container_label, data_test_ancestor, position_in_collection
  - candidate_count, identity_confidence

Output: reports/identity_forensics/<stamp>/signals.json

Usage:
    python scripts/experiments/identity_forensics.py --target saucedemo --runs 3
"""
import asyncio
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness


async def run_forensics(site_key: str, runs: int):
    harness = ReplayExperimentHarness()
    template_name = f"exp_{site_key}_checkout"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / "reports" / "identity_forensics" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    all_ambiguous = []
    run_summaries = []

    print(f"\n=== Identity Forensics: {site_key} ({runs} runs) ===\n")

    for i in range(runs):
        print(f"Run {i + 1}/{runs}...")
        try:
            result = await harness.run_full(site_key, template_name=template_name, skip_record=True)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        ambiguous_in_run = [s for s in result.step_outcomes if s.get("outcome") == "AMBIGUOUS_IDENTITY"]
        run_summaries.append({
            "run": i + 1,
            "total_steps": result.total_steps,
            "resolved_steps": result.resolved_steps,
            "ambiguous_steps": result.ambiguous_steps,
            "ambiguity_rate": result.ambiguity_rate,
            "replay_success": result.replay_success,
            "ambiguous_seqs": [s["seq"] for s in ambiguous_in_run],
        })

        for step in ambiguous_in_run:
            all_ambiguous.append({
                "run": i + 1,
                "seq": step["seq"],
                "role": step["role"],
                "name": step["name"],
                "candidate_count": step.get("candidate_count", 0),
                "identity_confidence": step.get("identity_confidence", 0.0),
                "candidates": step.get("candidates_info", []),
            })

        print(f"  ambiguity_rate={result.ambiguity_rate:.2f}  "
              f"ambiguous_steps={result.ambiguous_steps}  "
              f"replay_success={result.replay_success}")

    # Aggregate: count by step seq
    from collections import Counter
    seq_counts = Counter(a["seq"] for a in all_ambiguous)

    # Full forensics report
    report = {
        "site": site_key,
        "runs": runs,
        "total_ambiguous_events": len(all_ambiguous),
        "ambiguity_by_step": dict(seq_counts.most_common()),
        "overall_ambiguity_rate": round(
            sum(r["ambiguity_rate"] for r in run_summaries) / len(run_summaries), 4
        ) if run_summaries else 0.0,
        "run_summaries": run_summaries,
        "ambiguous_events": all_ambiguous,
    }

    signals_path = output_dir / "signals.json"
    signals_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary
    print(f"\n{'='*50}")
    print(f"IDENTITY FORENSICS SUMMARY")
    print(f"{'='*50}")
    print(f"  Total runs             : {runs}")
    print(f"  Total AMBIGUOUS events : {len(all_ambiguous)}")
    print(f"  Overall ambiguity_rate : {report['overall_ambiguity_rate']:.2%}")
    print(f"\n  Ambiguity by step:")
    for seq, count in seq_counts.most_common():
        step_info = next((a for a in all_ambiguous if a["seq"] == seq), {})
        print(f"    Step {seq:>2} | role='{step_info.get('role')}' name='{step_info.get('name')}' "
              f"| count={step_info.get('candidate_count')} | appeared {count}/{runs} runs")

    if all_ambiguous:
        print(f"\n  Sample candidates (Step {all_ambiguous[0]['seq']}):")
        for c in all_ambiguous[0].get("candidates", [])[:3]:
            print(f"    [{c.get('position_in_collection')}] "
                  f"tag={c.get('tag')} | "
                  f"container='{c.get('nearest_container_label')}' | "
                  f"data-test='{c.get('data_test_ancestor')}'")

    print(f"\n  Signals saved → {signals_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Identity Forensics — P4E Task 2")
    parser.add_argument("--target", default="saucedemo", help="Site key (default: saucedemo)")
    parser.add_argument("--runs", type=int, default=3, help="Number of replays (default: 3)")
    args = parser.parse_args()
    asyncio.run(run_forensics(args.target, args.runs))


if __name__ == "__main__":
    main()
