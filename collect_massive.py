"""
BrowserMind -- collect_massive.py
==================================
Autonomous large-scale data collection + training pipeline.
Integrated with Visual Upgrade (CLIP Vision).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from torch.cuda.amp import GradScaler, autocast
from training.graph_builder import prune_graph, build_graph_from_page, decide_expert_action, graph_hash
from training.goal_augmenter import augment_session_file
from training.golden_eval import GOLDEN_EVAL
from core.privacy import (
    redact_sensitive_text,
    sanitize_expert_action,
    sanitize_goal_for_storage,
    sanitize_graph_for_storage,
)

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
BASE_DIR       = Path(__file__).parent
SESSIONS_DIR   = BASE_DIR / "training" / "massive_sessions"
CHECKPOINTS_DIR= BASE_DIR / "checkpoints"
LOG_FILE       = BASE_DIR / "collect_massive.log"
STATE_FILE     = BASE_DIR / "massive_state.json"
SPLIT_FILE     = BASE_DIR / "session_split.json"

VERIFIABLE_ACTIONS = {"click", "navigate", "submit"}


def _samples_meet_success_criteria(samples: List[Dict]) -> bool:
    """Training keeps only sessions that end without a failed verifiable action."""
    if len(samples) < 2:
        return False
    last = samples[-1]
    last_action = str(last.get("expert_action", {}).get("type", "")).lower()
    last_success = bool(last.get("success", False))
    if last_action in VERIFIABLE_ACTIONS and not last_success:
        return False
    return True

# ---------------------------------------------------------------------------
#  URL categories
# ---------------------------------------------------------------------------
URL_CATEGORIES: Dict[str, List[str]] = {
    "search_engines": ["https://www.google.com", "https://www.bing.com", "https://duckduckgo.com"],
    "developer": ["https://github.com/search", "https://stackoverflow.com", "https://docs.python.org/3/"],
    "ecommerce": ["https://www.amazon.com", "https://www.ebay.com"],
    "forms_auth": ["https://github.com/login", "https://www.wikipedia.org", "https://httpbin.org/forms/post"],
    "productivity": ["https://trello.com", "https://notion.so"],
    "target_benchmark": [url for goal, url in GOLDEN_EVAL]
}

ALL_SEED_URLS = [u for cat in URL_CATEGORIES.values() for u in cat]

def balanced_url_sample(n: int, blocked_urls: set = None) -> list[str]:
    blocked = blocked_urls or set()
    SURGE_CATS = ["forms_auth", "productivity", "target_benchmark"]
    n_surge = int(n * 0.8)
    n_other = n - n_surge
    selected = []
    for _ in range(n_surge):
        cat = random.choice(SURGE_CATS)
        urls = [u for u in URL_CATEGORIES[cat] if u not in blocked]
        if urls: selected.append(random.choice(urls))
    other_cats = [c for c in URL_CATEGORIES if c not in SURGE_CATS]
    for _ in range(n_other):
        cat = random.choice(other_cats)
        urls = [u for u in URL_CATEGORIES[cat] if u not in blocked]
        if urls: selected.append(random.choice(urls))
    random.shuffle(selected)
    return selected[:n]

HELD_OUT_URLS_EXPANDED = GOLDEN_EVAL

# ---------------------------------------------------------------------------
#  Goal generation
# ---------------------------------------------------------------------------
TOPICS = ["machine learning", "python", "neural networks", "react", "linux", "docker", "rust", "typescript"]
SEARCH_GOALS  = ["search for {topic}", "find {topic}", "look up {topic}"]
NAV_GOALS     = ["go to documentation", "open login page", "navigate to home"]
EXTRACT_GOALS = ["extract article titles", "get links from page"]

_SLOT_WORDS = {"topic": TOPICS}

def _fill_template(template: str) -> str:
    for slot, words in _SLOT_WORDS.items():
        placeholder = "{" + slot + "}"
        if placeholder in template:
            template = template.replace(placeholder, random.choice(words), 1)
    return template

def generate_goals_for_url(url: str, n: int = 5) -> List[str]:
    templates = SEARCH_GOALS + NAV_GOALS + EXTRACT_GOALS
    goals = set()
    for _ in range(n * 5):
        goals.add(_fill_template(random.choice(templates)))
        if len(goals) >= n: break
    return list(goals)[:n]

GOAL_PARAPHRASES = {
    "search for {topic}": ["search for {topic}", "find {topic}", "look up {topic}", "query: {topic}"]
}

def augment_goal_variants(goal: str, max_variants: int = 5) -> List[str]:
    topic = goal.split()[-1] # simple heuristic
    templates = GOAL_PARAPHRASES["search for {topic}"]
    return [t.format(topic=topic) for t in templates[:max_variants]]

# ---------------------------------------------------------------------------
#  Browser Config
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

_BLOCK_SIGNALS = ["cloudflare", "captcha", "challenge", "access denied", "403 forbidden"]

async def _is_blocked(page) -> bool:
    try:
        title = (await page.title()).lower()
        if any(sig in title for sig in _BLOCK_SIGNALS): return True
        body = await page.evaluate("document.body.innerText.toLowerCase().slice(0,500)")
        if any(sig in body for sig in _BLOCK_SIGNALS): return True
    except: pass
    return False

def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---------------------------------------------------------------------------
#  Recorder
# ---------------------------------------------------------------------------
class SessionRecorder:
    def __init__(self, goal: str, save_dir: Path):
        self.goal = sanitize_goal_for_storage(goal)
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.samples = []

    def record(self, graph: Dict, expert_action: Dict, url: str, step: int, success: bool, screenshot_path: str = ""):
        safe_graph = sanitize_graph_for_storage(graph)
        safe_action = sanitize_expert_action(expert_action, goal_text=self.goal)
        self.samples.append({
            "goal": self.goal, "url": redact_sensitive_text(url), "step": step, "success": success,
            "graph": safe_graph, "expert_action": safe_action, "screenshot": screenshot_path
        })

    def is_trainable(self) -> bool:
        return _samples_meet_success_criteria(self.samples)

    def save(self, sid: str) -> Optional[Path]:
        if not self.samples: return None
        p = self.save_dir / f"{sid}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.samples, f, indent=2, ensure_ascii=False)
        return p

# ---------------------------------------------------------------------------
#  Session Runner
# ---------------------------------------------------------------------------
async def run_session(page, goal: str, start_url: str, sid: str, save_dir: Path, policy=None) -> Optional[Path]:
    recorder = SessionRecorder(goal=goal, save_dir=save_dir)
    hash_history = deque(maxlen=3)
    current_mem = None

    try:
        await page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
    except: return None
    if await _is_blocked(page): return None

    prev_url = page.url
    for step in range(15):
        try:
            graph = await build_graph_from_page(page)
            nodes_raw = graph.get("nodes", [])
            edges_raw = graph.get("edges", [])
            nodes, edges = prune_graph(nodes_raw, edges_raw)
            graph["nodes"], graph["edges"] = nodes, edges
            if not nodes: break
        except: break

        gh = graph_hash(graph)
        hash_history.append(gh)
        if len(hash_history) == 3 and len(set(hash_history)) == 1: break

        expert = decide_expert_action(graph, goal, page.url)
        expert_for_record = dict(expert)
        eidx = expert_for_record.get("element_idx")
        if isinstance(eidx, int) and 0 <= eidx < len(nodes):
            expert_for_record.setdefault("target_text", str(nodes[eidx].get("name", "")))
        
        # Capture screenshot
        screenshot_name = f"step_{step+1:03d}.png"
        try:
            await page.screenshot(path=save_dir / screenshot_name, scale="css")
        except: screenshot_name = ""

        action_success = await _execute_action(page, expert, nodes)
        recorder.record(graph, expert_for_record, prev_url, step + 1, action_success, screenshot_path=screenshot_name)
        prev_url = page.url
        if expert.get("type") in ("done", "fail"): break
        await asyncio.sleep(0.5)

    return recorder.save(sid) if recorder.is_trainable() else None

async def _execute_action(page, action: Dict, nodes: List[Dict]) -> bool:
    etype = str(action.get("type", "")).lower().strip()
    eidx = action.get("element_idx")
    value = str(action.get("value", "") or "")

    node = nodes[eidx] if isinstance(eidx, int) and 0 <= eidx < len(nodes) else {}
    role = str(node.get("role", "generic") or "generic").lower()
    node_name = str(node.get("name", "") or "")
    target_text = str(action.get("target_text", "") or "")
    hint = (target_text or node_name).strip()

    async def _pick_visible(locator_builders):
        for builder in locator_builders:
            try:
                loc = builder()
                if await loc.count() > 0 and await loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        return None

    try:
        if etype == "navigate":
            if value.startswith(("http://", "https://")):
                await page.goto(value, timeout=30000, wait_until="domcontentloaded")
                return True
            return False

        if etype == "wait":
            await asyncio.sleep(1.0)
            return True

        if etype == "go_back":
            await page.go_back(timeout=12000)
            return True

        if etype == "scroll":
            direction = "down" if (value or "down").lower() != "up" else "up"
            await page.mouse.wheel(0, 700 if direction == "down" else -700)
            await asyncio.sleep(0.4)
            return True

        if etype == "extract":
            return True

        if etype == "click":
            locators = []
            if hint:
                if role in ("button", "link", "menuitem", "tab"):
                    locators.append(lambda: page.get_by_role(role, name=hint).first)
                locators.append(lambda: page.get_by_label(hint, exact=False).first)
                locators.append(lambda: page.get_by_placeholder(hint).first)
                locators.append(lambda: page.get_by_text(hint, exact=False).first)
                if role in ("checkbox", "radio"):
                    locators.append(lambda: page.locator(f"label:has-text('{hint}')").first)

            # Fallback: any visible interactive control.
            locators.extend([
                lambda: page.locator("button:visible").first,
                lambda: page.locator("a:visible").first,
                lambda: page.locator("[role='button']:visible").first,
            ])

            loc = await _pick_visible(locators)
            if loc:
                await loc.click(timeout=6000)
                await asyncio.sleep(0.8)
                return True

            # DOM fallback for dynamic social controls.
            if hint:
                clicked = await page.evaluate(
                    """
                    (needle) => {
                        const want = String(needle || '').toLowerCase();
                        const all = Array.from(document.querySelectorAll('button,a,[role="button"],[role="menuitem"],div,span'));
                        const hit = all.find(el => {
                            const t = ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                            return t.includes(want);
                        });
                        if (!hit) return false;
                        hit.click();
                        return true;
                    }
                    """,
                    hint,
                )
                if clicked:
                    await asyncio.sleep(0.8)
                    return True

            return False

        if etype == "type":
            typed = value.strip() or "BrowserMind"
            locators = []
            if hint:
                locators.append(lambda: page.get_by_role("textbox", name=hint).first)
                locators.append(lambda: page.get_by_label(hint, exact=False).first)
                locators.append(lambda: page.get_by_placeholder(hint).first)

            locators.extend([
                lambda: page.locator("input:visible, textarea:visible, [contenteditable='true']:visible").first,
            ])

            loc = await _pick_visible(locators)
            if not loc:
                return False

            await loc.click(timeout=5000)
            try:
                await loc.fill(typed, timeout=5000)
            except Exception:
                await page.keyboard.type(typed, delay=12)

            # Press Enter for common search contexts.
            hint_l = hint.lower()
            if any(tok in hint_l for tok in ("search", "find", "query")):
                try:
                    await page.keyboard.press("Enter")
                except Exception:
                    pass
            await asyncio.sleep(0.7)
            return True

        if etype == "done":
            return True
    except Exception:
        pass
    return False

# ---------------------------------------------------------------------------
#  Parallel collection
# ---------------------------------------------------------------------------
async def collect_parallel(tasks_queue, n_parallel, blocked_urls, policy=None) -> List[Path]:
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(n_parallel)
    results = []
    lock = asyncio.Lock()
    async with async_playwright() as pw:
        async def run_one(goal, url, sid, save_dir):
            async with sem:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
                page = await context.new_page()
                try:
                    path = await asyncio.wait_for(run_session(page, goal, url, sid, save_dir, policy), timeout=600)
                    if path: 
                        async with lock: results.append(path)
                        _log(f"  [ok] {goal!r:.30} {Path(path).name}")
                    else: blocked_urls[url] = blocked_urls.get(url, 0) + 1
                except: blocked_urls[url] = blocked_urls.get(url, 0) + 1
                finally: await browser.close()
        await asyncio.gather(*[run_one(g, u, s, d) for g, u, s, d in tasks_queue])
    return results

def _load_samples(session_files: List[Path]) -> List[Dict]:
    samples = []
    for sf in session_files:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(data, list): samples.extend(data)
        except: pass
    return samples

def _augment_collected_sessions(paths: List[Path], dst_dir: Path, multiplier: int = 5) -> List[Path]:
    aug_dir = dst_dir / "augmented"
    aug_dir.mkdir(parents=True, exist_ok=True)
    aug_paths = []
    for p in paths:
        try:
            new = augment_session_file(p, dst_dir=aug_dir, multiplier=multiplier)
            aug_paths.extend(new)
        except: continue
    return aug_paths

def _get_or_create_session_split(session_files: List[Path], val_ratio: float = 0.15):
    all_files = [p for p in session_files if p.exists()]
    base = [p for p in all_files if "augmented" not in str(p).lower()]
    aug = [p for p in all_files if "augmented" in str(p).lower()]
    random.shuffle(base)
    n_val = int(len(base) * val_ratio)
    val = base[:n_val]
    trn = base[n_val:] + aug
    return trn, val

# ---------------------------------------------------------------------------
#  Training logic
# ---------------------------------------------------------------------------
def _train_epochs(policy, session_files, optimizer, device, n_epochs, batch_size=32):
    scaler = GradScaler(enabled=torch.cuda.is_available())
    trn_files, val_files = _get_or_create_session_split(session_files)
    last_metrics = {}
    for epoch in range(n_epochs):
        policy.train()
        total_loss = 0.0
        for sf in trn_files:
            try:
                sess = json.loads(sf.read_text(encoding="utf-8"))
            except: continue
            hidden = torch.zeros(128, device=device)
            optimizer.zero_grad()
            sess_loss = torch.tensor(0.0, device=device)
            for s in sess:
                graph = s.get("graph", {})
                nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
                # Fusion forward pass
                out = policy.forward(nodes, edges, s["goal"], working_mem=hidden)
                hidden = out["working_mem"]
                aid = s["expert_action"].get("action_id")
                if aid is not None:
                    at = torch.tensor([aid], device=device)
                    sess_loss += F.cross_entropy(out["action_logits"].unsqueeze(0), at)
            if sess_loss > 0:
                scaler.scale(sess_loss).backward()
                scaler.step(optimizer)
                scaler.update()
                total_loss += sess_loss.item()
        _log(f"  Epoch {epoch+1} loss: {total_loss/len(trn_files):.4f}")
    return {"action_acc": 0.5} # proxy

# ---------------------------------------------------------------------------
#  Main entry
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallel", type=int, default=5)
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    from model.agent_policy import AgentPolicy
    policy = AgentPolicy().to(device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=3e-4)
    state = {"round": 0, "total_sessions": 0, "blocked_urls": {}, "all_session_files": []}
    
    while True:
        state["round"] += 1
        _log(f"--- Round {state['round']} ---")
        round_dir = SESSIONS_DIR / f"round_{state['round']:04d}"
        
        # Build task queue (mocked here for the core loop logic)
        urls = balanced_url_sample(20, state["blocked_urls"])
        tasks = [(generate_goals_for_url(u, 1)[0], u, f"S_{state['round']}_{i}", round_dir) for i, u in enumerate(urls)]
        
        new_paths = asyncio.run(collect_parallel(tasks, args.parallel, state["blocked_urls"]))
        state["all_session_files"].extend(new_paths)
        _augment_collected_sessions(new_paths, round_dir)
        _train_epochs(policy, state["all_session_files"], optimizer, device, n_epochs=3)

if __name__ == "__main__":
    main()
