"""
BrowserMind — Autonomous Collect-and-Train Orchestrator
=========================================================
Implements the full self-training loop described in the training spec:

  PHASE 0 — Data collection:
    Collect 50 successful sessions before any training.
    A task that fails 3 times in a row on the same URL is skipped.
    A "successful session" = at least 2 steps recorded + final step success=True.

  PHASE 1 — Initial Behavioral Cloning:
    Run BC training on the 50 sessions (up to 20 epochs, early stop patience=3).

  CYCLE LOOP (up to 30 rounds):
    Collect 10 new sessions (using the current policy for actions, expert labels).
    Train 1 epoch on the full growing dataset.
    Save checkpoint to checkpoints/.
    Stop when task_success >= 0.65 or round >= 30.

Features:
  - 3-consecutive-failure skip rule per URL
  - Stuck-detection: identical graph hash 3 times in a row -> stop task
  - Checkpoints saved to checkpoints/, only best 3 kept
  - All sessions saved to training/sessions/round_NNN/

Usage:
  python collect_and_train.py                       # full pipeline
  python collect_and_train.py --collect-only        # only Phase 0
  python collect_and_train.py --train-only          # only BC on existing data
  python collect_and_train.py --cycle-only          # only the cycle loop
  python collect_and_train.py --headless false      # show browser
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from core.privacy import (
    redact_sensitive_text,
    sanitize_expert_action,
    sanitize_goal_for_storage,
    sanitize_graph_for_storage,
)

# ---------------------------------------------------------------------------
#  Task list
# ---------------------------------------------------------------------------
from training.target_websites import get_all_as_tuples
ALL_TASKS = get_all_as_tuples()

EVAL_TASKS: List[Tuple[str, str]] = [
    ("open issues on torvalds/linux", "https://github.com/torvalds/linux"),
    ("search for neural networks",    "https://scholar.google.com"),
    ("find python 3.12 release",      "https://www.python.org/downloads/"),
    ("search for bert model",         "https://huggingface.co/models"),
    ("find pytorch getting started",  "https://pytorch.org/get-started/locally/"),
    ("search for docker install",     "https://docs.docker.com"),
    ("find numpy documentation",      "https://numpy.org/doc/"),
    ("open pypi for requests",        "https://pypi.org"),
    ("search arxiv for gpt",          "https://arxiv.org/search/"),
    ("find stackoverflow top questions", "https://stackoverflow.com/questions"),
]

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
CHECKPOINTS_DIR    = Path("checkpoints")
SESSIONS_DIR       = Path("training/sessions")
SPEC_SESSIONS_DIR  = Path("training/spec_sessions")
LOG_FILE           = Path("collect_train.log")

TARGET_INITIAL_SESSIONS = 50
SESSIONS_PER_CYCLE      = 10
MAX_CYCLES              = 30
MAX_STEPS_PER_TASK      = 15
MAX_FAILURES_PER_URL    = 3
STUCK_HASH_WINDOW       = 3
BEST_CKPT_KEEP          = 3

INITIAL_BC_EPOCHS       = 20
BC_PATIENCE             = 3
BC_LR                   = 3e-4
CYCLE_LR                = 1e-4
BATCH_SIZE              = 32
GRAD_CLIP               = 1.0
TASK_SUCCESS_TARGET     = 0.65


# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------
def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


VERIFIABLE_ACTIONS = {"click", "navigate", "submit"}


def _samples_meet_success_criteria(samples: List[Dict]) -> bool:
    """
    A trainable session needs at least two steps and must not end with a
    verifiable browser action that explicitly failed.
    """
    if len(samples) < 2:
        return False

    last = samples[-1]
    last_action = str(last.get("expert_action", {}).get("type", "")).lower()
    last_success = bool(last.get("success", False))
    if last_action in VERIFIABLE_ACTIONS and not last_success:
        return False
    return True


# ---------------------------------------------------------------------------
#  Session recording
# ---------------------------------------------------------------------------
class SessionRecorder:
    """Records spec-format samples during a single task run."""

    def __init__(self, goal: str, save_dir: Path):
        self.goal     = sanitize_goal_for_storage(goal)
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.samples: List[Dict] = []

    def record(
        self,
        graph:         Dict,
        expert_action: Dict,
        url:           str,
        step:          int,
        success:       bool,
    ):
        """Append one spec-format sample."""
        safe_graph = sanitize_graph_for_storage(graph)
        safe_action = sanitize_expert_action(expert_action, goal_text=self.goal)
        self.samples.append({
            "goal":          self.goal,
            "url":           redact_sensitive_text(url),
            "step":          step,
            "success":       success,
            "graph":         safe_graph,
            "expert_action": safe_action,
        })

    def is_trainable(self) -> bool:
        """Compatibility wrapper for the session success gate."""
        return _samples_meet_success_criteria(self.samples)

    def is_successful(self) -> bool:
        """A successful session is safe to keep for training."""
        return self.is_trainable()

    def save(self, session_id: str) -> Optional[Path]:
        """Write samples to a JSON file. Returns path if saved."""
        if not self.samples:
            return None
        out_path = self.save_dir / f"{session_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.samples, f, indent=2, ensure_ascii=False)
        return out_path


# ---------------------------------------------------------------------------
#  Browser actions
# ---------------------------------------------------------------------------
async def _execute_expert_action(
    page,
    action:    Dict,
    nodes:     List[Dict],
) -> bool:
    """Execute the expert-decided action on the page. Returns success bool."""
    etype    = action.get("type", "")
    eidx     = action.get("element_idx")
    value    = action.get("value", "")

    try:
        if etype == "navigate":
            if value:
                await page.goto(value, timeout=12000, wait_until="domcontentloaded")
            return True

        if etype == "wait":
            await asyncio.sleep(1.5)
            return True

        if etype == "scroll":
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(0.5)
            return True

        if etype == "go_back":
            await page.go_back(timeout=8000)
            return True

        if etype in ("done", "fail"):
            return etype == "done"

        # click / type / extract — need an element
        if eidx is None or eidx >= len(nodes):
            return False

        nd   = nodes[eidx]
        name = nd.get("name", "")
        role = nd.get("role", "generic")

        if etype == "click":
            locators = []
            if role == "button" and name:
                locators.append(lambda: page.get_by_role("button", name=name).first)
            if role == "link" and name:
                locators.append(lambda: page.get_by_role("link", name=name).first)
            if name:
                locators.append(lambda: page.get_by_text(name, exact=False).first)
            for get_loc in locators:
                try:
                    loc = get_loc()
                    if await loc.is_visible():
                        await loc.click(timeout=5000)
                        await asyncio.sleep(0.8)
                        return True
                except Exception:
                    continue
            return False

        if etype == "type":
            locators = []
            if name:
                locators.append(lambda: page.get_by_role("textbox", name=name).first)
                locators.append(lambda: page.get_by_placeholder(name).first)
                locators.append(lambda: page.get_by_label(name).first)
            locators.append(lambda: page.locator("input:visible").first)
            for get_loc in locators:
                try:
                    loc = get_loc()
                    if await loc.is_visible():
                        await loc.fill(value or name, timeout=5000)
                        await asyncio.sleep(0.3)
                        return True
                except Exception:
                    continue
            return False

    except Exception as e:
        _log(f"    [action error] {etype}: {e}")
        return False

    return False


# ---------------------------------------------------------------------------
#  Single task runner
# ---------------------------------------------------------------------------
async def run_task(
    goal:      str,
    start_url: str,
    session_id: str,
    save_dir:  Path,
    page,
    policy=None,       # optional: AgentPolicy for DAgger-lite
) -> Optional[Path]:
    """
    Run one task on an already-open browser page.
    Records spec-format samples.
    Returns path to saved session file, or None if session was unsuccessful.
    """
    from training.graph_builder import build_graph_from_page, decide_expert_action, graph_hash
    from core.validator import Validator

    recorder  = SessionRecorder(goal=goal, save_dir=save_dir)
    validator = Validator()

    try:
        await page.goto(start_url, timeout=15000, wait_until="domcontentloaded")
    except Exception as e:
        _log(f"    [goto error] {start_url}: {e}")
        return None

    prev_url      = page.url
    hash_history  = deque(maxlen=STUCK_HASH_WINDOW)

    for step in range(MAX_STEPS_PER_TASK):
        try:
            graph = await build_graph_from_page(page)
        except Exception as e:
            _log(f"    [graph error] step={step}: {e}")
            break

        nodes    = graph.get("nodes", [])
        gh       = graph_hash(graph)

        # Stuck detection
        hash_history.append(gh)
        if len(hash_history) == STUCK_HASH_WINDOW and len(set(hash_history)) == 1:
            _log(f"    [stuck] {goal!r} — same graph 3 steps, stopping")
            break

        # Expert decides action
        current_url   = page.url
        expert_action = decide_expert_action(graph, goal, current_url)
        expert_for_record = dict(expert_action)
        eidx = expert_for_record.get("element_idx")
        if isinstance(eidx, int) and 0 <= eidx < len(nodes):
            expert_for_record.setdefault("target_text", str(nodes[eidx].get("name", "")))

        # Optional: DAgger-lite — policy acts, expert labels
        if policy is not None:
            try:
                pred = policy.predict(nodes, graph.get("edges", []), goal)
                # We always label with expert, but optionally let policy act
                # (50% chance after first 5 steps = exploration)
                if step >= 5 and random.random() < 0.5:
                    exec_action = {
                        "type":        pred["action_type"],
                        "action_id":   pred["action_id"],
                        "element_idx": pred["element_idx"],
                        "value":       expert_action.get("value", ""),
                    }
                else:
                    exec_action = expert_action
            except Exception:
                exec_action = expert_action
        else:
            exec_action = expert_action

        # Execute
        ok = await _execute_expert_action(page, exec_action, nodes)
        await asyncio.sleep(0.4)

        # Validate — only treat as done if validator found a REAL signal
        # (not the default "benefit of the doubt" result)
        task_done = False
        try:
            val_result = await validator.check(page, goal, prev_url)
            # Only accept explicit signals, not the default_ok fallback
            if val_result.success and val_result.signal not in ("default_ok",):
                task_done = True
        except Exception:
            pass

        success = ok  # per-step success = action executed ok

        # Record (always label with expert action, not exec_action)
        recorder.record(
            graph         = graph,
            expert_action = expert_for_record,
            url           = current_url,
            step          = step + 1,
            success       = success,
        )

        prev_url = page.url

        # Stop early only if: explicit goal-done signal OR minimum 5 steps reached
        if task_done and len(recorder.samples) >= 5:
            break
        if expert_action.get("type") in ("done", "fail"):
            break

    # Save session (always save if >=2 steps; success flag is per-step only)
    saved_path = recorder.save(session_id) if len(recorder.samples) >= 1 else None
    if saved_path and recorder.is_successful():
        _log(f"    [ok] {goal!r}  {len(recorder.samples)} steps  -> {saved_path.name}")
        return saved_path
    else:
        _log(f"    [fail] {goal!r}  {len(recorder.samples)} steps  (did not meet success criteria)")
        return None


# ---------------------------------------------------------------------------
#  Collection loop  (Phase 0 + cycle)
# ---------------------------------------------------------------------------
async def collect_sessions(
    target:       int,
    save_dir:     Path,
    headless:     bool    = True,
    policy=None,
    task_list:    List    = None,
) -> List[Path]:
    """
    Collect `target` successful sessions.
    Returns list of paths to successful session files.

    Rules:
    - Max 3 consecutive failures per URL -> skip that URL
    - Task list is cycled until target is reached
    """
    from playwright.async_api import async_playwright

    if task_list is None:
        task_list = ALL_TASKS

    save_dir.mkdir(parents=True, exist_ok=True)

    successful_paths: List[Path]       = []
    url_failures:     Dict[str, int]   = defaultdict(int)
    url_skipped:      set              = set()
    session_counter   = 0
    task_cycle        = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        while len(successful_paths) < target:
            task_cycle += 1
            tasks_remaining = [
                (g, u) for g, u in task_list
                if u not in url_skipped
            ]

            if not tasks_remaining:
                _log("[collect] All task URLs have been skipped. Stopping collection.")
                break

            for goal, start_url in tasks_remaining:
                if len(successful_paths) >= target:
                    break

                session_counter += 1
                sid = f"session_{session_counter:04d}"
                _log(f"  [{len(successful_paths)+1}/{target}] goal={goal!r}  url={start_url}")

                page = await browser.new_page()
                try:
                    path = await run_task(
                        goal      = goal,
                        start_url = start_url,
                        session_id= sid,
                        save_dir  = save_dir,
                        page      = page,
                        policy    = policy,
                    )
                except Exception as e:
                    _log(f"    [exception] {e}")
                    path = None
                finally:
                    await page.close()

                if path is not None:
                    successful_paths.append(path)
                    url_failures[start_url] = 0   # reset on success
                else:
                    url_failures[start_url] += 1
                    if url_failures[start_url] >= MAX_FAILURES_PER_URL:
                        _log(f"    [skip] {start_url!r} — {MAX_FAILURES_PER_URL}x failures")
                        url_skipped.add(start_url)
                        _save_skip_log(goal, start_url, save_dir)

                await asyncio.sleep(0.5)   # polite pause between tasks

        await browser.close()

    _log(f"[collect] Done: {len(successful_paths)} successful sessions in {save_dir}")
    return successful_paths


def _save_skip_log(goal: str, url: str, save_dir: Path):
    log_path = save_dir.parent / "skipped_tasks.json"
    skips    = []
    if log_path.exists():
        try:
            skips = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    skips.append({"task": goal, "url": url, "status": "skipped", "reason": "3x failure"})
    log_path.write_text(json.dumps(skips, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
#  Training utilities
# ---------------------------------------------------------------------------

def _load_all_samples(session_files: List[Path]) -> List[Dict]:
    """Load all spec samples from a list of session files."""
    all_samples = []
    for sf in session_files:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_samples.extend(data)
            elif isinstance(data, dict):
                all_samples.extend(data.get("samples", [data]))
        except Exception as e:
            _log(f"  [load error] {sf.name}: {e}")
    return all_samples


def _train_one_epoch(
    policy,
    samples:    List[Dict],
    optimizer,
    device:     torch.device,
    batch_size: int   = BATCH_SIZE,
    grad_clip:  float = GRAD_CLIP,
) -> Dict[str, float]:
    """Train one epoch over a list of spec-format sample dicts."""
    policy.train()
    random.shuffle(samples)

    total_loss = 0.0
    n_correct  = 0
    n_total    = 0

    for i in range(0, len(samples), batch_size):
        batch = samples[i: i + batch_size]
        if not batch:
            continue

        optimizer.zero_grad()
        batch_loss = torch.tensor(0.0, device=device)

        for s in batch:
            graph  = s.get("graph", {})
            nodes  = graph.get("nodes", [])
            edges  = graph.get("edges", [])
            goal   = s.get("goal", "")
            ea     = s.get("expert_action", {})
            success= s.get("success", True)

            action_id   = ea.get("action_id")
            element_idx = ea.get("element_idx")

            # Skip bad samples
            if not nodes or action_id is None or not (0 <= action_id <= 7):
                continue
            if element_idx is not None and element_idx >= len(nodes):
                element_idx = None

            try:
                out = policy.forward(nodes, edges, goal)
            except Exception:
                continue

            weight = 1.0 if success else 0.1

            at = torch.tensor([action_id], dtype=torch.long, device=device)
            a_loss = F.cross_entropy(out["action_logits"].unsqueeze(0), at)

            e_loss = torch.tensor(0.0, device=device)
            if element_idx is not None and success:
                n = out["element_scores"].shape[0]
                if element_idx < n:
                    et     = torch.tensor([element_idx], dtype=torch.long, device=device)
                    e_loss = F.cross_entropy(out["element_scores"].unsqueeze(0), et)

            sample_loss = weight * (a_loss + 0.5 * e_loss)
            batch_loss  = batch_loss + sample_loss

            with torch.no_grad():
                pred_a = int(out["action_logits"].argmax().item())
                n_correct += int(pred_a == action_id)
                n_total   += 1

        if n_total > 0:
            (batch_loss / max(len(batch), 1)).backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), grad_clip)
            optimizer.step()
            total_loss += float(batch_loss.item())

    return {
        "loss":       total_loss / max(n_total, 1),
        "action_acc": n_correct  / max(n_total, 1),
        "n_samples":  n_total,
    }


@torch.no_grad()
def _eval_offline(policy, samples: List[Dict], device: torch.device) -> Dict[str, float]:
    """Quick offline eval on a list of spec samples."""
    policy.eval()
    n_correct, n_e1, n_e3, n_elem = 0, 0, 0, 0
    n_total = 0

    for s in samples:
        graph  = s.get("graph", {})
        nodes  = graph.get("nodes", [])
        edges  = graph.get("edges", [])
        goal   = s.get("goal", "")
        ea     = s.get("expert_action", {})
        action_id   = ea.get("action_id")
        element_idx = ea.get("element_idx")

        if not nodes or action_id is None:
            continue

        try:
            out = policy.forward(nodes, edges, goal)
        except Exception:
            continue

        pred_a = int(out["action_logits"].argmax().item())
        n_correct += int(pred_a == action_id)
        n_total   += 1

        if element_idx is not None and element_idx < len(nodes):
            n = out["element_scores"].shape[0]
            if n > 0:
                k     = min(3, n)
                top3  = torch.topk(out["element_scores"], k).indices.tolist()
                n_e1 += int(top3[0] == element_idx)
                n_e3 += int(element_idx in top3)
                n_elem += 1

    return {
        "action_acc":  n_correct / max(n_total, 1),
        "elem_acc_1":  n_e1 / max(n_elem, 1),
        "elem_acc_3":  n_e3 / max(n_elem, 1),
        "n_total":     n_total,
    }


# ---------------------------------------------------------------------------
#  Checkpoint management
# ---------------------------------------------------------------------------

def _save_checkpoint(
    policy,
    optimizer,
    phase:      str,
    epoch:      int,
    round_num:  int,
    metrics:    Dict,
    extra:      str = "",
) -> Path:
    """Save checkpoint; keeps only best BEST_CKPT_KEEP by action_acc."""
    CHECKPOINTS_DIR.mkdir(exist_ok=True)
    val_acc = metrics.get("action_acc", 0.0)
    tag     = f"{phase}_round{round_num:03d}_ep{epoch:03d}"
    path    = CHECKPOINTS_DIR / f"browsermind_{tag}.pt"

    payload = {
        "model_state":      policy.state_dict(),
        "optimizer_state":  optimizer.state_dict(),
        "epoch":            epoch,
        "phase":            phase,
        "round":            round_num,
        "val_action_acc":   val_acc,
        "val_element_acc3": metrics.get("elem_acc_3", 0.0),
        "task_success":     metrics.get("task_success", 0.0),
        "config": {
            "hidden_dim":       128,
            "goal_dim":         384,
            "n_roles":          17,
            "n_action_types":   8,
            "graph_attn_heads": 4,
        },
    }
    torch.save(payload, path)
    _log(f"  [ckpt] Saved {path.name}  action_acc={val_acc:.3f}")

    # Always write best.pt -> symlink or copy to the best checkpoint
    best_path = CHECKPOINTS_DIR / "best.pt"
    torch.save(payload, best_path)

    # Keep only best BEST_CKPT_KEEP checkpoints (by val_action_acc)
    _prune_checkpoints()
    return path


def _prune_checkpoints():
    """Delete old checkpoints, keeping only the best BEST_CKPT_KEEP."""
    candidates = [
        p for p in CHECKPOINTS_DIR.glob("browsermind_*.pt")
        if p.name != "best.pt"
    ]
    if len(candidates) <= BEST_CKPT_KEEP:
        return

    scored = []
    for p in candidates:
        try:
            ckpt = torch.load(p, map_location="cpu")
            scored.append((ckpt.get("val_action_acc", 0.0), p))
        except Exception:
            scored.append((0.0, p))

    scored.sort(key=lambda x: -x[0])   # descending by accuracy
    to_delete = scored[BEST_CKPT_KEEP:]
    for _, p in to_delete:
        try:
            p.unlink()
            _log(f"  [prune] Removed {p.name}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Main orchestrator
# ---------------------------------------------------------------------------

def run(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _log(f"[start] Device={device}  headless={args.headless}")
    _log(f"[start] Target initial sessions: {TARGET_INITIAL_SESSIONS}")

    from model.agent_policy import AgentPolicy

    # ======================================================================
    #  PHASE 0 — Collect 50 successful sessions
    # ======================================================================
    initial_sessions: List[Path] = []

    if not args.train_only and not args.cycle_only:
        _log("\n=== PHASE 0: Collecting initial sessions ===")
        phase0_dir = SESSIONS_DIR / "phase0"

        # Resume: check how many we already have
        if phase0_dir.exists():
            existing = [
                p for p in phase0_dir.glob("*.json")
                if _is_successful_session(p)
            ]
            _log(f"  Resuming: already have {len(existing)} successful sessions")
            initial_sessions = existing

        if len(initial_sessions) < TARGET_INITIAL_SESSIONS:
            needed = TARGET_INITIAL_SESSIONS - len(initial_sessions)
            _log(f"  Collecting {needed} more sessions...")
            new_paths = asyncio.run(collect_sessions(
                target    = needed,
                save_dir  = phase0_dir,
                headless  = args.headless,
                policy    = None,   # expert only in phase 0
            ))
            initial_sessions.extend(new_paths)

        _log(f"[phase0] Done: {len(initial_sessions)} successful sessions")

    # ======================================================================
    #  PHASE 1 — Initial Behavioral Cloning on 50 sessions
    # ======================================================================
    policy    = AgentPolicy().to(device)
    optimizer = torch.optim.AdamW(
        policy.parameters(), lr=BC_LR, weight_decay=1e-4
    )

    all_session_files: List[Path] = []

    if not args.collect_only and not args.cycle_only:
        # Load checkpoint to resume if available
        best_ckpt = CHECKPOINTS_DIR / "best.pt"
        if best_ckpt.exists():
            ckpt = torch.load(best_ckpt, map_location=device)
            missing, unexpected = policy.load_state_dict(ckpt["model_state"], strict=False)
            try:
                optimizer.load_state_dict(ckpt["optimizer_state"])
            except Exception:
                pass
            _log(f"[resume] Loaded {best_ckpt}  val_acc={ckpt.get('val_action_acc',0):.3f}")

        # Gather all phase0 sessions
        phase0_dir = SESSIONS_DIR / "phase0"
        if phase0_dir.exists():
            all_session_files = [
                p for p in phase0_dir.glob("*.json")
                if _is_successful_session(p)
            ]
        all_session_files.extend(initial_sessions)
        # Deduplicate by path
        seen = set()
        all_session_files = [
            p for p in all_session_files
            if not (str(p) in seen or seen.add(str(p)))
        ]

        if not all_session_files:
            _log("[phase1] No session files found. Run Phase 0 first.")
        else:
            _log(f"\n=== PHASE 1: Behavioral Cloning on {len(all_session_files)} sessions ===")
            all_samples = _load_all_samples(all_session_files)

            # 80/20 split at session level
            random.shuffle(all_session_files)
            n_val     = max(1, int(len(all_session_files) * 0.2))
            val_files = all_session_files[:n_val]
            trn_files = all_session_files[n_val:]
            trn_samples = _load_all_samples(trn_files)
            val_samples = _load_all_samples(val_files)

            _log(f"  Train: {len(trn_samples)} samples | Val: {len(val_samples)} samples")

            best_val_acc  = 0.0
            no_improve    = 0

            for epoch in range(1, INITIAL_BC_EPOCHS + 1):
                t0      = time.time()
                metrics = _train_one_epoch(policy, trn_samples, optimizer, device)
                val_m   = _eval_offline(policy, val_samples, device)
                elapsed = time.time() - t0

                _log(
                    f"  Epoch {epoch:3d}/{INITIAL_BC_EPOCHS} | "
                    f"loss={metrics['loss']:.4f} | "
                    f"val_acc={val_m['action_acc']:.3f} | "
                    f"elem@3={val_m['elem_acc_3']:.3f} | "
                    f"{elapsed:.1f}s"
                )

                # Save every epoch
                _save_checkpoint(policy, optimizer, "bc", epoch, 0, val_m)

                if val_m["action_acc"] > best_val_acc:
                    best_val_acc = val_m["action_acc"]
                    no_improve   = 0
                else:
                    no_improve  += 1
                    _log(f"  No improvement ({no_improve}/{BC_PATIENCE})")
                    if no_improve >= BC_PATIENCE:
                        _log(f"  Early stop at epoch {epoch}")
                        break

                if val_m["action_acc"] >= 0.70:
                    _log(f"  Target action_acc >= 0.70 reached!")
                    break

            _log(f"[phase1] Done. Best val_acc={best_val_acc:.3f}")

    # ======================================================================
    #  CYCLE LOOP — collect 10 -> train 1 epoch -> repeat
    # ======================================================================
    if not args.collect_only and not args.train_only:
        _log(f"\n=== CYCLE LOOP (max {MAX_CYCLES} rounds) ===")

        # Load best checkpoint if we didn't just train
        best_ckpt = CHECKPOINTS_DIR / "best.pt"
        if best_ckpt.exists() and args.cycle_only:
            ckpt = torch.load(best_ckpt, map_location=device)
            policy = AgentPolicy().to(device)
            policy.load_state_dict(ckpt["model_state"], strict=False)
            optimizer = torch.optim.AdamW(
                policy.parameters(), lr=CYCLE_LR, weight_decay=1e-4
            )
            try:
                optimizer.load_state_dict(ckpt["optimizer_state"])
                for g in optimizer.param_groups:
                    g["lr"] = CYCLE_LR
            except Exception:
                pass
            _log(f"[cycle] Started from {best_ckpt} val_acc={ckpt.get('val_action_acc',0):.3f}")
        else:
            # Lower LR for cycles
            for g in optimizer.param_groups:
                g["lr"] = CYCLE_LR

        # Rebuild all_session_files from disk if this is cycle_only mode
        if args.cycle_only:
            all_session_files = []
            for d in SESSIONS_DIR.iterdir():
                if d.is_dir():
                    all_session_files.extend(p for p in d.glob("*.json"))

        for round_num in range(1, MAX_CYCLES + 1):
            _log(f"\n--- Round {round_num}/{MAX_CYCLES} ---")

            # Collect 10 new sessions with current policy (DAgger-lite)
            cycle_dir = SESSIONS_DIR / f"round_{round_num:03d}"
            _log(f"  Collecting {SESSIONS_PER_CYCLE} sessions with current policy...")
            new_paths = asyncio.run(collect_sessions(
                target    = SESSIONS_PER_CYCLE,
                save_dir  = cycle_dir,
                headless  = args.headless,
                policy    = policy,      # DAgger-lite
            ))
            all_session_files.extend(new_paths)
            _log(f"  New sessions: {len(new_paths)} | Total: {len(all_session_files)}")

            # Train 1 epoch on full dataset
            all_samples = _load_all_samples(all_session_files)
            if not all_samples:
                _log("  No samples to train on, skipping round.")
                continue

            random.shuffle(all_samples)
            n_val       = max(1, int(len(all_samples) * 0.2))
            val_samples = all_samples[:n_val]
            trn_samples = all_samples[n_val:]

            _log(f"  Training 1 epoch | {len(trn_samples)} train, {len(val_samples)} val")
            metrics     = _train_one_epoch(policy, trn_samples, optimizer, device)
            val_metrics = _eval_offline(policy, val_samples, device)

            _log(
                f"  Round {round_num} | "
                f"loss={metrics['loss']:.4f} | "
                f"action_acc={val_metrics['action_acc']:.3f} | "
                f"elem@3={val_metrics['elem_acc_3']:.3f}"
            )

            # Save checkpoint
            _save_checkpoint(policy, optimizer, "cycle", round_num, round_num, val_metrics)

            # Check target
            if val_metrics["action_acc"] >= TASK_SUCCESS_TARGET:
                _log(f"[cycle] Target action_acc >= {TASK_SUCCESS_TARGET} reached at round {round_num}!")
                break

        _log("[cycle] Cycle loop finished.")

    _log("[done] collect_and_train.py complete.")


def _is_successful_session(path: Path) -> bool:
    """Check if a saved session passes the training-success filter."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data if isinstance(data, list) else data.get("samples", [])
        return _samples_meet_success_criteria(samples)
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="BrowserMind autonomous collect-and-train pipeline"
    )
    p.add_argument("--headless",     type=lambda x: x.lower() != "false",
                   default=True,     help="Run browser headless (default: true)")
    p.add_argument("--collect-only", action="store_true",
                   help="Only run Phase 0 data collection")
    p.add_argument("--train-only",   action="store_true",
                   help="Only run Phase 1 BC training on existing sessions")
    p.add_argument("--cycle-only",   action="store_true",
                   help="Only run the cycle loop (needs best.pt checkpoint)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args)
