"""
BrowserMind  Evaluation Script (Unified)
==================================
Computes all metrics defined in spec Section 8 using the unified ActionExecutor.

  action_accuracy  : % steps where argmax(action_logits) == expert_action_id
  element_acc@1    : % where top-1 element == expert_element_idx
  element_acc@3    : % where expert_element_idx in top-3 by score
  task_success     : % of full tasks completed (end-to-end rollout)
  avg_steps        : mean steps to completion

Usage:
  # Offline eval on val split
  python evaluate.py --ckpt checkpoints/best.pt --data training/massive_sessions

  # Full end-to-end rollout eval (needs browser)
  python evaluate.py --ckpt checkpoints/best.pt --live --tasks 20
"""

from __future__ import annotations

import argparse
import asyncio
import math
import time
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F

from model.agent_policy import AgentPolicy, ACTION_TYPES
from training.graph_dataset import GraphDataset, GraphSample


# ------------------------------------------------------------------------------
#  Offline eval (no browser needed)
# ------------------------------------------------------------------------------

@torch.no_grad()
def offline_eval(
    policy:  AgentPolicy,
    dataset: GraphDataset,
    device:  torch.device,
) -> Dict[str, float]:
    """
    Evaluates policy on all samples in dataset.
    Returns metric dict.
    """
    policy.eval()

    n_action_total   = 0
    n_action_correct = 0

    n_elem_total  = 0
    n_elem_acc1   = 0
    n_elem_acc3   = 0

    per_action: Dict[int, Dict[str, int]] = {
        i: {"total": 0, "correct": 0} for i in range(len(ACTION_TYPES))
    }

    for sample in dataset.samples:
        out = policy.forward(sample.nodes, sample.edges, sample.goal)

        # Action accuracy
        pred_action = int(out["action_logits"].argmax().item())
        correct     = (pred_action == sample.action_id)
        n_action_total   += 1
        n_action_correct += int(correct)
        per_action[sample.action_id]["total"]   += 1
        per_action[sample.action_id]["correct"] += int(correct)

        # Element accuracy
        if sample.element_idx is not None:
            n = out["element_scores"].shape[0]
            if sample.element_idx < n and n > 0:
                k      = min(3, n)
                top3   = torch.topk(out["element_scores"], k).indices.tolist()
                top1   = top3[0] if top3 else -1
                n_elem_total += 1
                n_elem_acc1  += int(top1 == sample.element_idx)
                n_elem_acc3  += int(sample.element_idx in top3)

    return {
        "action_accuracy": n_action_correct / max(n_action_total, 1),
        "element_acc@1":   n_elem_acc1 / max(n_elem_total, 1),
        "element_acc@3":   n_elem_acc3 / max(n_elem_total, 1),
        "n_samples":       n_action_total,
        "n_elem_samples":  n_elem_total,
        "per_action":      {
            ACTION_TYPES[k]: {
                "total":   v["total"],
                "correct": v["correct"],
                "acc":     v["correct"] / max(v["total"], 1),
            }
            for k, v in per_action.items() if v["total"] > 0
        },
    }


# ------------------------------------------------------------------------------
#  Live rollout eval (needs browser)
# ------------------------------------------------------------------------------

async def _live_rollout(
    policy:    AgentPolicy,
    goal:      str,
    start_url: str,
    device:    torch.device,
    max_steps: int = 15,
) -> Dict:
    """Run one task rollout using unified ActionExecutor."""
    from playwright.async_api import async_playwright
    from core.validator import Validator
    from core.executor import ActionExecutor
    from training.graph_builder import build_graph_from_page, prune_graph

    validator = Validator()

    async with async_playwright() as pw:
        # Launch with production-like settings
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page    = await context.new_page()
        
        executor = ActionExecutor(policy_v2=policy, page=page)
        
        if hasattr(policy, "reset_task"):
            policy.reset_task(goal)

        try:
            await page.goto(start_url, timeout=15000, wait_until="domcontentloaded")
        except Exception:
            await browser.close()
            return {"success": False, "n_steps": 0}

        url_before = page.url

        for step in range(max_steps):
            try:
                # 1. Observe
                graph = await build_graph_from_page(page)
                nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
                
                if len(nodes) < 2: break

                # 2. Decide
                pred = policy.predict(nodes, edges, goal)
                target_node = nodes[pred["element_idx"]] if pred["element_idx"] is not None else {}
                target_name = target_node.get("name", "")
                print(f"      [Step {step+1}] {pred['action_type']} -> {target_name[:30]}")
                
                if pred["action_type"] in ("done", "fail"):
                    success = (pred["action_type"] == "done")
                    val_res = await validator.check(page, goal, url_before)
                    await browser.close()
                    return {"success": success or val_res.success, "n_steps": step + 1}

                # 3. Execute (Unified ActionExecutor with resilient typing/clicks)
                target_node = nodes[pred["element_idx"]] if pred["element_idx"] is not None else {}
                
                # Heuristic value provider for rollouts
                val = ""
                if pred["action_type"] == "type":
                    gl = goal.lower()
                    if "email" in gl: val = "test@example.com"
                    elif "search" in gl or "find" in gl:
                        # Extract query if possible from goal
                        match = re.search(r"search for (.*)", goal, re.I)
                        val = match.group(1) if match else "machine learning"
                    elif "name" in gl: val = "John Doe"
                    elif "password" in gl: val = "Password123!"
                    else: val = "Standard Input"

                action_dict = {
                    "type": pred["action_type"],
                    "element_idx": pred["element_idx"],
                    "target": target_node.get("name", ""),
                    "value": val
                }
                
                await executor.execute_atomic_action(action_dict, goal=goal, nodes=nodes)
                
                # 4. Success Check
                val_result = await validator.check(page, goal, url_before)
                if val_result.success:
                    await browser.close()
                    return {"success": True, "n_steps": step + 1}

                url_before = page.url
                await asyncio.sleep(0.5)

            except Exception:
                break

        await browser.close()
        return {"success": False, "n_steps": max_steps}


async def live_eval(
    policy:    AgentPolicy,
    tasks:     List[Tuple[str, str]],
    device:    torch.device,
    max_steps: int = 15,
) -> Dict:
    """Run live rollout evaluation on requested tasks."""
    policy.eval()
    results = []

    for i, (goal, start_url) in enumerate(tasks):
        print(f"  [{i+1:>2}/{len(tasks)}] {goal[:55]}", end=" ... ", flush=True)
        try:
            r = await _live_rollout(policy, goal, start_url, device, max_steps)
        except Exception as e:
            r = {"success": False, "n_steps": 0}
            print(f"[!] {e}", end="")

        results.append(r)
        status = "[OK]" if r["success"] else "[X]"
        print(f"{status} ({r['n_steps']} steps)")

    n_success  = sum(1 for r in results if r["success"])
    return {
        "task_success": n_success / max(len(results), 1),
        "avg_steps":    sum(r["n_steps"] for r in results if r["success"]) / max(n_success, 1),
        "n_tasks":      len(results),
        "n_success":    n_success,
    }


# ------------------------------------------------------------------------------
#  Main
# ------------------------------------------------------------------------------

def main(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}\n  BrowserMind  Evaluation (Unified)\n{'='*60}")
    
    ckpt_path = Path(args.ckpt)
    if not ckpt_path.exists():
        print(f"[!] Checkpoint not found: {ckpt_path}")
        return

    policy = AgentPolicy.load(str(ckpt_path), map_location=str(device)).to(device)
    
    metrics = {}

    # -- Offline --
    if Path(args.data).exists():
        ds = GraphDataset(args.data, split=args.split, val_ratio=0.2)
        if len(ds) > 0:
            off = offline_eval(policy, ds, device)
            metrics.update(off)
            print(f"  Offline | Samples: {off['n_samples']} | Action Acc: {off['action_accuracy']:.4f}")

    # -- Live --
    if args.live:
        from training.dagger_tasks import DAGGER_TASKS
        live_tasks = DAGGER_TASKS
        
        if args.short:
            # Filter to core sites only for fast feedback in the Autoscale loop
            core_patterns = ["github.com", "pypi.org", "arxiv.org", "google.com", "wikipedia.org"]
            live_tasks = [t for t in DAGGER_TASKS if any(p in t[1] for p in core_patterns)]
            print(f"[INIT] Short-path eval: 5 core tasks selected.")
        
        rng = random.Random(args.seed)
        task_sample = rng.sample(live_tasks, min(len(live_tasks), args.tasks if not args.short else 5))
        
        live = asyncio.run(live_eval(policy, task_sample, device, max_steps=args.max_steps))
        metrics.update(live)
        print(f"  Live    | Tasks: {live['n_tasks']} | Success: {live['task_success']:.4f} | Avg Steps: {live['avg_steps']:.1f}")

    print(f"\n{'='*60}\n")
    return metrics

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt",      default="checkpoints/best.pt")
    p.add_argument("--data",      default="training/massive_sessions")
    p.add_argument("--split",     default="val")
    p.add_argument("--live",      action="store_true")
    p.add_argument("--tasks",     type=int, default=10)
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--seed",      type=int, default=42)
    p.add_argument("--short",     action="store_true", help="Run only 5 core sites for fast feedback")
    return p.parse_args()

if __name__ == "__main__":
    main(parse_args())
