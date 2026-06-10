"""Extract TARGET_CHANGED steps from replay experiment JSON files."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPORTS = Path("reports/replay_experiments")


def main() -> None:
    step_ledger: Counter = Counter()
    tc_cases: list[dict] = []
    run_files: set[str] = set()

    for path in sorted(REPORTS.rglob("*.json")):
        if path.name == "summary.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "workflow_id" not in data or "site" not in data:
            continue
        run_files.add(str(path))
        for step in data.get("step_outcomes") or []:
            step_ledger[step["outcome"]] += 1
            if step["outcome"] == "TARGET_CHANGED":
                tc_cases.append(
                    {
                        "site": data.get("site"),
                        "timestamp": (data.get("timestamp") or "")[:19],
                        "template_name": data.get("template_name"),
                        "demonstration_id": data.get("demonstration_id"),
                        "seq": step["seq"],
                        "action_type": step["action_type"],
                        "recorded_role": step["role"],
                        "recorded_name": step["name"],
                        "source_file": str(path),
                    }
                )

    print(f"RUNS: {len(run_files)}")
    print(f"TOTAL STEPS: {sum(step_ledger.values())}")
    print(f"STEP LEDGER: {dict(step_ledger)}")
    print(f"TARGET_CHANGED CASES: {len(tc_cases)}")
    for case in tc_cases:
        print(json.dumps(case, indent=2))


if __name__ == "__main__":
    main()
