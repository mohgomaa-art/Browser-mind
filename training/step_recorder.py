import asyncio
import json
import time
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Ensure local imports work
sys.path.append(os.getcwd())
from training.graph_builder import build_graph_from_page_pruned
from collect_massive import SessionRecorder, _execute_action

class StepRecorder:
    def __init__(self, goal: str, sid: str = None):
        self.goal = goal
        self.sid = sid or f"S_GOLD_{int(time.time())}"
        self.save_dir = Path("training/massive_sessions")
        self.recorder = SessionRecorder(goal, self.save_dir)
        self.step = 1
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self, url: str):
        self.pw = await async_playwright().start()
        # Launch visible for user to see (using --headless=false internally)
        self.browser = await self.pw.chromium.launch(headless=True) # Use headless for agent, or False if user screen.
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 800})
        self.page = await self.context.new_page()
        print(f"Navigating to {url}...")
        await self.page.goto(url, wait_until="domcontentloaded")
        return await self.capture_state()

    async def capture_state(self):
        print(f"Capturing state for step {self.step}...")
        graph = await build_graph_from_page_pruned(self.page, max_nodes=100)
        # Simplify graph for display to agent
        nodes = graph.get("nodes", [])
        display_nodes = []
        for n in nodes[:30]:
            display_nodes.append({"idx": n["idx"], "role": n["role"], "text": n["name"][:50]})
        
        state_info = {
            "step": self.step,
            "url": self.page.url,
            "nodes": display_nodes,
            "full_graph": graph # stored internally
        }
        return state_info

    async def record_action(self, action_type: str, element_idx: int = None, value: str = ""):
        # 1. Capture current graph for the record
        graph = await build_graph_from_page_pruned(self.page, max_nodes=100)
        
        # 2. Map action
        action_map = {
            "navigate": 0, "click": 1, "type": 2, "scroll": 3, "wait": 4,
            "extract": 5, "go_back": 6, "done": 7
        }
        action_id = action_map.get(action_type, 1)
        target_text = ""
        if isinstance(element_idx, int):
            nodes_now = graph.get("nodes", [])
            if 0 <= element_idx < len(nodes_now):
                target_text = str(nodes_now[element_idx].get("name", ""))
        
        expert_action = {
            "type": action_type,
            "action_id": action_id,
            "element_idx": element_idx,
            "value": value,
            "target_text": target_text,
        }
        
        # 3. Record
        self.recorder.record(graph, expert_action, self.page.url, self.step, success=True)
        print(f"Recorded Step {self.step}: {action_type} on {element_idx}")
        
        # 4. Execute
        nodes = graph.get("nodes", [])
        await _execute_action(self.page, expert_action, nodes)
        
        self.step += 1
        await asyncio.sleep(2) # wait for DOM
        return await self.capture_state()

    async def finish(self):
        if self.recorder.is_trainable():
            path = self.recorder.save(self.sid)
            print(f"GOLD session saved: {path}")
        await self.browser.close()
        await self.pw.stop()

# Wrapper for CLI persistence
if __name__ == "__main__":
    # We use a state file to persist between CLI calls if needed, 
    # but for first pass, I'll just run a dedicated interactive script.
    pass
