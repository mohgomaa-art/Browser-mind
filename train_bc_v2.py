"""BrowserMind BC v2 — trains on OutcomeLedger episode JSONL.

Replaces the legacy `train_bc.py` + GraphDataset stack. Reads the JSONL
produced by `bm dataset export` and trains a two-head BC policy:

  * action_head    — predicts which action_type (click/fill/press/...)
  * strategy_head  — predicts which resolution_strategy to try first

Effect-verified successes are weighted 1.5x, effect-rejected 0.5x,
unknown 1.0x. Uses CrossEntropy + AdamW + cosine LR + early stop.

NOTE on strategy_head: In the current corpus the resolution strategy is
heavily correlated with the action type (fill→exact_selector,
navigate→navigate, etc.). The strategy_head therefore trains mostly as
a memorized function of action_head rather than an independent predictor.
Use --strategy-loss-weight 0 to disable the strategy head loss and train
only the action head, which is the more reliable signal. This limitation
resolves as the corpus accumulates diverse multi-strategy attempts on the
same (site, role, action) tuples.

Usage:
  python train_bc_v2.py --data training/dataset_v1.jsonl
  python train_bc_v2.py --data training/dataset_v1.jsonl --epochs 20 \\
                        --output bc_v2.pt --strategy-loss-weight 0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, random_split


# ── Vocabularies ────────────────────────────────────────────────────────────

ACTION_TYPES = [
    "click", "fill", "press", "navigate",
    "submit", "select", "check", "upload", "unknown",
]
RESOLUTION_STRATEGIES = [
    "primary_semantic", "loose_semantic", "semantic+container",
    "placeholder", "nearby_text", "structural_path",
    "exact_selector", "affordance", "unknown",
]
ROLES = [
    "button", "textbox", "link", "combobox", "checkbox", "radio",
    "searchbox", "img", "heading", "listitem", "unknown",
]


def _vocab(items: List[str]) -> Dict[str, int]:
    return {v: i for i, v in enumerate(items)}


ACTION_VOCAB = _vocab(ACTION_TYPES)
STRATEGY_VOCAB = _vocab(RESOLUTION_STRATEGIES)
ROLE_VOCAB = _vocab(ROLES)

# Environment vocabulary — sites seen in practice.
# "unknown" is the catch-all for sites not in the list.
SITES = [
    "saucedemo", "demoqa", "aria_internet", "static_baseline",
    "greenhouse", "lever", "workday", "huggingface", "unknown",
]
SITE_VOCAB = _vocab(SITES)


def _site_id(s: Optional[str]) -> int:
    return SITE_VOCAB.get((s or "").lower(), SITE_VOCAB["unknown"])


def _action_id(a: Optional[str]) -> int:
    return ACTION_VOCAB.get((a or "").lower(), ACTION_VOCAB["unknown"])


def _strategy_id(s: Optional[str]) -> int:
    return STRATEGY_VOCAB.get((s or "").lower(), STRATEGY_VOCAB["unknown"])


def _role_id(r: Optional[str]) -> int:
    return ROLE_VOCAB.get((r or "").lower(), ROLE_VOCAB["unknown"])


class EpisodeDataset(Dataset):
    def __init__(self, jsonl_path: str, success_only: bool = True, min_value_score: float = 0.0):
        self.samples: List[dict] = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ep = json.loads(line)
                if success_only and ep.get("label", 0) != 1:
                    continue
                if min_value_score > 0.0 and ep.get("task_value_score", 1.0) < min_value_score:
                    continue
                self.samples.append(ep)
        print(f"[Dataset] Loaded {len(self.samples)} episodes from {jsonl_path}"
              + (f" (min_value_score≥{min_value_score})" if min_value_score > 0.0 else ""))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        ep = self.samples[idx]
        ev = ep.get("effect_verified")
        weight = 1.5 if ev is True else (0.5 if ev is False else 1.0)
        return {
            "action_id":   torch.tensor(_action_id(ep.get("action_type")), dtype=torch.long),
            "strategy_id": torch.tensor(_strategy_id(ep.get("resolution_strategy")), dtype=torch.long),
            "role_id":     torch.tensor(_role_id(ep.get("role")), dtype=torch.long),
            "site_id":     torch.tensor(_site_id(ep.get("site")), dtype=torch.long),
            "step_seq":    torch.tensor(min(int(ep.get("step_seq", 0)), 50), dtype=torch.float32),
            "weight":      torch.tensor(weight, dtype=torch.float32),
        }


# placeholder-after-first-write


class BCPolicyV2(nn.Module):
    """Two-head BC policy: action_type + resolution_strategy.

    Inputs: role_id, action_id, site_id (environment), step_seq.
    The site embedding allows the model to learn site-specific resolution
    preferences (e.g. exact_selector dominates saucedemo; loose_semantic
    may be needed for greenhouse comboboxes).
    """

    def __init__(self, embed_dim: int = 64, hidden: int = 128):
        super().__init__()
        self.role_embed = nn.Embedding(len(ROLES), embed_dim)
        self.action_embed = nn.Embedding(len(ACTION_TYPES), embed_dim)
        self.site_embed = nn.Embedding(len(SITES), embed_dim)
        self.trunk = nn.Sequential(
            nn.Linear(embed_dim * 3 + 1, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.action_head = nn.Linear(hidden, len(ACTION_TYPES))
        self.strategy_head = nn.Linear(hidden, len(RESOLUTION_STRATEGIES))

    def forward(self, role_ids, action_ids, step_seqs, site_ids=None):
        r = self.role_embed(role_ids)
        a = self.action_embed(action_ids)
        s = step_seqs.unsqueeze(-1)
        if site_ids is not None:
            site = self.site_embed(site_ids)
        else:
            # Zero-embedding when site is unknown (backward compat with old callers)
            site = torch.zeros_like(r)
        x = torch.cat([r, a, site, s], dim=-1)
        h = self.trunk(x)
        return {
            "action_logits":   self.action_head(h),
            "strategy_logits": self.strategy_head(h),
        }


def _weighted_ce(logits, targets, weights):
    return (F.cross_entropy(logits, targets, reduction="none") * weights).mean()


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Train] Device: {device}")

    full_ds = EpisodeDataset(args.data, success_only=True, min_value_score=args.min_value_score)
    if len(full_ds) == 0:
        print("[ERROR] No training samples. Run replays first to populate the OutcomeLedger.")
        return 1

    val_size = max(1, int(len(full_ds) * 0.15))
    train_size = len(full_ds) - val_size
    train_ds, val_ds = random_split(full_ds, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size)

    model = BCPolicyV2().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val = float("inf")
    patience = 0

    print(f"[Train] {train_size} train / {val_size} val | {args.epochs} epochs")

    for epoch in range(1, args.epochs + 1):
        # ---- train ----
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            role_ids = batch["role_id"].to(device)
            action_ids = batch["action_id"].to(device)
            strategy_ids = batch["strategy_id"].to(device)
            site_ids = batch["site_id"].to(device)
            step_seqs = batch["step_seq"].to(device)
            weights = batch["weight"].to(device)
            out = model(role_ids, action_ids, step_seqs, site_ids)
            loss = (
                _weighted_ce(out["action_logits"], action_ids, weights)
                + args.strategy_loss_weight * _weighted_ce(out["strategy_logits"], strategy_ids, weights)
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item()
        scheduler.step()

        # ---- validate ----
        model.eval()
        val_loss = 0.0
        action_correct = 0
        with torch.no_grad():
            for batch in val_loader:
                role_ids = batch["role_id"].to(device)
                action_ids = batch["action_id"].to(device)
                strategy_ids = batch["strategy_id"].to(device)
                site_ids = batch["site_id"].to(device)
                step_seqs = batch["step_seq"].to(device)
                weights = batch["weight"].to(device)
                out = model(role_ids, action_ids, step_seqs, site_ids)
                val_loss += (
                    _weighted_ce(out["action_logits"], action_ids, weights)
                    + args.strategy_loss_weight * _weighted_ce(out["strategy_logits"], strategy_ids, weights)
                ).item()
                action_correct += (out["action_logits"].argmax(dim=-1) == action_ids).sum().item()

        val_loss /= max(1, len(val_loader))
        action_acc = action_correct / max(1, val_size)
        print(f"Epoch {epoch:3d}/{args.epochs} | "
              f"train_loss={train_loss/max(1,len(train_loader)):.4f} | "
              f"val_loss={val_loss:.4f} | action_acc={action_acc:.3f}")

        if val_loss < best_val:
            best_val = val_loss
            patience = 0
            ckpt = {
                "epoch": epoch,
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "val_loss": val_loss,
                "action_acc": action_acc,
                "vocabs": {
                    "action":   ACTION_VOCAB,
                    "strategy": STRATEGY_VOCAB,
                    "role":     ROLE_VOCAB,
                    "site":     SITE_VOCAB,
                },
                "config": {"embed_dim": 64, "hidden": 128},
            }
            torch.save(ckpt, args.output)
            print(f"  [Saved] {args.output}  (val_loss={val_loss:.4f})")
        else:
            patience += 1
            if patience >= args.patience:
                print(f"[EarlyStop] No improvement for {args.patience} epochs.")
                break

    print(f"\n[Done] Best val_loss={best_val:.4f} | Checkpoint: {args.output}")
    return 0


def main():
    p = argparse.ArgumentParser(description="BrowserMind BC v2 Trainer")
    p.add_argument("--data",       default="training/dataset_v1.jsonl",
                   help="JSONL from `bm dataset export`.")
    p.add_argument("--output",     default="bc_v2_checkpoint.pt")
    p.add_argument("--epochs",     type=int, default=30)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr",         type=float, default=3e-4)
    p.add_argument("--patience",   type=int, default=5)
    p.add_argument(
        "--strategy-loss-weight", type=float, default=0.0,
        dest="strategy_loss_weight",
        help=(
            "Weight applied to the strategy_head loss term (default 0). "
            "Disabled by default: the current corpus has heavy action-to-strategy "
            "correlation so strategy_head memorises action_head rather than "
            "learning an independent predictor. Increase once the corpus contains "
            ">2000 diverse multi-strategy StrategyTrial records."
        ),
    )
    p.add_argument(
        "--min-value-score", type=float, default=0.0,
        dest="min_value_score",
        help=(
            "Minimum aggregate TaskValueScore required to include an episode "
            "in training (0.0 = no filter). Requires task_value_score field in "
            "the JSONL, written by `bm dataset export --score`."
        ),
    )
    args = p.parse_args()
    raise SystemExit(train(args) or 0)


if __name__ == "__main__":
    main()
