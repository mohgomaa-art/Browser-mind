"""
BrowserMind — Autoscale Improvement Loop
========================================
Orchestrates autonomous "Test & Train" cycles.
Automatically clears orphan browsers and runs benchmarks.
"""

import os
import subprocess
import time
import sys
from pathlib import Path

def cleanup():
    """Purge orphan browser and python processes."""
    print("[AUTOSCALE] Cleaning environment...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome-headless-shell.exe", "/T"], capture_output=True)
        # We don't kill python.exe here because it would kill THIS script.
    except:
        pass

def run_train(episodes=5, headful=False):
    """Run Phase 3 PPO training batch."""
    print(f"\n[AUTOSCALE] Starting Training Cycle ({episodes} episodes)...")
    cmd = [
        "python", "-u", "train_ppo.py",
        "--episodes", str(episodes),
        "--checkpoint", "checkpoints/best.pt"
    ]
    if headful:
        cmd.append("--headful")
        
    with open("scaling.log", "a") as f:
        f.write(f"\n--- Training Start: {time.ctime()} ---\n")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(f"  [TRAIN] {line.strip()}")
            f.write(line)
        process.wait()

def run_test(headful=False):
    """Run Phase 4 Short Evaluation and return success rate."""
    print("\n[AUTOSCALE] Starting Testing Cycle (Short Bench)...")
    cmd = [
        "python", "-u", "evaluate.py",
        "--ckpt", "checkpoints/best.pt",
        "--live", "--short"
    ]
    
    success_rate = 0.0
    with open("scaling.log", "a") as f:
        f.write(f"\n--- Testing Start: {time.ctime()} ---\n")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(f"  [TEST]  {line.strip()}")
            f.write(line)
            # Parse success rate from: "Live    | Tasks: 5 | Success: 0.8000 | Avg Steps: 12.0"
            if "Success:" in line:
                try:
                    success_rate = float(line.split("Success:")[1].split("|")[0].strip())
                except:
                    pass
        process.wait()
    return success_rate

def main():
    import argparse
    import shutil
    parser = argparse.ArgumentParser()
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()
    
    cycles = 5
    best_rate = -1.0
    
    print(f"============================================================")
    print(f"  BrowserMind Autoscale Loop Initialized")
    if args.headful:
        print(f"  [VISUAL] Headful mode active. Watching the agent...")
    print(f"============================================================")
    
    for c in range(cycles):
        print(f"\n>>> CYCLE {c+1}/{cycles} <<<")
        cleanup()
        
        # 1. Train
        try:
            run_train(episodes=10, headful=args.headful)
        except Exception as e:
            print(f"[!] Training error: {e}")
            
        cleanup()
        
        # 2. Test
        try:
            rate = run_test(headful=args.headful)
            print(f"[AUTOSCALE] Cycle {c+1} Success Rate: {rate:.4f}")
            
            # GREEDY CHECKPOINTING
            if rate >= best_rate:
                best_rate = rate
                print(f"[AUTOSCALE] New BEST model found ({rate:.4f}). Saving to checkpoints/best_ever.pt")
                if Path("checkpoints/best.pt").exists():
                    shutil.copy("checkpoints/best.pt", "checkpoints/best_ever.pt")
        except Exception as e:
            print(f"[!] Testing error: {e}")

        print(f"\n>>> CYCLE {c+1} COMPLETE (Best Ever: {best_rate:.4f}) <<<")
        time.sleep(5)

            
        print(f"\n>>> CYCLE {c+1} COMPLETE <<<")
        time.sleep(5)

if __name__ == "__main__":
    main()
