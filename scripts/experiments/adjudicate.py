import os
import json
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "reports" / "reality_test"

def adjudicate_reports():
    reports = []
    for run_dir in sorted(REPORTS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        for f in run_dir.glob("*.json"):
            if f.name == "summary.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "verification_report" in data:
                    rep = data["verification_report"]
                    if rep.get("human_result") is None:
                        reports.append((f, data))
            except Exception:
                pass

    if not reports:
        print("No reports pending adjudication.")
        return

    print(f"Found {len(reports)} reports pending adjudication.")
    for f, data in reports:
        rep = data["verification_report"]
        print("-" * 50)
        print(f"Workflow: {rep.get('workflow')}")
        print(f"Verifier Result: {rep.get('verifier_result')}")
        for rule in rep.get('rule_results', []):
            print(f"  - {rule.get('rule').get('type')}: {rule.get('actual_value')} -> {rule.get('passed')}")
        
        while True:
            ans = input("Did the workflow achieve the goal? (y/n/skip): ").strip().lower()
            if ans in ('y', 'n', 'skip'):
                break
        
        if ans == 'skip':
            continue
            
        rep["human_result"] = (ans == 'y')
        
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Saved.")

if __name__ == "__main__":
    adjudicate_reports()
