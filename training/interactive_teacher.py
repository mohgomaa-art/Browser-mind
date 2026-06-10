import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright
import sys
import os

# Ensure local imports work
sys.path.append(os.getcwd())

from training.graph_builder import build_graph_from_page_pruned
from collect_massive import SessionRecorder

ACTION_MAP = {
    "navigate": 0, "click": 1, "type": 2, "scroll": 3, "wait": 4,
    "extract": 5, "go_back": 6, "done": 7
}

async def run_teacher():
    print("=== BrowserMind Manual Teacher Mode ===")
    goal = input("Enter Task Goal (e.g., 'Log in to Gmail'): ").strip()
    url = input("Enter Start URL: ").strip()
    
    save_dir = Path("training/massive_sessions")
    recorder = SessionRecorder(goal, save_dir)
    sid = f"S_GOLD_{int(time.time())}"
    
    async with async_playwright() as pw:
        # Launch visible browser for human interaction
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        print(f"\nNavigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded")
        
        step = 1
        while True:
            print(f"\n--- STEP {step} ---")
            print("Capturing page state...")
            try:
                graph = await build_graph_from_page_pruned(page, max_nodes=60)
            except Exception as e:
                print(f"Error capturing graph: {e}")
                break
                
            nodes = graph.get("nodes", [])
            print(f"Captured {len(nodes)} nodes.")
            
            # Show top interactive nodes for reference
            for nd in nodes[:20]:
                print(f"  [{nd['idx']}] {nd['role']:<12} {nd['name'][:50]!r}")
            
            print("\nAvailable Actions:", ", ".join(ACTION_MAP.keys()))
            action_type = input("Action Type (or 'quit'): ").strip().lower()
            if action_type == 'quit':
                break
            
            if action_type not in ACTION_MAP:
                print("Invalid action type.")
                continue
                
            action_id = ACTION_MAP[action_type]
            
            element_idx = None
            if action_type in ("click", "type", "extract"):
                try:
                    e_input = input("Element Index (from square brackets): ").strip()
                    element_idx = int(e_input) if e_input else None
                except ValueError:
                    print("Invalid index.")
                    continue
            
            value = ""
            if action_type in ("type", "navigate", "filter"):
                value = input("Value (text to type / URL): ").strip()

            target_text = ""
            if isinstance(element_idx, int) and 0 <= element_idx < len(nodes):
                target_text = str(nodes[element_idx].get("name", ""))
            
            expert_action = {
                "type": action_type,
                "action_id": action_id,
                "element_idx": element_idx,
                "value": value,
                "target_text": target_text,
            }
            
            # Record
            recorder.record(graph, expert_action, page.url, step, success=True)
            print(f"Recorded: {expert_action}")
            
            # Execute in browser (optional, but good for sync)
            from collect_massive import _execute_action
            await _execute_action(page, expert_action, nodes)
            
            if action_type == "done":
                break
            
            step += 1
            time.sleep(1) # wait for DOM update
            
        if recorder.is_trainable():
            path = recorder.save(sid)
            print(f"\n[SUCCESS] Golden Session saved to: {path}")
        else:
            print("\n[SKIP] Session too short to be trainable.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_teacher())
