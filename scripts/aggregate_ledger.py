"""
aggregate_ledger.py

Reads ALL replay result JSONs from reports/replay_experiments/*/ and produces
a combined step ledger + failure breakdown table. Prints to stdout and writes
to reports/forensic/combined_ledger.md
"""
import json
from pathlib import Path
from collections import Counter

REPORTS_DIR = Path("reports/replay_experiments")
OUT_PATH    = Path("reports/forensic/combined_ledger.md")

def main():
    step_ledger   = Counter()
    workflow_rows = []

    for result_path in sorted(REPORTS_DIR.rglob("*.json")):
        if result_path.name in ("summary.json",):
            continue
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "workflow_id" not in data or "site" not in data:
            continue

        site     = data.get("site", "?")
        rate     = data.get("resolution_rate", 0)
        wf_fail  = data.get("workflow_failed", False)
        cat      = data.get("failure_category") or "--"
        reason   = data.get("failure_reason") or "--"
        step_num = data.get("failed_step") or "--"
        ts       = data.get("timestamp", "")[:19]

        recovery_tally = Counter()

        outcomes = data.get("step_outcomes", [])
        for s in outcomes:
            step_ledger[s["outcome"]] += 1
            if s.get("recovered_by"):
                recovery_tally[s["recovered_by"]] += 1

        # Fallback for old run (no step_outcomes)
        if not outcomes:
            step_ledger["RESOLVED"] += data.get("resolved_steps", 0)
            if wf_fail and cat != "--":
                step_ledger[cat] += 1

        workflow_rows.append({
            "ts": ts,
            "site": site,
            "rate": rate,
            "wf_fail": wf_fail,
            "cat": cat,
            "reason": reason,
            "failed_step": step_num,
            "recovery_tally": recovery_tally,
        })

    # -- Print step ledger ------------------------------------------------------
    total = sum(step_ledger.values())
    print(f"\n{'='*60}")
    print(f"  COMBINED STEP LEDGER  ({total} steps across {len(workflow_rows)} runs)")
    print(f"{'='*60}")

    order = [
        "RESOLVED",
        "TRANSITION_SUCCESS",
        "NO_VISIBLE_SIGNAL",
        "ORPHANED_SEMANTIC_SIGNAL",
        "TARGET_CHANGED",
        "AMBIGUOUS_TARGET",
        "ENVIRONMENT_FAILURE",
        "SKIPPED",
        "UNKNOWN",
    ]
    for key in order:
        if key in step_ledger:
            n   = step_ledger[key]
            pct = n / total * 100
            bar = "#" * int(pct / 2)
            print(f"  {key:<30} {n:4d}  ({pct:5.1f}%)  {bar}")
    for key in sorted(step_ledger):
        if key not in order:
            n   = step_ledger[key]
            pct = n / total * 100
            print(f"  {key:<30} {n:4d}  ({pct:5.1f}%)")

    # -- Per-run table ----------------------------------------------------------
    print(f"\n{'-'*90}")
    print(f"  {'Site':<18} {'Rate':>6}  {'WF':>4}  {'FailedAt':>8}  Category / Reason")
    print(f"{'-'*90}")
    for r in workflow_rows:
        wf = "FAIL" if r["wf_fail"] else "OK"
        print(
            f"  {r['site']:<18} {r['rate']:>6.2f}  {wf:>4}  "
            f"{str(r['failed_step']):>8}  {r['cat']}  --  {r['reason'][:50]}"
        )
    print()

    # -- Write markdown ---------------------------------------------------------
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Combined Step Ledger",
        "",
        f"**Total steps observed:** {total}  |  **Total runs:** {len(workflow_rows)}",
        "",
        "## Signal-Availability Census",
        "",
        "| Outcome | Count | Share |",
        "|---------|------:|------:|",
    ]
    for key in order:
        if key in step_ledger:
            n   = step_ledger[key]
            pct = n / total * 100
            lines.append(f"| `{key}` | {n} | {pct:.1f}% |")
    for key in sorted(step_ledger):
        if key not in order:
            n   = step_ledger[key]
            pct = n / total * 100
            lines.append(f"| `{key}` | {n} | {pct:.1f}% |")

    # -- Recovery Ledger --
    lines += [
        "",
        "## Recovery Ledger",
        "",
        "| Recovery Method | Count |",
        "|-----------------|-------|",
    ]
    global_recovery = Counter()
    for r in workflow_rows:
        global_recovery.update(r["recovery_tally"])
        
    if not global_recovery:
        lines.append("| *(No recoveries recorded)* | 0 |")
    else:
        for method, count in global_recovery.most_common():
            lines.append(f"| `{method}` | {count} |")

    lines += [
        "",
        "## Per-Run Results",
        "",
        "| Timestamp | Site | Rate | WF | Failed Step | Category | Reason |",
        "|-----------|------|-----:|----:|-------------|----------|--------|",
    ]
    for r in workflow_rows:
        wf = "[X]" if r["wf_fail"] else "[OK]"
        lines.append(
            f"| {r['ts']} | {r['site']} | {r['rate']:.2f} | {wf} "
            f"| {r['failed_step']} | `{r['cat']}` | {r['reason'][:60]} |"
        )

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {OUT_PATH}")

main()
