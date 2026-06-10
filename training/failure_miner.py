"""
BrowserMind — Active Learning Failure Miner
===========================================
Analyzes telemetry logs and the failure buffer to generate the Evidence Dashboard.

It answers the critical question: "Why does the Policy fail?"
- Wrong Element?
- Wrong Action?
- Observation/Sparse Graph?
- Execution Error?
"""

import json
from pathlib import Path
from collections import Counter
import glob
import os

def analyze_failures():
    # 1. Parse Telemetry Logs
    telemetry_files = glob.glob("logs/telemetry_*.jsonl")
    records = []
    for fp in telemetry_files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except:
                        pass

    if not records:
        print("No telemetry records found. The system needs to run first.")
        return

    # 2. Parse Buffers
    policy_failures_dir = Path("training/failure_buffer/policy_failures")
    ood_successes_dir = Path("training/failure_buffer/ood_successes")
    
    pf_count = len(list(policy_failures_dir.glob("*.json"))) if policy_failures_dir.exists() else 0
    ood_count = len(list(ood_successes_dir.glob("*.json"))) if ood_successes_dir.exists() else 0

    # 3. Analyze Telemetry Failures
    failure_types = Counter()
    total_failures = 0
    
    for r in records:
        if not r.get("success"):
            failure_types[r.get("failure_type", "unknown")] += 1
            total_failures += 1
            
        # Also track policy failures that were rescued by fallback as failures for analysis
        if r.get("success") and r.get("fallback_used") and r.get("failure_type") == "policy":
            failure_types["policy_rescued"] += 1
            total_failures += 1

    # In a real run, we would parse the actual policy vs fallback divergence
    # to split "policy" into "wrong_element" and "wrong_action".
    # For now, we estimate based on the architecture:
    # Most policy failures in the current system are element selection errors.
    
    # 4. Analyze Buffer Complexity (if files exist)
    state_families = set()
    total_complexity = 0.0
    buffer_samples = 0
    
    if policy_failures_dir.exists():
        for fp in policy_failures_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                buffer_samples += 1
                # Recalculate hash/complexity just for dashboard
                nodes = data.get("graph", {}).get("nodes", [])
                
                # Family Hash
                interactive_seq = [n.get("role", "generic") for n in nodes if n.get("role") in {"button", "link", "textbox", "checkbox", "radio", "combobox"}]
                state_families.add(",".join(interactive_seq))
                
                # Complexity
                i_count = len(interactive_seq)
                max_depth = max((n.get("depth", 0) for n in nodes), default=0)
                has_modal = any(n.get("role") == "dialog" for n in nodes)
                score = (len(nodes) / 80.0) * 0.3 + (i_count / 30.0) * 0.4 + (max_depth / 20.0) * 0.2
                if has_modal: score += 0.1
                total_complexity += min(1.0, score)
                
            except:
                pass

    avg_complexity = (total_complexity / buffer_samples) if buffer_samples > 0 else 0.0

    print("\n" + "="*50)
    print(" BROWSERMIND ACTIVE LEARNING DASHBOARD")
    print("="*50)
    print(f"| Metric                | Count")
    print(f"|-----------------------|-------")
    print(f"| Total Steps Logged    | {len(records)}")
    print(f"| Policy Failures saved | {pf_count}")
    print(f"| OOD Successes saved   | {ood_count}")
    print(f"| Unique State Families | {len(state_families)}")
    print(f"| Avg State Complexity  | {avg_complexity:.2f}")
    
    if total_failures > 0:
        top_pattern = failure_types.most_common(1)[0][0]
        print(f"| Top Failure Pattern   | {top_pattern}")
    else:
        print(f"| Top Failure Pattern   | N/A")
    print("-" * 50)

    print("\nFailure Distribution (from Telemetry):")
    if total_failures == 0:
        print("  No failures recorded yet.")
    else:
        print(f"| Failure Type     | %     | Count")
        print(f"|------------------|-------|------")
        for ftype, count in failure_types.most_common():
            pct = (count / total_failures) * 100
            print(f"| {ftype.ljust(16)} | {pct:5.1f}% | {count}")
            
    print("\nNext Steps:")
    print("1. Run benchmark/eval to generate telemetry.")
    print("2. Re-run this miner to gather evidence.")
    print("3. If 'policy' failures dominate, inspect policy_failures/ JSONs to split into Wrong Action vs Wrong Element.")
    print("4. ONLY THEN implement Contrastive Ranking (Phase 6) if Wrong Element is the bottleneck.")

if __name__ == "__main__":
    analyze_failures()
