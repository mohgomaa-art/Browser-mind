"""
Run 100 rounds of strict hard complex live tests.

Per round:
- Sample 10 hard tasks from training.complex_tasks
- Execute scratch/test_complex_missions_live.py on those tasks
- Retry once on runtime errors and keep going
- Persist logs and per-round JSON summaries
"""

from __future__ import annotations

import argparse
import atexit
import json
import msvcrt
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / "logs"
ROUND_DIR = LOG_DIR / "no_mercy_hard_complex"
LOCK_FILE = LOG_DIR / "no_mercy_hard_complex_100.lock"
_LOCK_HANDLE = None

SUCCESS_RE = re.compile(r"STRICT_COMPLEX_SUCCESS=(\d+)/(\d+)")
ENV_RE = re.compile(r"ENV_BLOCKED_RATE=(\d+)/(\d+)")
PASS_LINE_RE = re.compile(r"^\s+PASS\s+\|", re.MULTILINE)
FAIL_LINE_RE = re.compile(r"^\s+FAIL\s+\|", re.MULTILINE)


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _acquire_lock() -> bool:
    """Acquire a single-instance lock using OS file locking (Windows-safe)."""
    global _LOCK_HANDLE

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch(exist_ok=True)

    fh = LOCK_FILE.open("r+", encoding="utf-8")
    try:
        # Lock the first byte. If already locked by another process, fail fast.
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return False

    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _LOCK_HANDLE = fh

    def _release() -> None:
        try:
            if _LOCK_HANDLE is not None:
                try:
                    _LOCK_HANDLE.seek(0)
                    msvcrt.locking(_LOCK_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
                _LOCK_HANDLE.close()
        except Exception:
            pass

    atexit.register(_release)
    return True


def _log(line: str, log_file: Path) -> None:
    msg = f"[{_timestamp()}] {line}"
    print(msg, flush=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _pick_ckpt(explicit: str = "") -> Path:
    if explicit:
        p = ROOT / explicit
        if p.exists():
            return p
        raise FileNotFoundError(f"checkpoint not found: {p}")

    candidates = [
        ROOT / "checkpoints/browsermind_super_complex_10h.pt",
        ROOT / "checkpoints/browsermind_no_mercy_24h.pt",
        ROOT / "checkpoints/best_ever.pt",
        ROOT / "checkpoints/best.pt",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("no checkpoint found in known candidates")


def _sample_hard_tasks(n_tasks: int, seed: int) -> list[dict[str, str]]:
    from training.complex_tasks import get_hard_tasks

    tasks = get_hard_tasks()
    if not tasks:
        raise RuntimeError("no hard tasks available from training.complex_tasks")

    rng = random.Random(seed)
    if len(tasks) >= n_tasks:
        picked = rng.sample(tasks, n_tasks)
    else:
        picked = [rng.choice(tasks) for _ in range(n_tasks)]

    return [
        {
            "goal": str(goal),
            "url": str(url),
            "family": str(task_type),
        }
        for goal, url, task_type, _difficulty in picked
    ]


def _parse_summary(output: str) -> dict[str, Any]:
    success_match = SUCCESS_RE.search(output)
    env_match = ENV_RE.search(output)

    pass_lines = len(PASS_LINE_RE.findall(output))
    fail_lines = len(FAIL_LINE_RE.findall(output))

    summary: dict[str, Any] = {
        "pass_lines": pass_lines,
        "fail_lines": fail_lines,
    }

    if success_match:
        summary["strict_success"] = int(success_match.group(1))
        summary["strict_total"] = int(success_match.group(2))
    else:
        summary["strict_success"] = pass_lines
        summary["strict_total"] = pass_lines + fail_lines

    if env_match:
        summary["env_blocked"] = int(env_match.group(1))
        summary["env_total"] = int(env_match.group(2))
    else:
        summary["env_blocked"] = 0
        summary["env_total"] = summary["strict_total"]

    return summary


def _find_latest_summary() -> Path | None:
    files = sorted(LOG_DIR.glob("no_mercy_hard_complex_100_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _summary_from_args(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.summary_json:
        summary = Path(args.summary_json)
        if not summary.is_absolute():
            summary = ROOT / summary
    elif args.run_id:
        summary = LOG_DIR / f"no_mercy_hard_complex_100_{args.run_id}.json"
    elif not args.fresh:
        latest = _find_latest_summary()
        if latest is not None:
            summary = latest
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            summary = LOG_DIR / f"no_mercy_hard_complex_100_{stamp}.json"
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = LOG_DIR / f"no_mercy_hard_complex_100_{stamp}.json"

    log_file = summary.with_suffix(".log")
    return summary, log_file


def _load_or_init_aggregate(
    json_summary: Path,
    rounds: int,
    tasks_per_round: int,
    max_steps: int,
    seed: int,
) -> dict[str, Any]:
    if json_summary.exists():
        try:
            loaded = json.loads(json_summary.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("started_at", _timestamp())
                loaded.setdefault("results", [])
                loaded["rounds"] = int(rounds)
                loaded["tasks_per_round"] = int(tasks_per_round)
                loaded["max_steps"] = int(max_steps)
                loaded["seed"] = int(seed)
                return loaded
        except Exception:
            pass

    return {
        "started_at": _timestamp(),
        "rounds": int(rounds),
        "tasks_per_round": int(tasks_per_round),
        "max_steps": int(max_steps),
        "seed": int(seed),
        "results": [],
    }


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _recompute_rollup(results_by_round: dict[int, dict[str, Any]]) -> tuple[int, int, int, int]:
    completed = len(results_by_round)
    total_pass = 0
    total_fail = 0
    runtime_errors = 0
    for r in results_by_round.values():
        rs = _coerce_int(r.get("strict_success", 0), 0)
        rt = _coerce_int(r.get("strict_total", 0), 0)
        rf = _coerce_int(r.get("strict_fail", max(rt - rs, 0)), max(rt - rs, 0))
        rc = _coerce_int(r.get("return_code", 0), 0)
        total_pass += rs
        total_fail += max(rf, 0)
        if rc != 0:
            runtime_errors += 1
    return completed, total_pass, total_fail, runtime_errors


def _run_round(
    python_bin: str,
    ckpt: Path,
    tasks_file: Path,
    max_steps: int,
    timeout_sec: int,
    log_file: Path,
) -> tuple[int, str, str, int]:
    cmd = [
        python_bin,
        "scratch/test_complex_missions_live.py",
        "--ckpt",
        str(ckpt),
        "--tasks-file",
        str(tasks_file),
        "--max-steps",
        str(max_steps),
    ]

    last_stdout = ""
    last_stderr = ""

    for attempt in (1, 2):
        _log("RUN attempt=" + str(attempt) + " cmd=" + " ".join(cmd), log_file)
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                timeout=timeout_sec,
            )
            elapsed = int(time.time() - start)
            last_stdout = proc.stdout or ""
            last_stderr = proc.stderr or ""

            with log_file.open("a", encoding="utf-8") as f:
                if last_stdout:
                    f.write(last_stdout)
                if last_stderr:
                    f.write(last_stderr)

            _log(f"EXIT attempt={attempt} code={proc.returncode} elapsed={elapsed}s", log_file)
            if proc.returncode == 0:
                return 0, last_stdout, last_stderr, elapsed

            # Error recovery: retry once after short backoff.
            if attempt == 1:
                _log("WARN round runtime error; retrying once", log_file)
                time.sleep(2)

        except subprocess.TimeoutExpired as e:
            elapsed = int(time.time() - start)
            last_stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            last_stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            with log_file.open("a", encoding="utf-8") as f:
                f.write(last_stdout)
                f.write(last_stderr)
            _log(f"EXIT attempt={attempt} code=124 elapsed={elapsed}s timeout", log_file)
            if attempt == 1:
                _log("WARN round timeout; retrying once", log_file)
                time.sleep(2)
            else:
                return 124, last_stdout, last_stderr, elapsed

    return 1, last_stdout, last_stderr, 0


def main() -> None:
    p = argparse.ArgumentParser(description="Run hard complex strict tests no-mercy loop")
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--tasks-per-round", type=int, default=10)
    p.add_argument("--max-steps", type=int, default=10)
    p.add_argument("--seed", type=int, default=7000)
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--ckpt", default="")
    p.add_argument("--run-id", default="", help="Optional fixed run id for summary/log names")
    p.add_argument("--summary-json", default="", help="Optional summary json path to update/resume")
    p.add_argument("--fresh", action="store_true", help="Start a new run instead of resuming latest summary")
    args = p.parse_args()

    if not _acquire_lock():
        print("[LOCK] another run_no_mercy_hard_complex_100.py instance is already active; exiting")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ROUND_DIR.mkdir(parents=True, exist_ok=True)

    json_summary, log_file = _summary_from_args(args)
    aggregate = _load_or_init_aggregate(
        json_summary=json_summary,
        rounds=int(args.rounds),
        tasks_per_round=int(args.tasks_per_round),
        max_steps=int(args.max_steps),
        seed=int(args.seed),
    )

    checkpoint_from_summary = str(aggregate.get("checkpoint", "")).strip()
    if args.ckpt:
        ckpt = _pick_ckpt(args.ckpt)
    elif checkpoint_from_summary and Path(checkpoint_from_summary).exists():
        ckpt = Path(checkpoint_from_summary)
    else:
        ckpt = _pick_ckpt("")

    aggregate["checkpoint"] = str(ckpt)
    py = sys.executable

    existing_results = aggregate.get("results", [])
    if not isinstance(existing_results, list):
        existing_results = []

    results_by_round: dict[int, dict[str, Any]] = {}
    for item in existing_results:
        if isinstance(item, dict):
            round_no = _coerce_int(item.get("round", 0), 0)
            if round_no > 0:
                results_by_round[round_no] = item

    completed_rounds, total_pass, total_fail, runtime_errors = _recompute_rollup(results_by_round)

    _log("=== HARD COMPLEX NO-MERCY START/RESUME ===", log_file)
    _log(f"rounds={args.rounds} tasks_per_round={args.tasks_per_round} max_steps={args.max_steps}", log_file)
    _log(f"seed={args.seed} timeout_sec={args.timeout_sec}", log_file)
    _log(f"python={py}", log_file)
    _log(f"checkpoint={ckpt}", log_file)
    _log(f"summary_json={json_summary}", log_file)
    _log(f"completed_rounds_before_resume={completed_rounds}", log_file)

    if completed_rounds >= int(args.rounds):
        final_rate = 100.0 * total_pass / max(total_pass + total_fail, 1)
        _log("RUN_ALREADY_COMPLETE requested rounds already reached", log_file)
        _log(f"TOTAL_PASS={total_pass}", log_file)
        _log(f"TOTAL_FAIL={total_fail}", log_file)
        _log(f"TOTAL_RATE={final_rate:.2f}%", log_file)
        _log(f"RUNTIME_ERRORS={runtime_errors}", log_file)
        _log(f"SUMMARY_JSON={json_summary}", log_file)
        return

    for round_idx in range(completed_rounds + 1, int(args.rounds) + 1):
        round_seed = int(args.seed) + round_idx
        round_name = f"round_{round_idx:03d}"
        tasks_path = ROUND_DIR / f"{round_name}_tasks.json"

        tasks = _sample_hard_tasks(int(args.tasks_per_round), round_seed)
        tasks_path.write_text(json.dumps(tasks, ensure_ascii=True, indent=2), encoding="utf-8")

        _log(f"--- {round_name} seed={round_seed} ---", log_file)

        rc, stdout, stderr, elapsed = _run_round(
            python_bin=py,
            ckpt=ckpt,
            tasks_file=tasks_path,
            max_steps=int(args.max_steps),
            timeout_sec=int(args.timeout_sec),
            log_file=log_file,
        )

        parsed = _parse_summary(stdout + "\n" + stderr)
        r_pass = int(parsed.get("strict_success", 0))
        r_total = int(parsed.get("strict_total", 0))
        r_fail = max(r_total - r_pass, 0)

        round_result = {
            "round": round_idx,
            "seed": round_seed,
            "return_code": rc,
            "elapsed_sec": elapsed,
            "strict_success": r_pass,
            "strict_total": r_total,
            "strict_fail": r_fail,
            "env_blocked": int(parsed.get("env_blocked", 0)),
            "env_total": int(parsed.get("env_total", r_total)),
            "tasks_file": str(tasks_path),
        }
        results_by_round[round_idx] = round_result

        ordered_rounds = sorted(results_by_round.keys())
        aggregate["results"] = [results_by_round[r] for r in ordered_rounds]

        completed_rounds, total_pass, total_fail, runtime_errors = _recompute_rollup(results_by_round)

        rate = (100.0 * r_pass / max(r_total, 1)) if r_total > 0 else 0.0
        _log(
            f"ROUND_RESULT {round_name} pass={r_pass}/{r_total} ({rate:.1f}%) rc={rc} elapsed={elapsed}s",
            log_file,
        )

        aggregate["completed_rounds"] = completed_rounds
        aggregate["total_pass"] = total_pass
        aggregate["total_fail"] = total_fail
        aggregate["runtime_errors"] = runtime_errors
        aggregate["updated_at"] = _timestamp()
        json_summary.write_text(json.dumps(aggregate, ensure_ascii=True, indent=2), encoding="utf-8")

    final_rate = 100.0 * total_pass / max(total_pass + total_fail, 1)
    _log("=== HARD COMPLEX NO-MERCY COMPLETE ===", log_file)
    _log(f"TOTAL_PASS={total_pass}", log_file)
    _log(f"TOTAL_FAIL={total_fail}", log_file)
    _log(f"TOTAL_RATE={final_rate:.2f}%", log_file)
    _log(f"RUNTIME_ERRORS={runtime_errors}", log_file)
    _log(f"SUMMARY_JSON={json_summary}", log_file)


if __name__ == "__main__":
    main()
