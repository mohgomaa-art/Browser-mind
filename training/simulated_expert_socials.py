"""
Explicit simulated expert training for Login, Logout, and Social interactions.
Generates Golden Sessions for Behavioral Cloning.
"""
import asyncio
import sys
import os
import time
from pathlib import Path

sys.path.append(os.getcwd())
from playwright.async_api import async_playwright
from collect_massive import SessionRecorder, _execute_action
from training.graph_builder import build_graph_from_page_pruned

SESSIONS_DIR = Path("training/massive_sessions")

async def record_expert_flow(pw, flow_name: str, url: str, steps: list):
    print(f"Starting Manual Expert Flow: {flow_name} at {url}")
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(url)
    
    recorder = SessionRecorder(f"Expert demonstration: {flow_name}", SESSIONS_DIR)
    
    step_num = 1
    for action_type, action_id, role, name_hint, value, wait_ms in steps:
        await asyncio.sleep(1.5)
        
        # Capture Graph
        graph = await build_graph_from_page_pruned(page, max_nodes=100)
        nodes = graph.get("nodes", [])
        
        # Find element by role and name hint
        element_idx = None
        if action_type in ["click", "type", "extract"] and role:
            for n in nodes:
                if n["role"] == role and (name_hint.lower() in n["name"].lower()):
                    element_idx = n["idx"]
                    break
            
            # Fallback for generic buttons or links
            if element_idx is None:
                for n in nodes:
                    if name_hint.lower() in n["name"].lower():
                       element_idx = n["idx"]
                       break 
        
        # Allow default actions like scroll to pass through without specific elements
        
        expert_action = {
            "type": action_type,
            "action_id": action_id,
            "element_idx": element_idx,
            "value": value,
            "target_text": name_hint,
        }
        
        recorder.record(graph, expert_action, page.url, step_num, success=True)
        print(f"  Step {step_num}: {action_type} on '{name_hint}' (Idx: {element_idx})")
        
        if action_type == "done":
            break
            
        try:
            await _execute_action(page, expert_action, nodes)
        except Exception as e:
            print(f"  [Error Executing Action]: {e}")
            
        await asyncio.sleep(wait_ms / 1000.0)
        step_num += 1

    if recorder.is_trainable():
        path = recorder.save(f"S_GOLD_MANUAL_{flow_name}")
        print(f"Saved Golden Session: {path}")
    await browser.close()

async def main():
    async with async_playwright() as pw:
        # Example 1: GitHub Sign In & Sign Out
        github_steps = [
            ("click", 1, "link", "Sign in", "", 3000),
            ("type", 2, "textbox", "Username", "expert_teacher@example.com", 1000),
            ("type", 2, "textbox", "Password", "SimulatedPassword123!", 1000),
            ("click", 1, "button", "Sign in", "", 5000),
            ("click", 1, "button", "Open user account", "", 2000),
            ("click", 1, "menuitem", "Sign out", "", 3000),
            ("done", 7, None, "", "", 0)
        ]
        
        # Wikipedia Login/Logout (Highly stable target)
        wiki_steps = [
            ("click", 1, "link", "Log in", "", 3000),
            ("type", 2, "textbox", "Username", "ExpertBrowser", 1000),
            ("type", 2, "textbox", "Password", "TestPass", 1000),
            ("click", 1, "button", "Log in", "", 3000),
            ("click", 1, "link", "Log out", "", 2000),
            ("done", 7, None, "", "", 0)
        ]

        # HackerNews Login/Logout
        hn_steps = [
            ("click", 1, "link", "login", "", 2000),
            ("type", 2, "textbox", "username", "ExpertAI", 1000),
            ("type", 2, "textbox", "password", "AIPass", 1000),
            ("click", 1, "button", "login", "", 3000),
            ("click", 1, "link", "logout", "", 2000),
            ("done", 7, None, "", "", 0)
        ]

        print("--- GENERATING MANUAL LOGIN/LOGOUT & SOCIAL EXPERT SESSIONS ---")
        try:
            await record_expert_flow(pw, "GITHUB_AUTH", "https://github.com", github_steps)
        except Exception as e: print(f"Error on Github: {e}")
        
        try:
            await record_expert_flow(pw, "WIKI_AUTH", "https://en.wikipedia.org", wiki_steps)
        except Exception as e: print(f"Error on Wiki: {e}")
        
        try:
            await record_expert_flow(pw, "HN_AUTH", "https://news.ycombinator.com/", hn_steps)
        except Exception as e: print(f"Error on HN: {e}")

if __name__ == "__main__":
    asyncio.run(main())
