"""
BrowserMind — Training Coordinator
=====================================
Orchestrates multiple SubAgents + training loop.

Loop:
  Round 0..N:
    1. All SubAgents collect concurrently (asyncio.gather)
    2. Merge all new sessions into training pool
    3. Train 1 epoch (BC loss) on full pool
    4. Evaluate on held-out tasks
    5. Save checkpoint if improved
    6. Stop if target metrics reached

Metrics target (from spec):
    action_acc  >= 0.75
    elem@3      >= 0.80
    task_success >= 0.55 on UNSEEN tasks  ← use EVAL_TASKS from collect_and_train.py
"""

import sys
import asyncio
import time
import random
from pathlib import Path
from typing import List, Dict

import torch
# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from model.agent_policy import AgentPolicy
from training.subagent import SubAgent, SubAgentResult
from training.graph_dataset import GraphDataset
from collect_and_train import EVAL_TASKS
from core.executor import ActionExecutor
from core.task_decomposer import TaskDecomposer
# Import dynamic target websites
from training.target_websites import get_tasks_for_domain

class TrainingCoordinator:
    def __init__(
        self,
        policy: AgentPolicy,
        optimizer,
        device: torch.device,
        n_rounds: int = 20,
        sessions_per_agent_per_round: int = 10,
        n_parallel_per_agent: int = 3,
        checkpoint_dir: Path = Path("checkpoints/subagent"),
        sessions_base_dir: Path = Path("training/subagent_sessions"),
    ):
        self.policy = policy
        self.optimizer = optimizer
        self.device = device
        self.n_rounds = n_rounds
        self.sessions_per_agent_per_round = sessions_per_agent_per_round
        self.n_parallel_per_agent = n_parallel_per_agent
        self.checkpoint_dir = checkpoint_dir
        self.sessions_base_dir = sessions_base_dir
        
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_base_dir.mkdir(parents=True, exist_ok=True)
        
        self.subagents = self._build_subagents()
        self.training_pool: List[Path] = []
        self.best_metric = 0.0
        self.round_log: List[Dict] = []
        
        self.decomposer = TaskDecomposer()

    def _build_subagents(self) -> List[SubAgent]:
        domains = ["extract", "navigation", "forms", "social"]
        return [
            SubAgent(
                domain=d,
                tasks=get_tasks_for_domain(d),
                save_dir=self.sessions_base_dir / d,
                policy=self.policy,
                n_parallel=self.n_parallel_per_agent,
                sessions_per_round=self.sessions_per_agent_per_round,
            )
            for d in domains
        ]

    def _train_one_epoch(self) -> Dict[str, float]:
        if not self.training_pool:
            return {"action_acc": 0.0, "elem@3": 0.0, "loss": 0.0}
            
        print(f"  Loading {len(self.training_pool)} sessions for training...")
        dataset = GraphDataset(self.training_pool)
        
        from torch.utils.data.dataloader import DataLoader
        from training.graph_dataset import collate_graph_samples

        loader = DataLoader(
            dataset, batch_size=4, shuffle=True,
            collate_fn=collate_graph_samples, num_workers=0
        )
        
        import torch.nn.functional as F
        self.policy.train()
        
        total_loss, correct_act, elem_top3, total_steps = 0.0, 0, 0, 0
        
        for batch in loader:
            batch_loss = torch.tensor(0.0, device=self.device, requires_grad=True)
            
            for sample in batch:
                if not sample: continue
                # Following train_bc.py logic
                # [Visual Upgrade] Pass image tensor if available
                out = self.policy(sample.nodes, sample.edges, sample.goal, image=getattr(sample, "image", None))
                
                # Action Loss
                target_act = torch.tensor([sample.action_id], dtype=torch.long, device=self.device)
                loss_a = F.cross_entropy(out["action_logits"].unsqueeze(0), target_act)
                
                # Accuracy
                if out["action_logits"].argmax().item() == sample.action_id:
                    correct_act += 1
                
                # Element Loss
                loss_e = torch.tensor(0.0, device=self.device)
                if sample.element_idx is not None:
                    n_els = out["element_scores"].shape[0]
                    if sample.element_idx < n_els:
                        target_el = torch.tensor([sample.element_idx], dtype=torch.long, device=self.device)
                        loss_e = F.cross_entropy(out["element_scores"].unsqueeze(0), target_el)
                        
                        top3 = torch.topk(out["element_scores"], min(3, n_els)).indices.tolist()
                        if sample.element_idx in top3:
                            elem_top3 += 1
                            
                sample_loss = sample.weight * (loss_a + 0.5 * loss_e)
                batch_loss = batch_loss + sample_loss
                total_steps += 1
                
            if isinstance(batch_loss, torch.Tensor) and batch_loss.requires_grad:
                self.optimizer.zero_grad()
                batch_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.policy.parameters(), 1.0)
                self.optimizer.step()
                total_loss += batch_loss.item()
                
        if total_steps == 0: total_steps = 1
        
        return {
            "action_acc": correct_act / total_steps,
            "elem@3": elem_top3 / total_steps,
            "loss": total_loss / total_steps
        }
                
        if total_steps == 0: total_steps = 1
        
        return {
            "action_acc": correct_act / total_steps,
            "elem@3": elem_top3 / total_steps,
            "loss": total_loss / total_steps
        }

    async def _eval_unseen(self) -> float:
        print("  Evaluating on unseen tasks...")
        if not EVAL_TASKS:
            return 0.0
            
        test_tasks = random.sample(EVAL_TASKS, min(5, len(EVAL_TASKS)))
        n_success = 0
        
        executor = ActionExecutor(policy_v2=self.policy)
        try:
            for (goal, url) in test_tasks:
                task = self.decomposer.decompose(intent="generic", user_type="bot", query=goal, url=url)
                result = await executor.execute_task(task)
                if result.success:
                    n_success += 1
        finally:
            # Not relying on executor.close(), execute_task manages browser
            pass
            
        return n_success / len(test_tasks)

    def _save_checkpoint(self, round_idx: int, metrics: dict, unseen_acc: float):
        ckpts = sorted(list(self.checkpoint_dir.glob("*.pt")))
        if len(ckpts) >= 3:
            # remove oldest
            ckpts[0].unlink()
            
        path = self.checkpoint_dir / f"round_{round_idx:03d}_acc{metrics['action_acc']:.2f}.pt"
        self.policy.save(str(path))

    async def run(self) -> Dict:
        for round_idx in range(self.n_rounds):
            print(f"\n{'='*50}")
            print(f"ROUND {round_idx + 1}/{self.n_rounds}")
            print(f"{'='*50}")

            # Step 1: All subagents collect concurrently
            results = await asyncio.gather(*[
                agent.collect_round(round_idx)
                for agent in self.subagents
            ])

            # Step 2: Add new sessions to pool
            new_paths = []
            for r in results:
                new_paths.extend(r.session_paths)
                print(f"  [{r.domain:12}] {r.n_success}/{r.n_success + r.n_failed} sessions ok")
            self.training_pool.extend(new_paths)

            # Step 3: Train 1 epoch on full pool
            metrics = self._train_one_epoch()
            print(f"\n  Training — action_acc={metrics['action_acc']:.3f}  elem@3={metrics['elem@3']:.3f}  loss={metrics['loss']:.3f}")

            # Step 4: Evaluate on unseen tasks
            unseen_acc = await self._eval_unseen()
            print(f"  Unseen task success: {unseen_acc:.3f}")

            # Step 5: Checkpoint if improved
            composite = (metrics['action_acc'] + metrics['elem@3'] + unseen_acc) / 3
            if composite > self.best_metric:
                self.best_metric = composite
                self._save_checkpoint(round_idx, metrics, unseen_acc)
                print(f"  ✅ New best: {composite:.3f} — checkpoint saved")

            # Step 6: Stop if target reached
            if (metrics['action_acc'] >= 0.75 and
                metrics['elem@3']     >= 0.80 and
                unseen_acc            >= 0.55):
                print(f"\n🎯 TARGET REACHED at round {round_idx + 1}")
                break

            self.round_log.append({
                "round": round_idx,
                "pool_size": len(self.training_pool),
                "action_acc": metrics['action_acc'],
                "elem@3": metrics['elem@3'],
                "unseen_acc": unseen_acc,
                "best": composite,
            })

        return {"rounds": len(self.round_log), "best_metric": self.best_metric, "log": self.round_log}
