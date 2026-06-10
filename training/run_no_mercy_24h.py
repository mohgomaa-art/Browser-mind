"""
BrowserMind 24h no-mercy trainer.

Runs continuous cycles for a target duration:
1) Real-world social collection across broad websites (logged-in Chrome profile)
2) Immediate BC retraining on collected data with checkpoint resume

Usage:
  python training/run_no_mercy_24h.py
  python training/run_no_mercy_24h.py --hours 24 --round-train-epochs 2 --max-tasks 0
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log(msg: str, fp: Path) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with fp.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _run(cmd: list[str], log_file: Path, env: dict[str, str] | None = None) -> int:
    _log("RUN: " + " ".join(cmd), log_file)
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(proc.stdout)
    if proc.stderr:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(proc.stderr)
    _log(f"EXIT: {proc.returncode}", log_file)
    return int(proc.returncode)


def _read_epoch(ckpt: Path) -> int:
    if not ckpt.exists():
        return 0
    try:
        data = torch.load(str(ckpt), map_location="cpu")
        return int(data.get("epoch", 0) or 0)
    except Exception:
        return 0


def main() -> None:
    p = argparse.ArgumentParser(description="24h no-mercy social collector + trainer")
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--max-tasks", type=int, default=0, help="0 = full all-websites task set")
    p.add_argument("--seed", type=int, default=42, help="Base shuffle seed for per-round task diversity")
    p.add_argument("--include-sensitive", action="store_true", help="Include sensitive high-traffic taxonomy layer")
    p.add_argument("--round-train-epochs", type=int, default=2, help="Additional epochs each cycle")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--patience", type=int, default=2)
    p.add_argument("--target-action-acc", type=float, default=0.99)
    p.add_argument("--ckpt", default="checkpoints/browsermind_no_mercy_24h.pt")
    args = p.parse_args()

    log_file = LOG_DIR / f"no_mercy_24h_{int(time.time())}.log"
    end_time = datetime.now() + timedelta(hours=float(args.hours))

    env = os.environ.copy()
    env["BROWSERMIND_STRICT_PRIVACY"] = "1"

    _log("=== BrowserMind 24h No-Mercy Trainer ===", log_file)
    _log(
        f"hours={args.hours} max_tasks={args.max_tasks} round_train_epochs={args.round_train_epochs} seed={args.seed}",
        log_file,
    )
    _log(f"ckpt={args.ckpt}", log_file)
    _log(f"end_time={end_time}", log_file)

    round_idx = 0
    py = sys.executable
    ckpt_path = ROOT / args.ckpt

    while datetime.now() < end_time:
        round_idx += 1
        _log(f"--- ROUND {round_idx} START ---", log_file)

        round_seed = int(args.seed) + round_idx
        collect_cmd = [
            py,
            "training/expert_marathon.py",
            "--all-websites",
            "--shuffle-tasks",
            "--seed",
            str(round_seed),
        ]
        if args.include_sensitive:
            collect_cmd.append("--include-sensitive")
        if int(args.max_tasks) > 0:
            collect_cmd += ["--max-tasks", str(int(args.max_tasks))]

        rc_collect = _run(collect_cmd, log_file, env=env)
        if rc_collect != 0:
            _log(f"[WARN] collect failed round={round_idx} code={rc_collect}", log_file)

        current_epoch = _read_epoch(ckpt_path)
        target_epochs = max(current_epoch + int(args.round_train_epochs), int(args.round_train_epochs))

        train_cmd = [
            py,
            "train_bc.py",
            "--data", "training/massive_sessions",
            "--ckpt", args.ckpt,
            "--resume",
            "--epochs", str(target_epochs),
            "--batch-size", str(int(args.batch_size)),
            "--lr", str(float(args.lr)),
            "--patience", str(int(args.patience)),
            "--target-action-acc", str(float(args.target_action_acc)),
            "--no-augment",
        ]

        rc_train = _run(train_cmd, log_file, env=env)
        if rc_train != 0:
            _log(f"[WARN] train failed round={round_idx} code={rc_train}", log_file)

        _log(f"--- ROUND {round_idx} END ---", log_file)

    _log("=== 24h window complete ===", log_file)


if __name__ == "__main__":
    main()
