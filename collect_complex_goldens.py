"""
BrowserMind - Auto-Collect Complex Goldens
===========================================
Collects high-quality expert sessions for complex browser missions.

Modes:
  - all:           sample from the full complex task pool
  - super-complex: focus on signup/login/logout/post/write/select/fill flows

Usage:
  python collect_complex_goldens.py --num-tasks 30
  python collect_complex_goldens.py --mode super-complex --num-tasks 40 --min-difficulty 2
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path
from typing import List, Tuple

from playwright.async_api import async_playwright

from collect_and_train import run_task
from collect_massive import USER_AGENTS
from training.complex_tasks import ALL_COMPLEX_TASKS

Task = Tuple[str, str, str, int]

SUPER_TYPES = {
    "signup",
    "login",
    "logout",
    "form_fill",
    "dropdown",
    "checkbox",
    "multistep",
    "account",
}

SUPER_KEYWORDS = (
    "create account",
    "sign up",
    "signup",
    "register",
    "login",
    "log in",
    "logout",
    "log out",
    "post",
    "write",
    "select",
    "fill",
)


def _is_super_complex_task(task: Task, min_difficulty: int) -> bool:
    goal, _, task_type, difficulty = task
    if difficulty < min_difficulty:
        return False
    goal_l = goal.lower()
    if task_type in SUPER_TYPES:
        return True
    return any(k in goal_l for k in SUPER_KEYWORDS)


def _build_task_pool(mode: str, min_difficulty: int) -> List[Task]:
    tasks = list(ALL_COMPLEX_TASKS)
    if mode == "super-complex":
        tasks = [t for t in tasks if _is_super_complex_task(t, min_difficulty)]
    return tasks


async def collect_complex_goldens(
    num_tasks: int = 100,
    mode: str = "super-complex",
    min_difficulty: int = 2,
    save_dir: Path = Path("training/super_complex_sessions"),
    headless: bool = True,
    seed: int = 42,
    timeout_sec: float = 180.0,
):
    print(f"\n{'=' * 70}")
    print("[*] Starting complex mission collection")
    print(f"    mode={mode} | target={num_tasks} | min_difficulty={min_difficulty}")
    print(f"    save_dir={save_dir}")
    print(f"{'=' * 70}\n")

    save_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)
    pool = _build_task_pool(mode=mode, min_difficulty=min_difficulty)
    if not pool:
        print("[!] No tasks matched the current filters.")
        return

    random.shuffle(pool)
    if num_tasks <= len(pool):
        tasks_to_run = pool[:num_tasks]
    else:
        tasks_to_run = [random.choice(pool) for _ in range(num_tasks)]
        print(f"    pool={len(pool)} — sampling {num_tasks} with replacement")
    successful_sessions = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        for idx, task in enumerate(tasks_to_run, 1):
            goal, url, task_type, difficulty = task
            sid = f"S_COMPLEX_{task_type.upper()}_{int(time.time())}_{idx:04d}"

            print(f"[{idx}/{len(tasks_to_run)}] Goal: {goal}")
            print(f"             URL: {url}")
            print(f"            Type: {task_type.upper()} | Diff: {difficulty}")

            ua = random.choice(USER_AGENTS)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=ua,
                locale="en-US",
                ignore_https_errors=True,
            )
            await context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            page = await context.new_page()

            try:
                saved_path = await asyncio.wait_for(
                    run_task(
                        goal=goal,
                        start_url=url,
                        session_id=sid,
                        save_dir=save_dir,
                        page=page,
                        policy=None,
                    ),
                    timeout=timeout_sec,
                )

                if saved_path:
                    successful_sessions += 1
                    print(f"  [OK] Saved -> {Path(saved_path).name}\n")
                else:
                    # run_task may persist a non-trainable trace; keep dataset clean here.
                    stale = save_dir / f"{sid}.json"
                    if stale.exists():
                        stale.unlink(missing_ok=True)
                    print("  [FAIL] Session was not trainable.\n")

            except asyncio.TimeoutError:
                print("  [TIMEOUT] Task exceeded timeout, skipped.\n")
            except Exception as e:
                print(f"  [ERROR] {e}\n")
            finally:
                await context.close()
                await asyncio.sleep(1.0)

        await browser.close()

    print(f"\n{'=' * 70}")
    print("[*] Collection completed")
    print(f"    Success: {successful_sessions}/{len(tasks_to_run)}")
    print(f"    Output : {save_dir}")
    print(f"{'=' * 70}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect complex BrowserMind sessions")
    p.add_argument("--num-tasks", type=int, default=30)
    p.add_argument("--mode", choices=["all", "super-complex"], default="super-complex")
    p.add_argument("--min-difficulty", type=int, default=2)
    p.add_argument("--save-dir", default="training/super_complex_sessions")
    p.add_argument("--headless", type=lambda x: x.lower() != "false", default=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout-sec", type=float, default=180.0)
    return p.parse_args()


if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.resolve()))
    args = parse_args()
    asyncio.run(
        collect_complex_goldens(
            num_tasks=args.num_tasks,
            mode=args.mode,
            min_difficulty=args.min_difficulty,
            save_dir=Path(args.save_dir),
            headless=args.headless,
            seed=args.seed,
            timeout_sec=args.timeout_sec,
        )
    )
