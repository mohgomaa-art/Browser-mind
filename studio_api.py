import asyncio
import sys
import os
import json
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path

# Bridge to BrowserMind Core
from core.task_decomposer import TaskDecomposer
from core.executor import ActionExecutor
from core.privacy import redact_sensitive_text, sanitize_goal_for_storage
from model.agent_policy import AgentPolicy

app = FastAPI(title="BrowserMind Studio")

# Shared state
class StudioState:
    def __init__(self):
        self.device = "cpu"
        self.policy = None
        self.decomposer = TaskDecomposer()
        self.log_queue = asyncio.Queue()

    def set_device(self, dev: str):
        self.device = dev

    async def add_log(self, msg: str):
        await self.log_queue.put(msg)

state = StudioState()

class ChatRequest(BaseModel):
    goal: str

# --- Custom Log Redirector ---
class StudioLogger:
    def write(self, data):
        if data.strip():
            # In a real app, we'd use a thread-safe queue. 
            # For this 'Quick GUI', we'll rely on the executor's async nature.
            pass
    def flush(self):
        pass

# --- Initialization ---
@app.on_event("startup")
async def startup_event():
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    state.set_device(dev)
    
    # Try to load best_ever.pt first
    ckpt_path = "checkpoints/best_ever.pt"
    if not os.path.exists(ckpt_path):
        ckpt_path = "checkpoints/best.pt"
    
    if os.path.exists(ckpt_path):
        state.policy = AgentPolicy.load(ckpt_path, map_location=dev).to(dev)
        print(f"[STUDIO] Policy loaded from {ckpt_path}")
    else:
        print("[STUDIO] [!] No checkpoint found. Running in heuristic mode.")

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("studio.html", "r") as f:
        return f.read()

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    async def log_stream():
        safe_goal = sanitize_goal_for_storage(req.goal)
        yield f"[*] Goal: {safe_goal}\n"
        yield f"[*] Device: {state.device}\n"
        
        # Decompose
        intent = "search_interactive" # Default
        user_type = "Standard User"
        try:
            task = state.decomposer.decompose(intent, user_type, req.goal)
            yield f"[*] Task decomposed into {len(task.actions)} steps.\n"
        except Exception as e:
            yield f"[!] Decomposition error: {redact_sensitive_text(str(e))}\n"
            return

        # Execute
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            # We run headful so the user can "watch" as requested
            browser = await pw.chromium.launch(headless=False)
            page = await browser.new_page()
            executor = ActionExecutor(page=page, model=state.policy)
            
            yield "[*] Browser launched (headful mode).\n"
            
            # Helper to capture logs from executor
            # In a quick GUI, we'll manually yield key steps
            for i, action in enumerate(task.actions):
                yield f"--- Step {i+1}: {action.action_type.value} ---\n"
                yield f"Thinking: Targeting {redact_sensitive_text(action.target)}...\n"
                
                try:
                    res = await executor.execute_atomic_action(action, goal=req.goal)
                    if res.success:
                        yield f"Success: {action.action_type.value} completed.\n"
                    else:
                        yield f"Warning: {redact_sensitive_text(res.error or 'Action failed')}\n"
                except Exception as e:
                    yield f"Error: {redact_sensitive_text(str(e))}\n"
                    break
            
            yield "[*] Task execution finished.\n"
            await asyncio.sleep(5) # Let user see final state
            await browser.close()

    return StreamingResponse(log_stream(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
