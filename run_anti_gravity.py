"""
Anti-Gravity training loop.

Collect -> clean -> train -> eval(seen + golden) -> analyze overrides -> repeat
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import torch

from collect_massive import (
    CHECKPOINTS_DIR,
    SESSIONS_DIR,
    _eval_golden,
    _log,
    _train_epochs,
    build_task_queue,
    collect_parallel,
    eval_held_out,
    load_state,
    save_ckpt,
    save_state,
)
from logs.override_tracker import analyze_overrides
from model.agent_policy import AgentPolicy


async def run_anti_gravity_round(
    round_idx: int,
    policy: AgentPolicy,
    optimizer: torch.optim.Optimizer,
    all_session_files: list[Path],
    total_sessions: int,
    blocked_urls: dict[str, int],
    n_collect: int = 10,
    n_parallel: int = 5,
) -> tuple[bool, list[Path], int, dict]:
    _log(f"\n{'=' * 50}")
    _log(f"ANTI-GRAVITY ROUND {round_idx:03d}")
    _log(f"{'=' * 50}")

    round_save_dir = SESSIONS_DIR / f"anti_gravity_round_{round_idx:04d}"
    round_save_dir.mkdir(parents=True, exist_ok=True)

    tasks_queue = build_task_queue(
        n_sessions=n_collect,
        blocked_urls=blocked_urls,
        round_num=round_idx,
        save_dir=round_save_dir,
        existing_count=total_sessions,
    )
    new_sessions = await collect_parallel(
        tasks_queue=tasks_queue,
        n_parallel=n_parallel,
        blocked_urls=blocked_urls,
        policy=policy if total_sessions > 0 else None,
    )
    clean_sessions = list(new_sessions)
    _log(f"  Sessions: {len(new_sessions)} collected, {len(clean_sessions)} clean")

    if clean_sessions:
        all_session_files.extend(clean_sessions)
        metrics = _train_epochs(
            policy=policy,
            session_files=all_session_files,
            optimizer=optimizer,
            device=next(policy.parameters()).device,
            n_epochs=1,
        )
    else:
        metrics = {}

    seen_score = await eval_held_out(policy, n_parallel=3)
    golden_score = await _eval_golden(policy)
    metrics["task_success"] = seen_score
    metrics["golden_success"] = golden_score
    _log(f"  Seen: {seen_score:.1%} | Golden: {golden_score:.1%}")

    analysis = analyze_overrides(min_events=10)
    if analysis.get("status") == "ok":
        _log(f"  Override accuracy: {analysis['model_accuracy']:.1%}")
        _log(f"  Recommended threshold: {analysis['recommended_threshold']}")

    total_sessions += len(clean_sessions)
    save_ckpt(policy, optimizer, round_idx, total_sessions, metrics)
    save_state({
        "total_sessions": total_sessions,
        "round": round_idx,
        "lr": optimizer.param_groups[0]["lr"],
        "lr_milestone": 1000,
        "blocked_urls": blocked_urls,
        "all_session_files": [str(path) for path in all_session_files[-2000:]],
    })

    if seen_score >= 0.65 and golden_score >= 0.40:
        _log("[CONVERGED] Both seen and unseen thresholds met. Stopping.")
        return True, all_session_files, total_sessions, metrics

    if round_idx >= 15 and golden_score < 0.25:
        _log("[OVERFIT WARNING] Golden eval < 25% after Round 15. Check data quality.")

    return False, all_session_files, total_sessions, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--parallel", type=int, default=5)
    parser.add_argument("--collect", type=int, default=10)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    policy = AgentPolicy().to(device)
    state = load_state()

    best_ckpt = CHECKPOINTS_DIR / "best.pt"
    if best_ckpt.exists():
        try:
            policy.load_weights(str(best_ckpt))
        except Exception as exc:
            _log(f"[warn] Could not load best checkpoint: {exc}")

    optimizer = torch.optim.AdamW(policy.parameters(), lr=3e-4, weight_decay=1e-4)
    all_session_files = [Path(path) for path in state.get("all_session_files", []) if Path(path).exists()]
    total_sessions = state.get("total_sessions", 0)
    blocked_urls = state.get("blocked_urls", {})
    start_round = state.get("round", 0) + 1

    for round_idx in range(start_round, start_round + args.rounds):
        converged, all_session_files, total_sessions, _ = asyncio.run(
            run_anti_gravity_round(
                round_idx=round_idx,
                policy=policy,
                optimizer=optimizer,
                all_session_files=all_session_files,
                total_sessions=total_sessions,
                blocked_urls=blocked_urls,
                n_collect=args.collect,
                n_parallel=args.parallel,
            )
        )
        if converged:
            break


if __name__ == "__main__":
    main()
