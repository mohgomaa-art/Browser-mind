"""
BrowserMind - Deep Training Orchestrator (time-boxed)
=====================================================
Runs repeated rounds of:
  1) super-complex data collection
  2) BC training resume
  3) optional offline evaluation

Primary use:
  python run_deep_training.py --hours 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import torch

from collect_complex_goldens import collect_complex_goldens


@dataclass
class RoundRecord:
    round_idx: int
    started_at_utc: str
    ended_at_utc: str
    duration_sec: float
    total_sessions: int
    ckpt_epoch_before: int
    ckpt_epoch_after: int
    train_exit_code: int
    eval_action_acc: Optional[float]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_json_files(data_dir: Path) -> int:
    return len(list(data_dir.glob("*.json")))


def _read_ckpt_epoch(ckpt_path: Path) -> int:
    if not ckpt_path.exists():
        return 0
    try:
        ckpt = torch.load(ckpt_path, map_location="cpu")
        return int(ckpt.get("epoch", 0))
    except Exception:
        return 0


def _run_train_bc(
    python_exe: str,
    data_dir: Path,
    ckpt_path: Path,
    epochs_target: int,
    batch_size: int,
    patience: int,
) -> int:
    cmd = [
        python_exe,
        "-u",
        "train_bc.py",
        "--data",
        str(data_dir),
        "--ckpt",
        str(ckpt_path),
        "--epochs",
        str(epochs_target),
        "--batch-size",
        str(batch_size),
        "--patience",
        str(patience),
    ]
    if ckpt_path.exists():
        cmd.append("--resume")

    print(f"[train] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def _run_offline_eval(python_exe: str, ckpt_path: Path, data_dir: Path) -> Optional[float]:
    cmd = [
        python_exe,
        "-u",
        "evaluate.py",
        "--ckpt",
        str(ckpt_path),
        "--data",
        str(data_dir),
    ]
    print(f"[eval ] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Echo output for operator visibility.
    if proc.stdout:
        print(proc.stdout, end="", flush=True)
    if proc.stderr:
        print(proc.stderr, end="", flush=True)

    if proc.returncode != 0:
        return None

    # Parse line like: "Offline | Samples: 29 | Action Acc: 0.6552"
    for line in proc.stdout.splitlines():
        if "Action Acc:" in line:
            try:
                tail = line.split("Action Acc:", 1)[1].strip()
                return float(tail)
            except Exception:
                return None
    return None


def _write_status(status_file: Path, payload: dict):
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run time-boxed deep training")
    p.add_argument("--hours", type=float, default=10.0)
    p.add_argument("--collect-per-round", type=int, default=20)
    p.add_argument("--min-difficulty", type=int, default=2)
    p.add_argument("--mode", choices=["all", "super-complex"], default="super-complex")
    p.add_argument("--data-dir", default="training/super_complex_sessions/deep_10h")
    p.add_argument("--ckpt", default="checkpoints/browsermind_super_complex_10h.pt")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--patience", type=int, default=4)
    p.add_argument("--epoch-step", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout-sec", type=float, default=120.0)
    p.add_argument("--headless", type=lambda x: x.lower() != "false", default=True)
    p.add_argument("--eval-every", type=int, default=1)
    p.add_argument("--status-file", default="logs/deep_training_status.json")
    return p.parse_args()


def main():
    args = parse_args()

    python_exe = sys.executable
    data_dir = Path(args.data_dir)
    ckpt_path = Path(args.ckpt)
    status_file = Path(args.status_file)

    data_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    start_ts = time.time()
    deadline_ts = start_ts + args.hours * 3600.0

    print("=" * 72, flush=True)
    print("BrowserMind Deep Training Started", flush=True)
    print(f"hours={args.hours}  mode={args.mode}  data_dir={data_dir}", flush=True)
    print(f"ckpt={ckpt_path}", flush=True)
    print("=" * 72, flush=True)

    rounds: list[RoundRecord] = []
    round_idx = 0

    while time.time() < deadline_ts:
        round_idx += 1
        round_start = time.time()
        started_at = _utc_now()

        remaining_hr = max(0.0, (deadline_ts - round_start) / 3600.0)
        print(
            f"\n[round {round_idx}] remaining_hours={remaining_hr:.2f} "
            f"collect={args.collect_per_round}",
            flush=True,
        )

        asyncio.run(
            collect_complex_goldens(
                num_tasks=args.collect_per_round,
                mode=args.mode,
                min_difficulty=args.min_difficulty,
                save_dir=data_dir,
                headless=args.headless,
                seed=args.seed + round_idx,
                timeout_sec=args.timeout_sec,
            )
        )

        total_sessions = _count_json_files(data_dir)
        ckpt_epoch_before = _read_ckpt_epoch(ckpt_path)
        target_epoch = max(ckpt_epoch_before + args.epoch_step, args.epoch_step)

        train_exit = _run_train_bc(
            python_exe=python_exe,
            data_dir=data_dir,
            ckpt_path=ckpt_path,
            epochs_target=target_epoch,
            batch_size=args.batch_size,
            patience=args.patience,
        )

        ckpt_epoch_after = _read_ckpt_epoch(ckpt_path)

        eval_acc = None
        if train_exit == 0 and (round_idx % max(1, args.eval_every) == 0):
            eval_acc = _run_offline_eval(
                python_exe=python_exe,
                ckpt_path=ckpt_path,
                data_dir=data_dir,
            )

        round_end = time.time()
        ended_at = _utc_now()

        record = RoundRecord(
            round_idx=round_idx,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            duration_sec=round_end - round_start,
            total_sessions=total_sessions,
            ckpt_epoch_before=ckpt_epoch_before,
            ckpt_epoch_after=ckpt_epoch_after,
            train_exit_code=train_exit,
            eval_action_acc=eval_acc,
        )
        rounds.append(record)

        status_payload = {
            "started_at_utc": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "deadline_utc": datetime.fromtimestamp(deadline_ts, tz=timezone.utc).isoformat(),
            "now_utc": _utc_now(),
            "hours": args.hours,
            "mode": args.mode,
            "data_dir": str(data_dir),
            "checkpoint": str(ckpt_path),
            "rounds_completed": len(rounds),
            "latest": asdict(record),
            "history": [asdict(r) for r in rounds],
        }
        _write_status(status_file, status_payload)

        print(
            f"[round {round_idx} done] sessions={total_sessions} "
            f"epoch:{ckpt_epoch_before}->{ckpt_epoch_after} "
            f"train_exit={train_exit} eval_acc={eval_acc}",
            flush=True,
        )

        if train_exit != 0:
            print("[warn] train step failed; continuing to next round", flush=True)

    total_h = (time.time() - start_ts) / 3600.0
    print("\n" + "=" * 72, flush=True)
    print(f"Deep training finished. rounds={len(rounds)} elapsed_hours={total_h:.2f}", flush=True)
    print(f"Status file: {status_file}", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    main()
