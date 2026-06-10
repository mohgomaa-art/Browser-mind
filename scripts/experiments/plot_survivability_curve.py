#!/usr/bin/env python3
"""
Survivability Curve Printer

Reads drift_matrix.json and prints a formatted Survivability Curve table.
Does not require matplotlib — pure terminal output + JSON summary.

Usage:
    python scripts/experiments/plot_survivability_curve.py
    python scripts/experiments/plot_survivability_curve.py --input path/to/drift_matrix.json
"""
import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT_DIR / "reports" / "survivability" / "drift" / "drift_matrix.json"


def bar(rate: float, width: int = 30) -> str:
    """ASCII progress bar."""
    filled = int(rate * width)
    return "█" * filled + "░" * (width - filled)


def main():
    parser = argparse.ArgumentParser(description="Survivability Curve Printer")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to drift_matrix.json")
    parser.add_argument("--output", default=None, help="Optional path to write summary JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] drift_matrix.json not found at: {input_path}")
        print("Run scripts/experiments/controlled_drift.py first.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Sort by severity
    data.sort(key=lambda x: x.get("severity_level", 99))

    print()
    print("=" * 70)
    print("  BrowserMind Survivability Curve")
    print("=" * 70)
    print(f"  {'Sv':<4} {'Drift Type':<28} {'Resolution':>10}  {'Bar'}")
    print("-" * 70)

    for entry in data:
        sv   = entry.get("severity_level", "?")
        dt   = entry.get("drift_type", "?")
        rate = entry.get("resolution_rate", 0.0)
        ok   = entry.get("workflow_success", False)
        status = "✓" if ok else "✗"

        print(f"  {sv:<4} {dt:<28} {rate:>9.1%}  {bar(rate)} {status}")

        # Show representation breakdown if available
        breakdown = entry.get("representation_breakdown") or {}
        if breakdown:
            parts = "  ".join(f"{k}={v}" for k, v in breakdown.items())
            print(f"  {'':4} {'':28} {'':10}  ↳ {parts}")

    print("-" * 70)

    # Find survivability boundary
    survived = [e for e in data if e.get("workflow_success")]
    failed   = [e for e in data if not e.get("workflow_success")]

    if survived and failed:
        last_survived = max(e["severity_level"] for e in survived)
        first_failed  = min(e["severity_level"] for e in failed)
        print(f"\n  Survivability boundary: severity {last_survived} → {first_failed}")
        boundary_drift = next((e["drift_type"] for e in data if e["severity_level"] == first_failed), "?")
        print(f"  First fatal drift type: {boundary_drift}")
    elif not failed:
        print(f"\n  ALL {len(survived)} drift levels survived.")
    else:
        print(f"\n  NO drift levels survived — baseline failure.")

    print()

    # JSON summary
    summary = {
        "total_drift_levels": len(data),
        "survived_count": len(survived),
        "failed_count": len(failed),
        "survivability_boundary_severity": max((e["severity_level"] for e in survived), default=None),
        "first_fatal_severity": min((e["severity_level"] for e in failed), default=None),
        "curve": [
            {
                "severity_level": e["severity_level"],
                "drift_type": e["drift_type"],
                "resolution_rate": e["resolution_rate"],
                "workflow_success": e["workflow_success"],
            }
            for e in data
        ]
    }

    out_path = args.output or str(DEFAULT_INPUT.parent / "survivability_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary JSON → {out_path}")


if __name__ == "__main__":
    main()
