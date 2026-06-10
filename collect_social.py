"""
BrowserMind -- collect_social.py
==================================
Autonomous large-scale data collection specifically targeted at Social Media platforms
for the Social Media Mastery Initiative.
Focuses on Facebook, Instagram, X, LinkedIn, Reddit, YouTube, TikTok, Pinterest, Snapchat, and Threads.
"""

import argparse
import asyncio
import json
import os
import random
import time
from pathlib import Path

# We reuse most of the robust infrastructure from collect_massive
from collect_massive import (
    SessionRecorder, _is_blocked, _execute_action, balanced_url_sample, _log,
    _augment_collected_sessions, _get_or_create_session_split, _samples_meet_success_criteria
)

from training.graph_builder import prune_graph, build_graph_from_page, decide_expert_action, graph_hash
from core.privacy import (
    redact_sensitive_text, sanitize_expert_action, sanitize_goal_for_storage, sanitize_graph_for_storage
)

from collections import deque
import torch

BASE_DIR       = Path(__file__).parent
SESSIONS_DIR   = BASE_DIR / "training" / "social_sessions"
LOG_FILE       = BASE_DIR / "collect_social.log"
STATE_FILE     = BASE_DIR / "social_state.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

SOCIAL_URLS = [
    "https://www.facebook.com",
    "https://www.instagram.com",
    "https://x.com",
    "https://www.linkedin.com",
    "https://www.reddit.com",
    "https://www.youtube.com",
    "https://www.tiktok.com",
    "https://www.pinterest.com",
    "https://www.snapchat.com",
    "https://www.threads.net"
]

TOPICS = ["AI news", "Machine learning", "Python coding", "Startups", "Tech memes"]
SOCIAL_GOALS = [
    "login to account",
    "search for {topic}",
    "like the top post about {topic}",
    "go to notifications",
    "reply to a comment",
    "share this post",
    "bookmark the best post on feed",
    "follow a creator for {topic}",
    "navigate to my profile",
    "open direct messages",
    "open reels or short videos tab",
    "open stories and view first story",
    "open groups or communities",
    "join a relevant group",
    "open a trending hashtag page",
    "save a post for later",
    "open a creator channel and inspect latest upload",
    "open account settings",
    "switch feed sorting to latest",
    "start a post draft",
    "open comments and sort by newest",
    "find and open a live stream",
    "open marketplace or monetization section",
    "report spam content",
    "mute a noisy conversation",
    "inspect privacy settings",
    "open creator analytics",
    "follow and then unfollow a random public account"
]

def generate_social_goals(n: int = 5) -> list[str]:
    goals = []
    for _ in range(n):
        template = random.choice(SOCIAL_GOALS)
        if "{topic}" in template:
            template = template.replace("{topic}", random.choice(TOPICS))
        goals.append(template)
    return goals


def generate_diverse_social_goals(n: int) -> list[str]:
    """Return goals with broad action coverage before repeating patterns."""
    if n <= 0:
        return []
    templates = SOCIAL_GOALS[:]
    random.shuffle(templates)
    out: list[str] = []
    idx = 0
    while len(out) < n:
        template = templates[idx % len(templates)]
        idx += 1
        if "{topic}" in template:
            template = template.replace("{topic}", random.choice(TOPICS))
        out.append(template)
    return out

async def run_social_session(page, goal: str, start_url: str, sid: str, save_dir: Path, policy=None):
    """Execution logic adapted for dynamic social feeds."""
    recorder = SessionRecorder(goal=goal, save_dir=save_dir)
    hash_history = deque(maxlen=3)
    
    try:
        await page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
    except: return None
    
    if await _is_blocked(page): return None
    
    prev_url = page.url
    for step in range(20): # Increased steps for deeper social interactions!
        try:
            graph = await build_graph_from_page(page)
            nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
            graph["nodes"], graph["edges"] = nodes, edges
            if not nodes: break
        except: break

        gh = graph_hash(graph)
        hash_history.append(gh)
        if len(hash_history) == 3 and len(set(hash_history)) == 1: break # stuck

        # Decide action (Using our robust heuristic DecisionEngine inside decide_expert_action)
        expert = decide_expert_action(graph, goal, page.url)
        expert_for_record = dict(expert)
        eidx = expert_for_record.get("element_idx")
        if isinstance(eidx, int) and 0 <= eidx < len(nodes):
            expert_for_record.setdefault("target_text", str(nodes[eidx].get("name", "")))
        
        screenshot_name = f"step_{step+1:03d}.png"
        try:
            await page.screenshot(path=save_dir / screenshot_name, scale="css")
        except: screenshot_name = ""

        # Check Domain Boundary (Strict Constraint)
        base_domain = start_url.split("//")[-1].split("/")[0].replace("www.", "")
        current_domain = page.url.split("//")[-1].split("/")[0].replace("www.", "")
        if base_domain not in current_domain and "oauth" not in current_domain:
            # Violated boundary, terminate
            break

        action_success = await _execute_action(page, expert, nodes)
        recorder.record(graph, expert_for_record, prev_url, step + 1, action_success, screenshot_name)
        prev_url = page.url
        if expert.get("type") in ("done", "fail"): break
        await asyncio.sleep(1.0) # slightly longer wait for social SPA hydration

    return recorder.save(sid) if recorder.is_trainable() else None

async def collect_parallel_social(tasks_queue, n_parallel, blocked_urls, policy=None):
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(n_parallel)
    results = []
    lock = asyncio.Lock()
    async def run_one(goal, url, sid, save_dir):
        async with sem:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
                page = await context.new_page()
                try:
                    path = await asyncio.wait_for(
                        run_social_session(page, goal, url, sid, save_dir, policy), 
                        timeout=900
                    )
                    if path:
                        async with lock: results.append(path)
                        _log(f"  [ok] {goal!r:.30} {Path(path).name}")
                    else:
                        blocked_urls[url] = blocked_urls.get(url, 0) + 1
                except:
                    blocked_urls[url] = blocked_urls.get(url, 0) + 1
                finally:
                    await browser.close()
            
    await asyncio.gather(*[run_one(g, u, s, d) for g, u, s, d in tasks_queue])
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--tasks-per-round", type=int, default=24)
    parser.add_argument("--inline-train", action="store_true", help="also run lightweight inline BC inside collector")
    args = parser.parse_args()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    from model.agent_policy import AgentPolicy
    policy = AgentPolicy().to(device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=2e-5) # Fine-tune LR
    
    state = {"round": 0, "blocked_urls": {}, "all_session_files": []}
    
    for r in range(args.rounds):
        state["round"] += 1
        _log(f"--- Social Round {state['round']} ---")
        round_dir = SESSIONS_DIR / f"round_{state['round']:04d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        
        # Build tasks with explicit goal diversity to cover more social action types.
        tasks = []
        diverse_goals = generate_diverse_social_goals(args.tasks_per_round)
        for i, goal in enumerate(diverse_goals):
            url = random.choice(SOCIAL_URLS)
            tasks.append((goal, url, f"S_{state['round']}_{i}", round_dir))
            
        new_paths = asyncio.run(collect_parallel_social(tasks, args.parallel, state["blocked_urls"]))
        state["all_session_files"].extend(new_paths)
        _augment_collected_sessions(new_paths, round_dir, multiplier=2)
        
        # Optional inline training: default off because deep orchestration usually handles full BC externally.
        if args.inline_train and state["all_session_files"]:
            from collect_massive import _train_epochs

            _train_epochs(policy, state["all_session_files"], optimizer, device, n_epochs=2)

if __name__ == "__main__":
    main()
