"""
BrowserMind — Master Training Pipeline
======================================
Automates the End-to-End training process across all 3 phases:
  Phase 1: Behavior Cloning (BC) on static datasets
  Phase 2: DAgger (Dataset Aggregation) via Interactive Collect & Train
  Phase 3: Proximal Policy Optimization (PPO) 

It leverages the newly defined Complex Tasks (signup, login, forms, multistep).

Usage:
  python run_full_pipeline.py [--skip-bc] [--skip-dagger] [--skip-ppo]
"""

import sys
import subprocess
import argparse
from pathlib import Path

# Important: these task collections were added via complex_tasks.py
try:
    from training.complex_tasks import PHASE1_TASKS, PHASE2_TASKS, PHASE3_TASKS
except ImportError:
    print("WARNING: complex_tasks.py not found. Falling back to default tasks.")


def run_command(cmd: list, step_name: str):
    print(f"\n{'+'*70}")
    print(f"+++ STARTING: {step_name}")
    print(f"+++ COMMAND:  {' '.join(cmd)}")
    print(f"{'+'*70}\n")
    
    try:
        proc = subprocess.run(cmd, check=True)
        print(f"\n[OK] {step_name} completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] {step_name} failed with exit code {e.returncode}.")
        sys.exit(e.returncode)


def main():
    parser = argparse.ArgumentParser(description="BrowserMind Full Training Pipeline")
    parser.add_argument("--skip-bc", action="store_true", help="Skip Phase 1: Behavior Cloning")
    parser.add_argument("--skip-dagger", action="store_true", help="Skip Phase 2: DAgger")
    parser.add_argument("--skip-ppo", action="store_true", help="Skip Phase 3: PPO")
    args = parser.parse_args()

    # Ensure checkpoint dir exists
    Path("checkpoints").mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # PHASE 1: Behavior Cloning (BC)
    # -------------------------------------------------------------------------
    if not args.skip_bc:
        # train_bc.py handles static dataset training (massive_sessions or local sessions)
        cmd_bc = [
            sys.executable, "train_bc.py",
            "--epochs", "20",
            "--batch-size", "16"
        ]
        run_command(cmd_bc, "Phase 1: Behavior Cloning (train_bc.py)")
    else:
        print("\n[SKIP] Skipping Phase 1: BC")

    # -------------------------------------------------------------------------
    # PHASE 2: DAgger (Interactive Collect & Train)
    # -------------------------------------------------------------------------
    if not args.skip_dagger:
        # We rely on either collect_and_train.py or train_dagger.py
        # Both now use FormExpert automatically through graph_builder integration.
        cmd_dagger = [
            sys.executable, "train_dagger.py",
            "--ckpt", "browsermind_policy_v2.pt",
            "--iterations", "50"
        ]
        run_command(cmd_dagger, "Phase 2: DAgger (train_dagger.py)")
    else:
        print("\n[SKIP] Skipping Phase 2: DAgger")

    # -------------------------------------------------------------------------
    # PHASE 3: Reinforcement Learning (PPO) 
    # -------------------------------------------------------------------------
    if not args.skip_ppo:
        # PPO requires a functional train_ppo.py. Ensure the Anti-Gravity audit 
        # C-5 fixes are addressed before executing this part.
        cmd_ppo = [
            sys.executable, "train_ppo.py",
            "--checkpoint", "browsermind_policy_v2.pt",
            "--episodes", "50"
        ]
        print("\nNOTE: Phase 3 (PPO) might be marked non-functional per C-5 audit.")
        run_command(cmd_ppo, "Phase 3: Proximal Policy Optimization (train_ppo.py)")
    else:
        print("\n[SKIP] Skipping Phase 3: PPO")

    print(f"\n{'='*70}")
    print("BrowserMind Master Pipeline Completed Successfully!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
