"""
BrowserMind — Training SubAgent
================================
A specialized collector for one task domain.
Wraps collect_parallel from collect_massive.py.

Each SubAgent owns:
- a domain name ("extract", "navigation", "forms", "pipeline")
- a task list [(goal, url), ...]
- a save directory for its sessions
- a reference to the shared policy model

SubAgent does NOT train — it only collects.
Training is done by the coordinator after all agents finish.
"""

from typing import List, Tuple
from pathlib import Path
from dataclasses import dataclass
import sys
import time

sys.path.insert(0, str(Path(__file__).parent.parent))
from collect_massive import collect_parallel

@dataclass
class SubAgentResult:
    domain:        str
    round_idx:     int
    session_paths: List[Path]
    n_success:     int
    n_failed:      int
    duration_sec:  float

class SubAgent:
    def __init__(
        self,
        domain: str,
        tasks: List[Tuple[str, str]],
        save_dir: Path,
        policy,                     # shared AgentPolicy reference
        n_parallel: int = 3,        # max concurrent browsers (respect 6GB VRAM)
        sessions_per_round: int = 10,
    ):
        self.domain = domain
        self.tasks = tasks
        self.save_dir = save_dir
        self.policy = policy
        self.n_parallel = n_parallel
        self.sessions_per_round = sessions_per_round

    async def collect_round(self, round_idx: int) -> SubAgentResult:
        import random
        # Pick random tasks for this round
        round_tasks = random.choices(self.tasks, k=self.sessions_per_round)
        
        round_dir = self.save_dir / f"round_{round_idx:03d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        
        start_t = time.time()
        import uuid
        tasks_queue = []
        for goal, url in round_tasks:
            sid = f"{self.domain}_{uuid.uuid4().hex[:8]}"
            tasks_queue.append((goal, url, sid, round_dir))
            
        session_paths = await collect_parallel(
            tasks_queue=tasks_queue,
            n_parallel=self.n_parallel,
            blocked_urls={},
            policy=self.policy
        )
        duration = time.time() - start_t
        
        # Check success/failure based on collect_parallel result
        # collect_parallel returns only the paths of *saved* (successful/trainable) sessions
        # Wait, if collect_parallel yields list of paths, n_success is len(session_paths)
        n_success = len(session_paths)
        n_failed = self.sessions_per_round - n_success
        
        print(f"[SubAgent:{self.domain}] Round {round_idx} — {n_success}/{self.sessions_per_round} sessions collected")
        
        return SubAgentResult(
            domain=self.domain,
            round_idx=round_idx,
            session_paths=session_paths,
            n_success=n_success,
            n_failed=n_failed,
            duration_sec=duration
        )
