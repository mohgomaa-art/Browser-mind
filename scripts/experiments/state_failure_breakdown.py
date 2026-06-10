import json
import glob
from collections import Counter
from urllib.parse import urlparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

def generate_state_failure_breakdown():
    base_dir = ROOT_DIR / "reports" / "reality_test"
    
    # Find most recent test run directory
    subdirs = sorted([d for d in base_dir.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True)
    if not subdirs:
        print("No reality test reports found.")
        return
        
    latest_dir = subdirs[0]
    print(f"Analyzing State Failure Taxonomy in: {latest_dir.name}")
    
    files = glob.glob(str(latest_dir / "*" / "*.json"))
    
    taxonomy_list = []
    
    for f_path in files:
        if "summary.json" in f_path:
            continue
            
        with open(f_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
            
        verif = report.get("verification_report")
        if not verif or verif.get("state_match", False):
            continue
            
        # Extract rich details
        terminal_url = "unknown"
        expected_url = "unknown"
        
        rules = verif.get("rule_results", [])
        for r in rules:
            if r.get("rule", {}).get("type") == "url_contains":
                terminal_url = r.get("actual_value") or "unknown"
                expected_url = r.get("rule", {}).get("value") or "unknown"
                break
                
        state_inference = report.get("state_inference", {})
        terminal_state = state_inference.get("inferred_state", "unknown")
        expected_state = state_inference.get("expected_state", "unknown")
        
        last_step = report.get("resolved_steps", 0)
        total_steps = report.get("total_steps", 0)
        
        failure_reasons = []
        for r in rules:
            if not r.get("passed", True):
                rule_type = r.get("rule", {}).get("type")
                rule_val = r.get("rule", {}).get("value")
                failure_reasons.append(f"{rule_type} failed (expected: {rule_val})")
                
        taxonomy_list.append({
            "run_file": Path(f_path).name,
            "failure_location": terminal_url,
            "failure_reason": " | ".join(failure_reasons),
            "observed_url": terminal_url,
            "expected_url_contains": expected_url,
            "last_successful_step": f"{last_step} / {total_steps}",
            "terminal_state": terminal_state,
            "expected_state": expected_state
        })

    if not taxonomy_list:
        print("No state failures found in the report.")
        return
        
    # Group by terminal state
    state_groups = Counter()
    for item in taxonomy_list:
        state_groups[item["terminal_state"]] += 1
        
    breakdown = {
        "total_state_failures": len(taxonomy_list),
        "unique_terminal_states": dict(state_groups),
        "taxonomy": taxonomy_list
    }
    
    out_file = latest_dir / "state_failure_taxonomy.json"
    out_file.write_text(json.dumps(breakdown, indent=2), encoding="utf-8")
    
    print(json.dumps(breakdown, indent=2))
    print(f"\nSaved taxonomy to {out_file}")

if __name__ == "__main__":
    generate_state_failure_breakdown()
