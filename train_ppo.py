"""
BrowserMind — Phase 3: Reinforcement Learning (PPO)
===================================================

Fixed version using AgentPolicy's native stochastic prediction and 
Playwright CDP graph building (Forming a headless RL environment).

Usage:
  python train_ppo.py --checkpoint browsermind_policy_v2.pt
"""

from browsermind_core.training.freeze_legacy import check_legacy_trainer_call
check_legacy_trainer_call(__file__)

import os
import time
import random
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import torch
import torch.nn.functional as F

from model.agent_policy import AgentPolicy
from training.graph_builder import build_graph_from_page, _infer_target_url, _infer_type_value, prune_graph
from playwright.async_api import async_playwright
from core.executor import ActionExecutor
from core.task_decomposer import AtomicAction, ActionType

# ------------------------------------------------------------------------------
#  PPO Buffer
# ------------------------------------------------------------------------------

class PPOBuffer:
    def __init__(self):
        self.states      = []  # (nodes, edges, goal, hidden)
        self.actions     = []  # (action_id, element_idx)
        self.log_probs   = []
        self.rewards     = []
        self.values      = []
        self.is_terminals = []

    def clear(self):
        self.states.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.values.clear()
        self.is_terminals.clear()

    def merge(self, other: 'PPOBuffer'):
        """Merge another buffer's data into this one."""
        self.states.extend(other.states)
        self.actions.extend(other.actions)
        self.log_probs.extend(other.log_probs)
        self.rewards.extend(other.rewards)
        self.values.extend(other.values)
        self.is_terminals.extend(other.is_terminals)


# ------------------------------------------------------------------------------
#  Browser Environment for RL execution
# ------------------------------------------------------------------------------

async def run_episode(policy: AgentPolicy, goal: str, start_url: str, buffer: PPOBuffer, max_steps: int = 15, headless: bool = True):
    """Runs a single RL episode using the unified ActionExecutor."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()
        executor = ActionExecutor(page=page)
        
        try:
            await page.goto(start_url, timeout=15000, wait_until="domcontentloaded")
            working_mem = None
            consecutive_scrolls = 0
            
            for step in range(max_steps):
                graph = await build_graph_from_page(page)
                nodes, edges = prune_graph(graph.get("nodes", []), graph.get("edges", []))
                
                if not nodes:
                    break

                # 1. Forward pass (Stochastic)
                old_mem = working_mem.clone() if working_mem is not None else None
                out = policy.predict(nodes, edges, goal, working_mem=old_mem, stochastic=True)
                
                aid = out["action_id"]
                eidx = out["element_idx"]
                lp = out["log_prob"]
                val = out["value"]
                action_type_str = out["action_type"]
                working_mem = out["working_mem"]

                # 2. Save state
                buffer.states.append((nodes, edges, goal, old_mem))
                buffer.actions.append((aid, eidx))
                buffer.log_probs.append(lp)
                buffer.values.append(val)

                # 3. Step env via Unified ActionExecutor
                # Map RL output to AtomicAction
                atype = ActionType.CLICK
                try: atype = ActionType(action_type_str)
                except: pass
                
                atomic = AtomicAction(
                    step=step+1,
                    action_type=atype,
                    element_idx=eidx,
                    target=nodes[eidx].get("name", "") if eidx is not None and eidx < len(nodes) else ""
                )
                
                result = await executor.execute_atomic_action(atomic, goal=goal)
                
                # Check for terminal states
                done = (action_type_str in ("done", "fail")) or (step == max_steps - 1)
                success = result.success if result else False
                
                # Heuristic success check (URL changed substantially or Done predicted)
                if action_type_str == "done" and step > 1:
                    success = True

                reward = -0.05  # Step penalty
                
                if action_type_str == "scroll":
                    consecutive_scrolls += 1
                else:
                    consecutive_scrolls = 0

                if success and action_type_str == "done":
                    reward = 1.0
                elif not success:
                    reward = -0.1 # Failure penalty
                    
                if consecutive_scrolls > 3:
                    reward -= 0.5 # Infinite scroll entrapment penalty

                buffer.rewards.append(reward)
                buffer.is_terminals.append(done)

                if done:
                    break

        except Exception as e:
            print(f"      [!] Episode err: {e}")
        finally:
            await browser.close()



# ------------------------------------------------------------------------------
#  PPO Trainer
# ------------------------------------------------------------------------------

class PPOTrainer:
    def __init__(self, policy: AgentPolicy, lr: float = 1e-4):
        self.policy = policy
        self.optimizer = torch.optim.AdamW(policy.parameters(), lr=lr)
        self.MseLoss = torch.nn.MSELoss()
        self.scaler = torch.cuda.amp.GradScaler() # [SPEED] Mixed Precision
        
        self.gamma = 0.99
        self.eps_clip = 0.2
        self.K_epochs = 3

    def update(self, buffer: PPOBuffer, device: torch.device):
        if not buffer.rewards:
            return 0.0

        rewards = []
        discounted_reward = 0
        for reward, is_terminal in zip(reversed(buffer.rewards), reversed(buffer.is_terminals)):
            if is_terminal:
                discounted_reward = 0
            discounted_reward = reward + (self.gamma * discounted_reward)
            rewards.insert(0, discounted_reward)
            
        rewards = torch.tensor(rewards, dtype=torch.float32).to(device)
        old_logprobs = torch.tensor(buffer.log_probs, dtype=torch.float32).to(device)
        old_values = torch.tensor(buffer.values, dtype=torch.float32).to(device)
        
        advantages = rewards - old_values
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        total_loss = 0
        for _ in range(self.K_epochs):
            for i in range(len(buffer.states)):
                nodes, edges, goal, mem = buffer.states[i]
                aid, eidx = buffer.actions[i]
                
                if not nodes: continue
                
                aid_t = torch.tensor(aid, dtype=torch.long).to(device)
                eidx_t = torch.tensor(eidx, dtype=torch.long).to(device) if eidx is not None else torch.tensor([], dtype=torch.long).to(device)
                
                # [SPEED] Forward pass with autocast
                with torch.cuda.amp.autocast():
                    logprob, value, entropy = self.policy.evaluate_actions(
                        nodes, edges, goal, aid_t, eidx_t, working_mem=mem
                    )
                    
                    ratios = torch.exp(logprob - old_logprobs[i])
                    adv = advantages[i].detach()
                    
                    surr1 = ratios * adv
                    surr2 = torch.clamp(ratios, 1 - self.eps_clip, 1 + self.eps_clip) * adv
                    
                    loss = -torch.min(surr1, surr2) + 0.5 * self.MseLoss(value.squeeze(), rewards[i]) - 0.01 * entropy
                
                self.optimizer.zero_grad()
                self.scaler.scale(loss).backward() # [SPEED] Scaled backward
                self.scaler.step(self.optimizer)
                self.scaler.update()
                total_loss += loss.item()
                
        return total_loss / max(1, len(buffer.states) * self.K_epochs)


# ------------------------------------------------------------------------------
#  Main Loop
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, default="checkpoints/best.pt")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}")
    print(f"  BrowserMind  Phase 3: PPO (RL)")
    if device.type == "cuda":
        print(f"  [HEALTH] Training on GPU: {torch.cuda.get_device_name(0)}")
        print(f"  [HEALTH] AMP (Mixed Precision) enabled.")
    else:
        print(f"  [!] CUDA not found. Training on CPU.")
    print(f"{'='*60}")

    ckpt_path = Path(args.checkpoint)
    if not ckpt_path.exists():
        print(f"[!] Checkpoint not found: {ckpt_path}")
        return

    ckpt = torch.load(ckpt_path, map_location=device)
    policy = AgentPolicy().to(device)
    policy.load_state_dict(ckpt["model_state"])
    print("  [OK] Policy loaded successfully.")

    trainer = PPOTrainer(policy)
    buffer = PPOBuffer()

    # Import the full task set for RL exploration
    from training.dagger_tasks import DAGGER_TASKS
    tasks = DAGGER_TASKS

    # Run Dual-Parallel Rollouts for 2x speedup on 6GB VRAM
    for ep_batch in range(0, args.episodes, 2):
        batch_tasks = tasks[ep_batch : min(ep_batch + 2, args.episodes)]
        print(f"\n-- Episodes {ep_batch+1}-{ep_batch+len(batch_tasks)}/{args.episodes} ---")
        
        temp_buffers = [PPOBuffer() for _ in range(len(batch_tasks))]
        rollouts = []
        for i, (goal, url) in enumerate(batch_tasks):
            print(f"  Worker {i+1} Goal: {goal}")
            rollouts.append(run_episode(policy, goal, url, temp_buffers[i], headless=(not args.headful)))
            
        async def _run_batch():
            return await asyncio.gather(*rollouts)
            
        asyncio.run(_run_batch())
        
        # Merge parallel results into main buffer for update
        buffer.clear()
        for tb in temp_buffers:
            buffer.merge(tb)
            
        if len(buffer.rewards) > 0:
            ep_reward = sum(buffer.rewards)
            print(f"  Parallel results recorded {len(buffer.rewards)} total steps. Combined Reward: {ep_reward:.2f}")
            
            loss = trainer.update(buffer, device)
            print(f"  PPO Update Loss: {loss:.4f}")
        else:
            print("  Parallel batch yielded no samples.")
            
    # Save optimized policy
    print(f"\n[OK] Phase 3 PPO complete. Saving checkpoint_ppo.pt")
    torch.save({
        "model_state": policy.state_dict(),
        "phase": "ppo"
    }, "checkpoint_ppo.pt")


if __name__ == "__main__":
    main()
