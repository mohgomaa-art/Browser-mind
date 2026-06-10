"""
BrowserMind  Phase 2: DAgger
================================
Interactive imitation learning that fixes distribution shift.

Algorithm (Section 4):
  beta = 1.0  (starts full expert control)
  D    = Phase1_data

  for iteration in range(20):
    # Rollout: use expert if rand < beta, else use policy
    # Always label with expert action
    for task in task_set:
      reset browser
      for step in range(15):
        observe -> build graph
        expert_action = DecisionEngine.decide(graph, goal)
        if rand < beta: execute expert_action
        else:           execute policy.predict(...)
        D.append({graph, goal, expert_action})

    # Train one epoch on D
    train_one_epoch(policy, D, lr=1e-4, batch_size=32)
    beta = max(0.0, beta - 0.05)

Expert: DecisionEngine (heuristic scorer, NO LLM)
  Uses ConstraintFilter.apply() + ElementScorer.rank()

Prerequisites:
  - Phase 1 checkpoint must exist (--ckpt)
  - Playwright must be installed: pip install playwright && playwright install chromium
  - DAgger task set in training/dagger_tasks.py

Usage:
  python train_dagger.py --ckpt browsermind_policy_v2.pt
  python train_dagger.py --ckpt browsermind_policy_v2.pt --iterations 10 --max-steps 15
"""

from __future__ import annotations

from browsermind_core.training.freeze_legacy import check_legacy_trainer_call
check_legacy_trainer_call(__file__)


import argparse
import asyncio
import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F

from model.agent_policy import AgentPolicy, ACTION_TYPES, ROLE_TO_ID, UNKNOWN_ROLE_ID
from training.graph_dataset import GraphSample
from training.dagger_tasks import DAGGER_TASKS


# ------------------------------------------------------------------------------
#  Accessibility snapshot -> spec graph
# ------------------------------------------------------------------------------

def _snapshot_to_graph(snapshot: Dict) -> Tuple[List[Dict], List[List]]:
    """
    Convert Playwright accessibility snapshot to spec graph format.
    snapshot: result of page.accessibility.snapshot()
    """
    nodes = []
    edges = []
    _walk_node(snapshot or {}, nodes, edges, depth=0, parent_idx=None)
    # Truncate to 80 (bottom = deepest nodes are last -> slice from end)
    if len(nodes) > 80:
        kept = set(range(80))
        nodes = nodes[:80]
        edges = [e for e in edges if e[0] in kept and e[1] in kept]
    return nodes, edges


def _walk_node(
    node:       Dict,
    nodes:      List[Dict],
    edges:      List,
    depth:      int,
    parent_idx: Optional[int],
):
    """DFS over accessibility tree, building node/edge lists."""
    if not node:
        return

    idx = len(nodes)
    role = str(node.get("role", "generic")).lower()
    name = str(node.get("name", "") or "")
    value = str(node.get("value", "") or "")

    nodes.append({
        "idx":     idx,
        "role":    role,
        "name":    name[:120],
        "value":   value[:80],
        "focused": bool(node.get("focused", False)),
        "depth":   min(depth, 19),
    })

    if parent_idx is not None:
        edges.append([parent_idx, idx, "parent_child"])

    children = node.get("children", []) or []
    prev_child_idx = None
    for child in children:
        child_idx_before = len(nodes)
        _walk_node(child, nodes, edges, depth + 1, idx)
        child_idx_after = len(nodes)
        if child_idx_after > child_idx_before:
            actual_child_idx = child_idx_before
            if prev_child_idx is not None:
                edges.append([prev_child_idx, actual_child_idx, "sibling"])
            prev_child_idx = actual_child_idx


# ------------------------------------------------------------------------------
#  Expert decision via DecisionEngine heuristic
# ------------------------------------------------------------------------------

def _expert_decide(goal: str, nodes: List[Dict], edges: List) -> Dict:
    """
    Heuristic expert using ConstraintFilter + ElementScorer.
    Returns spec-format expert_action dict: {action_id, element_idx}
    """
    from core.decision_engine import ConstraintFilter, ElementScorer

    # Convert spec nodes -> old format for the existing scorer
    old_elements = []
    for nd in nodes:
        old_elements.append({
            "tag":        _role_to_tag(nd.get("role", "generic")),
            "role":       nd.get("role", "generic"),
            "text":       nd.get("name", ""),
            "placeholder": "",
            "x":          100,   # scorer doesn't need real coords here
            "y":          200 + nd.get("depth", 0) * 30,
            "w":          200,
            "h":          40,
            "clickable":  nd.get("role", "") in ("button", "link", "menuitem"),
            "visible":    True,
        })

    # Determine the most likely action type from goal keywords
    goal_l = goal.lower()
    if any(w in goal_l for w in ["type", "enter", "fill", "input", "write"]):
        action_type = "type"
        action_id   = 2
    elif any(w in goal_l for w in ["click", "press", "submit", "sign", "log", "go"]):
        action_type = "click"
        action_id   = 1
    elif any(w in goal_l for w in ["navigate", "open", "visit", "go to"]):
        action_type = "navigate"
        action_id   = 0
    elif any(w in goal_l for w in ["scroll"]):
        action_type = "scroll"
        action_id   = 3
    elif any(w in goal_l for w in ["extract", "read", "get", "find"]):
        action_type = "extract"
        action_id   = 5
    else:
        action_type = "click"
        action_id   = 1

    filtered    = ConstraintFilter.apply(old_elements, action_type)
    if not filtered:
        filtered = old_elements

    candidates  = ElementScorer.rank(filtered, goal, goal=goal, top_k=3)
    best_old_idx = candidates[0].index if candidates else 0

    # Map back to spec node idx (filtered -> original -> spec idx mapping)
    # Since old_elements is 1:1 with nodes (same order), best_old_idx is the spec idx
    element_idx  = best_old_idx if best_old_idx < len(nodes) else None

    return {
        "type":       action_type,
        "action_id":  action_id,
        "element_idx": element_idx,
    }


def _role_to_tag(role: str) -> str:
    _map = {
        "button": "button", "link": "a", "textbox": "input",
        "combobox": "select", "checkbox": "input", "radio": "input",
        "heading": "h2", "img": "img", "navigation": "nav",
        "main": "main", "dialog": "dialog",
    }
    return _map.get(role, "div")


# ------------------------------------------------------------------------------
#  One-epoch training on the growing D dataset
# ------------------------------------------------------------------------------

def train_one_epoch(
    policy:    AgentPolicy,
    dataset:   List[GraphSample],
    optimizer: torch.optim.Optimizer,
    device:    torch.device,
    batch_size: int = 32,
    grad_clip:  float = 1.0,
) -> Dict[str, float]:
    """Trains one pass over dataset D (list of GraphSample). Returns metrics."""
    policy.train()
    random.shuffle(dataset)

    total_loss, n_action_correct, n_total = 0.0, 0, 0

    for i in range(0, len(dataset), batch_size):
        batch = dataset[i: i + batch_size]
        if not batch:
            continue

        batch_loss = torch.tensor(0.0, device=device)
        optimizer.zero_grad()

        for sample in batch:
            out = policy.forward(sample.nodes, sample.edges, sample.goal)

            action_target = torch.tensor([sample.action_id], dtype=torch.long, device=device)
            action_loss   = F.cross_entropy(out["action_logits"].unsqueeze(0), action_target)

            element_loss = torch.tensor(0.0, device=device)
            if sample.element_idx is not None:
                n = out["element_scores"].shape[0]
                if sample.element_idx < n:
                    et = torch.tensor([sample.element_idx], dtype=torch.long, device=device)
                    element_loss = F.cross_entropy(out["element_scores"].unsqueeze(0), et)

            loss = sample.weight * (action_loss + 0.5 * element_loss)
            batch_loss = batch_loss + loss

            with torch.no_grad():
                pred = int(out["action_logits"].argmax().item())
                n_action_correct += int(pred == sample.action_id)
                n_total += 1

        (batch_loss / len(batch)).backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), grad_clip)
        optimizer.step()
        total_loss += float(batch_loss.item())

    return {
        "total_loss":    total_loss / max(n_total, 1),
        "action_acc":    n_action_correct / max(n_total, 1),
        "n_samples":     n_total,
    }


# ------------------------------------------------------------------------------
#  DAgger rollout (async  needs Playwright)
# ------------------------------------------------------------------------------

async def rollout_task(
    policy:    AgentPolicy,
    goal:      str,
    start_url: str,
    beta:      float,
    max_steps: int,
    device:    torch.device,
) -> List[GraphSample]:
    """
    Roll out one task with the policy/expert mixture.
    Returns list of new GraphSamples (labelled with expert action).
    """
    from playwright.async_api import async_playwright

    new_samples: List[GraphSample] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()

        try:
            await page.goto(start_url, timeout=15000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"      [!]  Failed to load {start_url}: {e}")
            await browser.close()
            return new_samples

        for step in range(max_steps):
            try:
                # Build graph from live page using our robust CDP pipeline
                from training.graph_builder import build_graph_from_page, decide_expert_action, prune_graph
                graph = await build_graph_from_page(page)
                nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
                
                if len(nodes) < 2:
                    break   # can't do anything useful
                    
                graph["nodes"] = nodes
                graph["edges"] = edges

                # Expert labels this state (using FormExpert implicitly via decide_expert_action)
                expert_action = decide_expert_action(graph, goal, page.url)

                # Who acts?
                if random.random() < beta:
                    actor = "expert"
                    action_source = expert_action
                else:
                    actor = "policy"
                    pred  = policy.predict(nodes, edges, goal)
                    action_source = {
                        "type":       pred["action_type"],
                        "action_id":  pred["action_id"],
                        "element_idx": pred["element_idx"],
                    }

                # Always append expert label to D
                elem_idx = expert_action.get("element_idx")
                if elem_idx is not None and elem_idx >= len(nodes):
                    elem_idx = None

                sample = GraphSample(
                    goal        = goal,
                    nodes       = nodes,
                    edges       = edges,
                    action_id   = expert_action["action_id"],
                    element_idx = elem_idx,
                    success     = True,
                    weight      = 1.0,
                    url         = page.url,
                    step        = step,
                )
                new_samples.append(sample)

                # Execute the chosen action
                from core.executor import ActionExecutor
                executor = ActionExecutor(policy_v2=policy, page=page)
                
                res = await executor.execute_atomic_action(action_source, goal=goal, nodes=nodes)
                if action_source.get("type") in ("done", "fail"):
                    break

                await asyncio.sleep(0.5)   # small wait between steps

            except Exception as e:
                print(f"      [!]  Step {step} error: {e}")
                break

        await browser.close()

    return new_samples


# ------------------------------------------------------------------------------
#  Main DAgger loop
# ------------------------------------------------------------------------------

def train_dagger(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}")
    print(f"  BrowserMind  Phase 2: DAgger")
    print(f"{'='*60}")
    print(f"  Checkpoint : {args.ckpt}")
    print(f"  Iterations : {args.iterations}")
    print(f"  Max steps  : {args.max_steps}")
    print(f"  Task set   : {len(DAGGER_TASKS)} tasks")
    print(f"  Device     : {device}")
    print(f"{'='*60}\n")

    # -- Load Phase 1 checkpoint -----------------------------------------------
    ckpt_path = Path(args.ckpt)
    if not ckpt_path.exists():
        print(f"[!] Checkpoint not found: {ckpt_path}")
        print("    Run Phase 1 first: python train_bc.py")
        return

    ckpt = torch.load(ckpt_path, map_location=device)

    # Check Phase 1 quality gate
    val_acc = ckpt.get("val_action_acc", 0.0)
    if val_acc < 0.50 and not args.force:
        print(f"[!] Phase 1 val_action_acc={val_acc:.3f} < 0.50  (too low for DAgger)")
        print("    Train more Phase 1 epochs, or pass --force to skip this check.")
        return
    print(f"  Phase 1 val_action_acc = {val_acc:.3f}  [OK]")

    policy = AgentPolicy().to(device)
    # strict=False allows loading v1 checkpoints into v2 architecture
    policy.load_state_dict(ckpt["model_state"], strict=False)

    optimizer = torch.optim.AdamW(policy.parameters(), lr=args.lr)
    if ckpt.get("optimizer_state"):
        try:
            optimizer.load_state_dict(ckpt["optimizer_state"])
        except Exception:
            pass   # optimizer state may not be compatible after phase change

    # -- Seed dataset D from Phase 1 data -------------------------------------
    from training.graph_dataset import GraphDataset
    D: List[GraphSample] = []
    seed_ds = GraphDataset(args.data, split="all")
    D.extend(seed_ds.samples)
    print(f"  Seed |D| = {len(D)} samples from Phase 1 data\n")

    # -- DAgger loop -----------------------------------------------------------
    beta = 1.0

    for iteration in range(args.iterations):
        print(f"\n-- DAgger iter {iteration+1}/{args.iterations}  beta={beta:.2f}  |D|={len(D)} ---")

        # Select task subset for this iteration (cycle through all tasks)
        start_idx = (iteration * args.tasks_per_iter) % len(DAGGER_TASKS)
        task_batch = DAGGER_TASKS[start_idx: start_idx + args.tasks_per_iter]

        # Rollout
        new_samples: List[GraphSample] = []
        for task_idx, (goal, start_url) in enumerate(task_batch):
            print(f"  [{task_idx+1:>2}/{len(task_batch)}] {goal[:55]}")
            try:
                # [Robustness Upgrade] Wrap rollout in a 180s timeout to prevent site hangs
                samples = asyncio.run(
                    asyncio.wait_for(
                        rollout_task(policy, goal, start_url, beta, args.max_steps, device),
                        timeout=180.0
                    )
                )
                new_samples.extend(samples)
                print(f"           -> {len(samples)} new samples")
            except asyncio.TimeoutError:
                print(f"           [!]  Rollout timed out after 180s (Skipped)")
            except KeyboardInterrupt:
                print("\n  [!] Rollout interrupted by user")
                break
            except Exception as e:
                print(f"           [!]  rollout error: {e}")

        D.extend(new_samples)

        # Train one epoch on full D
        metrics = train_one_epoch(
            policy, D, optimizer, device,
            batch_size=args.batch_size
        )

        # Decay beta
        beta = max(0.0, beta - 0.05)

        # Evaluate (simple: metrics from training pass)
        val_acc = metrics["action_acc"]
        print(
            f"\n  iter={iteration+1:>2}  beta={beta:.2f}  |D|={len(D)}  "
            f"loss={metrics['total_loss']:.4f}  val_acc={val_acc:.3f}"
        )

        # Save checkpoint each iteration
        policy.save(
            path=str(ckpt_path),
            optimizer=optimizer,
            epoch=iteration + 1,
            phase="dagger",
            beta=beta,
            val_action_acc=val_acc,
        )

    # -- Phase 2 summary -------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Phase 2 (DAgger) complete.")
    print(f"  Total |D| = {len(D)} samples")
    print(f"  Final val_acc = {val_acc:.3f}")
    if val_acc >= 0.72:
        print(f"  [OK]  Threshold met (>=0.72) -> Phase 3 (PPO) unlocked")
        print(f"     Next: python train_ppo.py --ckpt {ckpt_path}")
    else:
        print(f"  [!]   val_acc={val_acc:.3f} < 0.72  PPO may be unstable.")
        print(f"      Consider more DAgger iterations or more Phase 1 data.")
    print(f"{'='*60}\n")


# ------------------------------------------------------------------------------
#  CLI
# ------------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="BrowserMind Phase 2  DAgger"
    )
    p.add_argument("--ckpt",           default="checkpoints/best.pt",
                   help="Phase 1 checkpoint to start from (and overwrite)")
    p.add_argument("--data",           default="training/massive_sessions",
                   help="Massive sessions directory (seed dataset D)")
    p.add_argument("--iterations",     type=int, default=5,
                   help="Number of DAgger iterations")
    p.add_argument("--max-steps",      type=int, default=15,
                   help="Max steps per task rollout")
    p.add_argument("--tasks-per-iter", type=int, default=10,
                   help="Tasks to sample per DAgger iteration")
    p.add_argument("--batch-size",     type=int, default=32)
    p.add_argument("--lr",             type=float, default=1e-4,
                   help="Lower lr than Phase 1 (spec: 1e-4)")
    p.add_argument("--force",          action="store_true",
                   help="Skip Phase 1 quality gate check")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train_dagger(args)
