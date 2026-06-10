"""
BrowserMind -- Dataset Cleanup and Rebalancing
=============================================
Reads from training/sessions/phase0/
Deduplicates samples.
Validates samples.
Caps specific actions (e.g., scroll) to prevent distribution bias (Phase 5).
Writes cleaned, balanced dataset to training/dataset_v2/
"""

import json
import collections
import hashlib
import random
from pathlib import Path


def deduplicate_and_balance():
    input_dir = Path("training/sessions/phase0")
    output_dir = Path("training/dataset_v2")
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob("*.json"))
    if not files:
        print(f"No json files found in {input_dir}")
        return

    seen_keys = set()
    raw_samples = []

    # 1. Load and deduplicate
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            samples = data if isinstance(data, list) else data.get("samples", [data])
            for s in samples:
                ea = s.get("expert_action", {})
                if not ea:
                    continue
                atype = ea.get("type") or ea.get("action_type", "unknown")
                url = s.get("url", "")
                goal = s.get("goal", "")
                eidx = ea.get("element_idx")
                
                # Dedup key
                key = f"{url}|{goal}|{atype}|{eidx}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    # Annotate original action type for filtering
                    s["_action_type"] = atype
                    raw_samples.append(s)
        except Exception as e:
            print(f"Error reading {fp}: {e}")

    print(f"Loaded {len(raw_samples)} unique samples after deduplication.")

    # 2. Action Rebalancing (Phase 5)
    # Target: no action should exceed 20% of the total dataset if it's overrepresented.
    # We'll specifically cap 'scroll', as it's the most common and easiest action.
    
    # First pass: count action distribution
    action_counts = collections.Counter(s["_action_type"] for s in raw_samples)
    print(f"Pre-balance distribution: {dict(action_counts)}")

    # We want to cap scroll at roughly 20% of the total *after* capping.
    # Let Non-Scroll = N. Scroll = S.
    # We want S / (N + S) <= 0.20
    # S <= 0.25 * N
    
    non_scroll = sum(c for a, c in action_counts.items() if a != "scroll")
    max_scroll = int(non_scroll * 0.25)
    
    if action_counts["scroll"] > max_scroll:
        print(f"Capping scroll from {action_counts['scroll']} down to {max_scroll}")
    else:
        max_scroll = action_counts["scroll"]

    # Build final dataset
    random.seed(42)
    scroll_samples = [s for s in raw_samples if s["_action_type"] == "scroll"]
    other_samples = [s for s in raw_samples if s["_action_type"] != "scroll"]
    
    random.shuffle(scroll_samples)
    final_samples = other_samples + scroll_samples[:max_scroll]
    random.shuffle(final_samples)

    # 3. Write out to v2
    # We chunk them into files of 100 samples each to keep sizes reasonable
    chunk_size = 100
    file_count = 0
    
    for i in range(0, len(final_samples), chunk_size):
        chunk = final_samples[i:i + chunk_size]
        # remove internal tracking keys
        for s in chunk:
            s.pop("_action_type", None)
            
        file_count += 1
        out_path = output_dir / f"session_v2_{file_count:04d}.json"
        out_path.write_text(json.dumps(chunk, indent=2, ensure_ascii=False), encoding="utf-8")

    final_counts = collections.Counter(s.get("expert_action", {}).get("type") or s.get("expert_action", {}).get("action_type") for s in final_samples)
    
    print("\n--- Summary ---")
    print(f"Total samples written: {len(final_samples)}")
    print(f"Files written: {file_count}")
    print(f"Final Action Distribution: {dict(final_counts)}")


if __name__ == "__main__":
    deduplicate_and_balance()
