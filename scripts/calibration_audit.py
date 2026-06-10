"""Calibration audit -- Stage 2.3.

Measures how well the existing predicted_tier / predicted_score values
correlate with empirical success rates in the OutcomeLedger. This is
*measurement only* per Stage 2 authorization. No confidence-weighted
policies, no execution changes, no deferral logic -- just a number that
tells us whether today's heuristic predictions are worth anything.

Output:
    reports/calibration_audit_<timestamp>.json -- full bin breakdown
    stdout -- human-readable summary

Usage:
    python scripts/calibration_audit.py
    python scripts/calibration_audit.py --baseline <prior.json>  # compare

The "good" outcome of running this against current data is finding that
predicted_tier='HIGH' empirically succeeds at >90%, AMBIGUOUS at <70%,
LOW at <30%. If the bins are flat (every tier has the same empirical
rate), the heuristic is uninformative and Stage 4 may pick path C
(replace it).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

LEDGER_DIR = Path.home() / ".browsermind" / "outcome_ledger"
REPORT_DIR = Path("reports")


def _load_step_records() -> list[dict]:
    if not LEDGER_DIR.exists():
        return []
    out = []
    for p in LEDGER_DIR.glob("*.json"):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            data = blob.get("_data", blob)
        except Exception:
            continue
        if data.get("scope") == "step":
            out.append(data)
    return out


def calibration(records: list[dict], min_n_per_bin: int = 30) -> dict:
    """Pure aggregation: bin by predicted_tier, compute empirical success.

    ``min_n_per_bin``: bins with fewer than this many records are excluded from
    the tier_spread calculation. This prevents a 2-record UNREPLAYABLE bin from
    inflating the spread and triggering a false ``discriminative=True`` flag.
    The flag fires only when at least 2 qualifying bins remain after filtering.
    """
    bins: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "successes": 0, "score_sum": 0.0,
    })

    for r in records:
        m = r.get("metrics") or {}
        tier = m.get("predicted_tier") or "UNKNOWN"
        score = m.get("predicted_score")
        bins[tier]["n"] += 1
        if r.get("success"):
            bins[tier]["successes"] += 1
        if isinstance(score, (int, float)):
            bins[tier]["score_sum"] += float(score)

    rows = []
    for tier, b in bins.items():
        n = b["n"]
        empirical = (b["successes"] / n) if n else 0.0
        avg_score = (b["score_sum"] / n) if n else 0.0
        rows.append({
            "predicted_tier": tier,
            "n": n,
            "empirical_success_rate": empirical,
            "avg_predicted_score": avg_score,
            # Calibration error: distance between the avg score the system
            # claimed and the empirical success it actually delivered. Lower
            # is better; 0 = perfectly calibrated for this bin.
            "calibration_error": abs(avg_score - empirical) if n else None,
        })

    # Order by tier: HIGH > AMBIGUOUS > LOW > UNKNOWN.
    tier_order = {"HIGH": 0, "MEDIUM": 1, "AMBIGUOUS": 2, "LOW": 3, "UNKNOWN": 9}
    rows.sort(key=lambda r: tier_order.get(r["predicted_tier"], 5))

    # Discrimination signal -- does the heuristic actually separate bins?
    # Only include bins with n >= min_n_per_bin so small outlier bins
    # don't inflate the spread (P1.8: CAL1 fix).
    qualifying_rates = [r["empirical_success_rate"] for r in rows if r["n"] >= min_n_per_bin]
    spread = (max(qualifying_rates) - min(qualifying_rates)) if len(qualifying_rates) >= 2 else 0.0

    # Per-strategy breakdown -- how does each resolver strategy perform?
    by_strategy: dict[str, dict] = defaultdict(lambda: {"n": 0, "successes": 0})
    for r in records:
        m = r.get("metrics") or {}
        strategy = m.get("resolved_by") or "<failed>"
        by_strategy[strategy]["n"] += 1
        if r.get("success"):
            by_strategy[strategy]["successes"] += 1
    strategy_rows = sorted(
        [
            {
                "strategy": s,
                "n": v["n"],
                "successes": v["successes"],
                "empirical_success_rate": v["successes"] / v["n"] if v["n"] else 0.0,
            }
            for s, v in by_strategy.items()
        ],
        key=lambda r: -r["n"],
    )

    return {
        "total_records": len(records),
        "tiers": rows,
        "tier_spread": spread,
        "discriminative": spread >= 0.20,
        "strategies": strategy_rows,
    }


def diff_against(current: dict, baseline_path: Path) -> Optional[dict]:
    if not baseline_path.exists():
        return None
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    deltas = []
    base_by_tier = {r["predicted_tier"]: r for r in baseline.get("tiers", [])}
    for cur in current.get("tiers", []):
        prev = base_by_tier.get(cur["predicted_tier"])
        if not prev:
            continue
        deltas.append({
            "predicted_tier": cur["predicted_tier"],
            "n_delta": cur["n"] - prev["n"],
            "empirical_delta": cur["empirical_success_rate"] - prev["empirical_success_rate"],
            "calibration_error_delta": (
                (cur["calibration_error"] or 0) - (prev["calibration_error"] or 0)
            ),
        })
    return {
        "baseline_path": str(baseline_path),
        "tier_spread_delta": current["tier_spread"] - baseline.get("tier_spread", 0),
        "tiers": deltas,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibration audit of predicted_tier")
    ap.add_argument("--baseline", default=None, help="Prior calibration_audit JSON to diff against")
    ap.add_argument("--output", default=None, help="Output JSON path (default: reports/calibration_audit_<ts>.json)")
    ap.add_argument("--min-n-per-bin", type=int, default=30, dest="min_n_per_bin",
                    help="Minimum records per tier bin to include in tier_spread (default 30).")
    args = ap.parse_args()

    records = _load_step_records()
    if not records:
        print("[calibration] No step records found in ledger.")
        return 1

    result = calibration(records, min_n_per_bin=args.min_n_per_bin)
    if args.baseline:
        d = diff_against(result, Path(args.baseline))
        if d:
            result["delta_vs_baseline"] = d

    out_path = Path(args.output) if args.output else (
        REPORT_DIR / f"calibration_audit_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 64)
    print("CALIBRATION AUDIT")
    print("=" * 64)
    print(f"Total step records:  {result['total_records']}")
    print(f"Tier spread:         {result['tier_spread']:.2f}  "
          f"({'discriminative' if result['discriminative'] else 'flat'})")
    print()
    print(f"{'TIER':<12} {'N':>5} {'EMPIRICAL':>10} {'AVG SCORE':>10} {'CAL ERR':>9}")
    print("-" * 64)
    for r in result["tiers"]:
        ce = f"{r['calibration_error']:.2f}" if r["calibration_error"] is not None else "--"
        print(f"{r['predicted_tier']:<12} {r['n']:>5} "
              f"{r['empirical_success_rate']:>10.0%} "
              f"{r['avg_predicted_score']:>10.2f} "
              f"{ce:>9}")
    print()
    print("STRATEGY BREAKDOWN (top 8 by volume)")
    print("-" * 64)
    print(f"{'STRATEGY':<28} {'N':>5} {'EMPIRICAL':>10}")
    for r in result["strategies"][:8]:
        print(f"{r['strategy']:<28} {r['n']:>5} {r['empirical_success_rate']:>10.0%}")
    print()
    if "delta_vs_baseline" in result:
        d = result["delta_vs_baseline"]
        print("DELTA vs BASELINE")
        print("-" * 64)
        print(f"  Tier spread delta: {d['tier_spread_delta']:+.2f}")
        for t in d["tiers"]:
            print(f"  {t['predicted_tier']:<10} "
                  f"n {t['n_delta']:+d}  "
                  f"empirical {t['empirical_delta']:+.0%}  "
                  f"cal_err {t['calibration_error_delta']:+.2f}")
        print()
    print(f"Report: {out_path}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
