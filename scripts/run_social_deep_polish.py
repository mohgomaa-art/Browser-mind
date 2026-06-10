"""
BrowserMind - Social Deep Polish Orchestrator (time-boxed)
===========================================================
Runs repeated rounds of:
  1) social-only collection with broad action coverage
  2) strict real-social curation + BC resume training
  3) optional offline evaluation

Primary use:
  python scripts/run_social_deep_polish.py --hours 10
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import torch


@dataclass
class RoundRecord:
    round_idx: int
    started_at_utc: str
    ended_at_utc: str
    duration_sec: float
    collect_exit_code: int
    train_exit_code: int
    eval_exit_code: int
    eval_action_acc: Optional[float]
    ckpt_epoch_before: int
    ckpt_epoch_after: int
    curated_files: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_ckpt_epoch(ckpt_path: Path) -> int:
    if not ckpt_path.exists():
        return 0
    try:
        ckpt = torch.load(ckpt_path, map_location="cpu")
        return int(ckpt.get("epoch", 0))
    except Exception:
        return 0


def _count_json_files(data_dir: Path) -> int:
    if not data_dir.exists():
        return 0
    return len(list(data_dir.glob("*.json")))


def _write_status(status_file: Path, payload: dict) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run(cmd: list[str], label: str) -> int:
    print(f"[{label}] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def _run_eval(python_exe: str, ckpt_path: Path, data_dir: Path) -> tuple[int, Optional[float]]:
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
    if proc.stdout:
        print(proc.stdout, end="", flush=True)
    if proc.stderr:
        print(proc.stderr, end="", flush=True)

    action_acc: Optional[float] = None
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if "Action Acc:" in line:
                try:
                    action_acc = float(line.split("Action Acc:", 1)[1].strip())
                except Exception:
                    action_acc = None
                break

    return int(proc.returncode), action_acc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run time-boxed social deep polish training")
    p.add_argument("--hours", type=float, default=10.0)
    p.add_argument("--parallel", type=int, default=6)
    p.add_argument("--tasks-per-round", type=int, default=24)
    p.add_argument("--epoch-step", type=int, default=4)
    p.add_argument("--batch-size", type=int, default=24)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--target-action-acc", type=float, default=0.92)
    p.add_argument("--eval-every", type=int, default=1)

    p.add_argument("--ckpt", default="checkpoints/browsermind_social_real_only.pt")
    p.add_argument("--curated-output", default="training/social_real_only")
    p.add_argument("--status-file", default="logs/social_deep_polish_status.json")
    p.add_argument("--collect-inline-train", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    python_exe = sys.executable

    ckpt_path = Path(args.ckpt)
    curated_output = Path(args.curated_output)
    status_file = Path(args.status_file)

    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    curated_output.mkdir(parents=True, exist_ok=True)

    start_ts = time.time()
    deadline_ts = start_ts + args.hours * 3600.0

    print("=" * 72, flush=True)
    print("BrowserMind Social Deep Polish Started", flush=True)
    print(f"hours={args.hours} parallel={args.parallel} tasks_per_round={args.tasks_per_round}", flush=True)
    print(f"ckpt={ckpt_path}", flush=True)
    print(f"curated_output={curated_output}", flush=True)
    print("=" * 72, flush=True)

    rounds: list[RoundRecord] = []
    round_idx = 0

    while time.time() < deadline_ts:
        round_idx += 1
        started_at = _utc_now()
        round_start = time.time()
        remaining_hr = max(0.0, (deadline_ts - round_start) / 3600.0)

        print(
            f"\n[round {round_idx}] remaining_hours={remaining_hr:.2f} "
            f"collect_parallel={args.parallel} tasks_per_round={args.tasks_per_round}",
            flush=True,
        )

        collect_cmd = [
            python_exe,
            "-u",
            "collect_social.py",
            "--parallel",
            str(args.parallel),
            "--rounds",
            "1",
            "--tasks-per-round",
            str(args.tasks_per_round),
        ]
        if args.collect_inline_train:
            collect_cmd.append("--inline-train")
        collect_exit = _run(collect_cmd, "collect")

        ckpt_epoch_before = _read_ckpt_epoch(ckpt_path)
        target_epoch = max(ckpt_epoch_before + int(args.epoch_step), int(args.epoch_step))

        train_cmd = [
            python_exe,
            "-u",
            "scripts/train_social_real_only.py",
            "--sources",
            "training/social_sessions",
            "training/massive_sessions",
            "training/spec_sessions",
            "training/sessions",
            "--output",
            str(curated_output),
            "--ckpt",
            str(ckpt_path),
            "--resume",
            "--epochs",
            str(target_epoch),
            "--batch-size",
            str(args.batch_size),
            "--lr",
            str(args.lr),
            "--val-ratio",
            str(args.val_ratio),
            "--seed",
            str(args.seed + round_idx),
            "--target-action-acc",
            str(args.target_action_acc),
        ]
        train_exit = _run(train_cmd, "train")

        ckpt_epoch_after = _read_ckpt_epoch(ckpt_path)
        curated_files = _count_json_files(curated_output)

        eval_exit = -1
        eval_acc: Optional[float] = None
        if train_exit == 0 and round_idx % max(1, int(args.eval_every)) == 0:
            eval_exit, eval_acc = _run_eval(
                python_exe=python_exe,
                ckpt_path=ckpt_path,
                data_dir=curated_output,
            )

        ended_at = _utc_now()
        duration_sec = time.time() - round_start

        record = RoundRecord(
            round_idx=round_idx,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            duration_sec=duration_sec,
            collect_exit_code=collect_exit,
            train_exit_code=train_exit,
            eval_exit_code=eval_exit,
            eval_action_acc=eval_acc,
            ckpt_epoch_before=ckpt_epoch_before,
            ckpt_epoch_after=ckpt_epoch_after,
            curated_files=curated_files,
        )
        rounds.append(record)

        status_payload = {
            "started_at_utc": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "deadline_utc": datetime.fromtimestamp(deadline_ts, tz=timezone.utc).isoformat(),
            "now_utc": _utc_now(),
            "hours": args.hours,
            "parallel": args.parallel,
            "tasks_per_round": args.tasks_per_round,
            "checkpoint": str(ckpt_path),
            "curated_output": str(curated_output),
            "rounds_completed": len(rounds),
            "latest": asdict(record),
            "history": [asdict(r) for r in rounds],
        }
        _write_status(status_file, status_payload)

        print(
            f"[round {round_idx} done] collect_exit={collect_exit} train_exit={train_exit} "
            f"eval_exit={eval_exit} eval_acc={eval_acc} epoch:{ckpt_epoch_before}->{ckpt_epoch_after} "
            f"curated_files={curated_files}",
            flush=True,
        )

        if collect_exit != 0:
            print("[warn] collect step failed; continuing", flush=True)
        if train_exit != 0:
            print("[warn] train step failed; continuing", flush=True)

    total_h = (time.time() - start_ts) / 3600.0
    print("\n" + "=" * 72, flush=True)
    print(f"Social deep polish finished. rounds={len(rounds)} elapsed_hours={total_h:.2f}", flush=True)
    print(f"Status file: {status_file}", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    main()
