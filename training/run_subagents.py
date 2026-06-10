"""
Usage:
  python -m training.run_subagents
  python -m training.run_subagents --rounds 10
  python -m training.run_subagents --resume checkpoints/subagent/round_005_acc0.71.pt
  python -m training.run_subagents --headless false --rounds 3
"""

import sys
import argparse
import asyncio
import json
import time
from pathlib import Path
import torch

# Must insert project root if run as module from script dir directly,
# though `-m training.run_subagents` from root handles it.
sys.path.insert(0, str(Path(__file__).parent.parent))

from model.agent_policy import AgentPolicy
from training.coordinator import TrainingCoordinator

async def main():
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = argparse.ArgumentParser()

    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--resume", type=str, default="")
    parser.add_argument("--headless", type=str, default="true")
    parser.add_argument("--parallel", type=int, default=2, help="Parallel browsers per agent")
    parser.add_argument("--sessions", type=int, default=10, help="Sessions per agent per round")
    args = parser.parse_args()

    headless = args.headless.lower() == "true"
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Initializing BrowserMind TrainingCoordinator on {device}")
    
    policy = AgentPolicy().to(device)
    if args.resume:
        path = Path(args.resume)
        if path.exists():
            policy.load_weights(str(path))
            print(f"Loaded weights from {path}")
        else:
            print(f"Warning: Checkpoint {path} not found.")

    # 3e-4 LR and weight_decay=1e-4 as spec
    optimizer = torch.optim.AdamW(policy.parameters(), lr=3e-4, weight_decay=1e-4)
    
    coordinator = TrainingCoordinator(
        policy=policy,
        optimizer=optimizer,
        device=device,
        n_rounds=args.rounds,
        sessions_per_agent_per_round=args.sessions,
        n_parallel_per_agent=args.parallel,
    )
    
    start_t = time.time()
    
    try:
        result = await coordinator.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving log...")
        result = {"rounds": len(coordinator.round_log), "best_metric": coordinator.best_metric, "log": coordinator.round_log}
        
    duration = time.time() - start_t
    
    # Save log
    ts = int(time.time())
    log_name = f"training/subagent_run_{ts}.json"
    with open(log_name, "w") as f:
        json.dump({
            "duration": duration,
            "rounds": result["rounds"],
            "best_metric": result["best_metric"],
            "log": result["log"]
        }, f, indent=2)
        
    print(f"\nTraining completed in {duration:.1f}s. Log saved to {log_name}")

if __name__ == "__main__":
    asyncio.run(main())
