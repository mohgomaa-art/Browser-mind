"""
Reads training/subagent_run_*.json and prints a summary table.

Usage:
  python -m training.subagent_dashboard
"""

import sys
import json
from pathlib import Path

def print_dashboard():
    logs = list(Path("training").glob("subagent_run_*.json"))
    if not logs:
        print("No subagent run logs found in training/")
        sys.exit(0)
        
    latest_log = max(logs, key=lambda p: p.stat().st_mtime)
    
    with open(latest_log, "r") as f:
        data = json.load(f)
        
    print("BrowserMind SubAgent Training Dashboard")
    print("========================================")
    print("Round | Pool  | ActionAcc | Elem@3 | Unseen | Best")
    
    rounds = data.get("log", [])
    for row in rounds:
        print(f" {row['round']+1:3d}  | {row['pool_size']:4d}  |   {row['action_acc']:.3f}   |  {row['elem@3']:.3f} | {row['unseen_acc']:.3f}  | {row['best']:.3f}")
        
    print("========================================")
    print(f"Status: COMPLETED |  Best: {data.get('best_metric', 0.0):.3f}  |  Target: 0.700")

if __name__ == "__main__":
    print_dashboard()
