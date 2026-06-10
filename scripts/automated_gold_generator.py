import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright
import sys
import os

sys.path.append(os.getcwd())
from training.graph_builder import build_graph_from_page_pruned
from collect_massive import SessionRecorder, _execute_action

# Perfect expert trajectories for Gold Surge
GOLD_SCENARIOS = [
    {
        "goal": "Login to GitHub",
        "url": "https://github.com/login",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "demo_user"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "password123"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Sign in to Yahoo Mail",
        "url": "https://login.yahoo.com/",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "test@yahoo.com"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Access Microsoft Office",
        "url": "https://login.microsoftonline.com/",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "office_user@outlook.com"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Create a GitHub Account",
        "url": "https://github.com/signup",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "new_user@example.com"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "secure_pass_123"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "unique_username_99"},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Register on Reddit",
        "url": "https://www.reddit.com/register/",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "reddit_newbie@yahoo.com"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Login to LeetCode",
        "url": "https://leetcode.com/accounts/login/",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "lc_user"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "pass123"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Navigate to ProductHunt Login",
        "url": "https://www.producthunt.com",
        "steps": [
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Sign in to Coursera",
        "url": "https://www.coursera.org/?authMode=login",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "test@coursera.com"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "pass123"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": ""},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Sign in to Gmail",
        "url": "https://accounts.google.com/InteractiveLogin",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "demo_user@gmail.com"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": "Next"},
            {"type": "wait", "action_id": 4, "element_idx": None, "value": ""},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "password123"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": "Next"},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    },
    {
        "goal": "Create Gmail Account",
        "url": "https://accounts.google.com/signup",
        "steps": [
            {"type": "type", "action_id": 2, "element_idx": None, "value": "First"},
            {"type": "type", "action_id": 2, "element_idx": None, "value": "Last"},
            {"type": "click", "action_id": 1, "element_idx": None, "value": "Next"},
            {"type": "done", "action_id": 7, "element_idx": -1, "value": ""}
        ]
    }
]

async def generate_gold_traces():
    save_dir = Path("training/massive_sessions")
    save_dir.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as pw:
        # Use headless=True for speed, but the states are real
        browser = await pw.chromium.launch(headless=True)
        
        for i, scenario in enumerate(GOLD_SCENARIOS):
            print(f"Generating Gold Trace {i+1}: {scenario['goal']}")
            sid = f"S_GOLD_AUTO_{int(time.time())}_{i}"
            recorder = SessionRecorder(scenario['goal'], save_dir)
            
            page = await browser.new_page()
            try:
                await page.goto(scenario['url'], wait_until="domcontentloaded", timeout=30000)
                
                for step_idx, step_action in enumerate(scenario['steps']):
                    # Capture State BEFORE action
                    graph = await build_graph_from_page_pruned(page, max_nodes=60)
                    nodes = graph.get("nodes", [])
                    
                    # Heuristic to find the 'best' element index to make the trace useful
                    if step_action['type'] in ('click', 'type'):
                        # If we have a type action, look for the first input
                        if step_action['type'] == 'type':
                            inputs = [n for n in nodes if n.get('role') == 'textbox' or 'input' in n.get('name', '').lower()]
                            if inputs: step_action['element_idx'] = inputs[0]['idx']
                        # If click, look for the first button
                        if step_action['type'] == 'click':
                            btns = [n for n in nodes if n.get('role') in ('button', 'link')]
                            if btns: step_action['element_idx'] = btns[0]['idx']
                    
                    recorder.record(graph, step_action, page.url, step_idx + 1)
                    
                    # Execute
                    await _execute_action(page, step_action, nodes)
                    await asyncio.sleep(1)
                    
                path = recorder.save(sid)
                print(f"  [ok] Saved to {path}")
            except Exception as e:
                print(f"  [err] Failed {scenario['goal']}: {e}")
            finally:
                await page.close()
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(generate_gold_traces())
