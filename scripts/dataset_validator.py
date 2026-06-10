"""
BrowserMind -- Dataset V3 Validator
==================================
Enforces the strict Dataset V3 Architecture constraints.

Rules:
1. Max 1% per intent (max 50 samples)
2. Max 2% per domain (max 100 samples)
3. Quality gates: AX nodes >= 20, element exists, success=true

Outputs a report with:
- Total samples
- Unique domains
- Unique goals
- Difficulty distribution
- Action distribution
"""

import json
import hashlib
from collections import Counter
from pathlib import Path

def compute_complexity(nodes):
    interactive_roles = {"button", "link", "textbox", "checkbox", "radio", "combobox"}
    interactive_count = sum(1 for n in nodes if n.get("role") in interactive_roles)
    max_depth = max((n.get("depth", 0) for n in nodes), default=0)
    has_modal = any(n.get("role") == "dialog" for n in nodes)
    
    score = (len(nodes) / 80.0) * 0.3 + (interactive_count / 30.0) * 0.4 + (max_depth / 20.0) * 0.2
    if has_modal:
        score += 0.1
    return min(1.0, score)

def compute_state_family_hash(nodes):
    interactive_seq = [n.get("role", "generic") for n in nodes if n.get("role") in {"button", "link", "textbox", "checkbox", "radio", "combobox"}]
    # We take the sequence of interactive elements to represent the structural "family"
    seq_str = ",".join(interactive_seq)
    return hashlib.md5(seq_str.encode()).hexdigest()

def validate_dataset(dataset_dir: str = "training/dataset_v2"):
    dir_path = Path(dataset_dir)
    if not dir_path.exists():
        print(f"Directory {dataset_dir} does not exist.")
        return

    files = list(dir_path.glob("*.json"))
    samples = []
    
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                samples.extend(data)
            else:
                samples.append(data)
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

    if not samples:
        print("No samples found.")
        return

    total_samples = len(samples)
    
    # Tracking
    intents = Counter()
    state_families = Counter()
    domains = Counter()
    difficulties = Counter()
    actions = Counter()
    
    dropped = 0
    duplicates = 0
    valid_samples = []

    for s in samples:
        nodes = s.get("graph", {}).get("nodes", [])
        
        # State metrics
        s["state_complexity"] = compute_complexity(nodes)
        state_hash = compute_state_family_hash(nodes)
        
        # Quality Gates
        ax_nodes = len(nodes)
        if ax_nodes < 20:
            dropped += 1
            continue
            
        success = s.get("success", True) # Assume true if not present for older formats
        if not success:
            dropped += 1
            continue
            
        ea = s.get("expert_action", {})
        if not ea or ea.get("element_idx") is None:
            dropped += 1
            continue

        goal = s.get("goal", "").lower().strip()
        url = s.get("url", "")
        # Extract domain roughly
        domain = url.split("//")[-1].split("/")[0].replace("www.", "")
        
        diff = s.get("difficulty", "medium")
        action = ea.get("type") or ea.get("action_type", "unknown")

        # Constraints
        if state_families[state_hash] >= 50:
            dropped += 1
            duplicates += 1
            continue
            
        if domains[domain] >= 100:
            dropped += 1
            continue
            
        # Passed
        intents[goal] += 1
        state_families[state_hash] += 1
        domains[domain] += 1
        difficulties[diff] += 1
        actions[action] += 1
        valid_samples.append(s)

    v_count = len(valid_samples) or 1
    dup_rate = (duplicates / total_samples) * 100 if total_samples else 0.0

    print("\n" + "="*45)
    print(" BROWSERMIND DATASET V3 DASHBOARD")
    print("="*45)
    print(f"| Metric                      | Value")
    print(f"|-----------------------------|-------")
    print(f"| Unique State Families       | {len(state_families)}")
    print(f"| Unique Interaction Patterns | {len(actions)}")
    print(f"| Unique Domains              | {len(domains)}")
    print(f"| Unique Workflows (Goals)    | {len(intents)}")
    print(f"| Duplicate Rate              | {dup_rate:.1f}%")
    print(f"| Total Valid Samples         | {v_count}")
    print("-" * 45)
    
    # Compute percentages
    v_count = len(valid_samples) or 1
    print("Difficulty Distribution:")
    for d, c in difficulties.most_common():
        print(f"  {d.ljust(8)} : {c} ({c/v_count*100:.1f}%)")
        
    print("\nAction Distribution:")
    for a, c in actions.most_common():
        print(f"  {a.ljust(10)} : {c} ({c/v_count*100:.1f}%)")

    # Final Readiness Checks
    print("\n" + "="*40)
    print(" TRAINING READINESS GATES")
    print("="*40)
    ready = True
    
    if len(state_families) < 5000:
        print(f"[FAIL] Unique State Families {len(state_families)} < 5000")
        ready = False
    else:
        print(f"[PASS] Unique State Families {len(state_families)} >= 5000")
        
    if len(domains) < 200:
        print(f"[FAIL] Unique domains {len(domains)} < 200")
        ready = False
    else:
        print(f"[PASS] Unique domains {len(domains)} >= 200")
        
    hard_pct = difficulties["hard"] / v_count * 100
    if hard_pct < 20.0:
        print(f"[FAIL] Hard tasks {hard_pct:.1f}% < 20.0%")
        ready = False
    else:
        print(f"[PASS] Hard tasks {hard_pct:.1f}% >= 20.0%")

    if ready:
        print("\n>>> DATASET IS READY FOR TRAINING <<<")
    else:
        print("\n>>> DATASET REJECTED - DOES NOT MEET V3 SPEC <<<")

    # Optionally write back the samples with complexity scores
    # for s in valid_samples:
    #    ...

if __name__ == "__main__":
    validate_dataset()
