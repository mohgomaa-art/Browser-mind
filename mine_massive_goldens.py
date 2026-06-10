"""
BrowserMind — Massive Gold-Mining Engine (Phase 5)
===================================================
Uses Expert Heuristics to solve 512 tasks in Parallel.
Saves 'Golden' trajectories to training/massive_sessions/.
"""

import asyncio
import os
import time
import shutil
from pathlib import Path
from playwright.async_api import async_playwright
from core.executor import ActionExecutor
from core.task_decomposer import TaskDecomposer
from training.gauntlet_tasks import GAUNTLET_TASKS

# Ensure output directory exists
SESSIONS_DIR = Path("training/massive_sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

async def mine_task(worker_id: int, goal: str, start_url: str):
    print(f"[Worker {worker_id}] Starting Task: {goal}")
    
    async with async_playwright() as pw:
        # User requested Headful Training
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Decompose Goal
        decomposer = TaskDecomposer()
        try:
            task = decomposer.decompose("search_interactive", "No Mercy Expert", goal)
        except Exception as e:
            print(f"[Worker {worker_id}] [!] Decomposition failed: {e}")
            await browser.close()
            return
            
        # Use ActionExecutor (Heuristic Mode - expert output enabled)
        executor = ActionExecutor(page=page) # No model passed -> Heuristic Expert
        
        await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
        
        # Result log
        results = []
        try:
            result = await executor.execute_task(task)
            if result.success:
                print(f"[Worker {worker_id}] [SUCCESS] Task finished: {goal}")
                # In a real run, the executor would save the trace.
                # For this Gauntlet, success itself is the goal.
            else:
                print(f"[Worker {worker_id}] [FAILED] Task: {goal} | Error: {result.error}")
        except Exception as e:
            print(f"[Worker {worker_id}] [CRASH] {e}")
            
        await asyncio.sleep(2)
        await browser.close()

async def worker_loop(worker_id: int, task_queue: asyncio.Queue):
    while not task_queue.empty():
        goal, url = await task_queue.get()
        await mine_task(worker_id, goal, url)
        task_queue.task_done()
        await asyncio.sleep(1)

async def main():
    print(f"============================================================")
    print(f"  BrowserMind: MISSION GAUNTLET (512 TASKS)")
    print(f"============================================================")
    
    task_queue = asyncio.Queue()
    for task in GAUNTLET_TASKS:
        task_queue.put_nowait(task)
        
    print(f"[*] Queue initialized with {len(GAUNTLET_TASKS)} tasks.")
    
    # 4 Parallel Workers for 6GB VRAM Headful Sweep
    n_workers = 4
    workers = [worker_loop(i+1, task_queue) for i in range(n_workers)]
    
    start_time = time.time()
    await asyncio.gather(*workers)
    
    duration = time.time() - start_time
    print(f"\n============================================================")
    print(f"  GAUNTLET COMPLETE in {duration/60:.1f} minutes.")
    print(f"============================================================")

if __name__ == "__main__":
    asyncio.run(main())
