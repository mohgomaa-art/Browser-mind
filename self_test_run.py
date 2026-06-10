"""
BrowserMind — Self-Test Script
==============================
Verifying the agent's 'Best' model on a live Wikipedia search.
"""

import asyncio
import os
from playwright.async_api import async_playwright
from core.executor import ActionExecutor
from model.agent_policy import AgentPolicy
from core.task_decomposer import AtomicAction, ActionType

async def run_self_test():
    ckpt_path = "checkpoints/best.pt"
    device = "cpu" # Standard for a quick test
    
    print(f"============================================================")
    print(f"  BrowserMind Self-Test: Wikipedia Search")
    print(f"============================================================")
    
    # 1. Load Policy
    policy = AgentPolicy.load(ckpt_path, map_location=device).to(device)
    print(f"[OK] Policy loaded from {ckpt_path}")
    
    async with async_playwright() as pw:
        # Launch headful so I can 'see' it in my head (and user sees headless logs)
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        executor = ActionExecutor(page=page, policy_v2=policy)
        
        goal = "Search for 'DeepMind' on Wikipedia"
        print(f"[*] Goal: {goal}")
        
        # Initial Navigation
        print(f"[*] Navigating to Wikipedia...")
        await page.goto("https://www.wikipedia.org/")
        
        # Run 3-5 steps of autonomous execution
        for step in range(1, 6):
            print(f"\n--- Step {step} ---")
            # In a real run, the AgentPolicy.predict would happen here
            # We'll use the executor's internal logic to simulate a step
            # Actually, let's just use the direct 'execute_task' logic from main
            
            # Since I want to see the decision, I'll manually call predict
            from training.graph_builder import build_graph_from_page
            graph = await build_graph_from_page(page)
            nodes, edges = graph["nodes"], graph["edges"]
            
            pred = policy.predict(nodes, edges, goal)
            print(f"Action  : {pred['action_type']} (Confidence: {pred['confidence']:.2f})")
            print(f"Target  : {pred['top3'][0]['idx'] if pred['top3'] else 'None'}")

            pred_action = pred["action_type"]
            if pred_action == "navigate":
                action_enum = ActionType.OPEN_URL
            else:
                action_enum = ActionType(pred_action)

            target_name = ""
            if pred.get("element_idx") is not None and pred["element_idx"] < len(nodes):
                target_name = str(nodes[pred["element_idx"]].get("name", ""))
            
            # Convert prediction to AtomicAction for execution
            atomic = AtomicAction(
                step=step,
                action_type=action_enum,
                target=target_name,
                element_idx=pred['element_idx'],
                value="DeepMind" if pred['action_type'] == "type" else ""
            )
            
            res = await executor.execute_atomic_action(atomic, goal=goal)
            print(f"Result  : {'SUCCESS' if res.success else 'FAILED'}")
            
            if pred['action_type'] == "done" or not res.success:
                break
                
        print(f"\n============================================================")
        print(f"  Self-Test Complete. Result: {page.url}")
        print(f"============================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_self_test())
