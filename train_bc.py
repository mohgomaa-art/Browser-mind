"""
BrowserMind  Phase 1: Behavioral Cloning
==========================================
Trains AgentPolicy on recorded human sessions.

Loss (Section 3):
  action_loss   = CrossEntropy(action_logits, expert_action_id)
  element_loss  = CrossEntropy(element_scores, expert_element_idx)  [only when idx is not None]
  total_loss    = weight * (action_loss + 0.5 * element_loss)

  success=True  -> weight = 1.0
  success=False -> weight = 0.1

Hyperparams (Section 3):
  optimizer:    AdamW(lr=3e-4, weight_decay=1e-4)
  batch_size:   32
  epochs:       10 (early stop: val_loss no improve for 3 epochs)
  grad_clip:    1.0

Checkpoint format: spec Section 9.

Usage:
  # Step 1  convert sessions to spec format
  python -m training.session_adapter --input training/sessions --output training/spec_sessions

  # Step 2  train
  python train_bc.py --data training/spec_sessions

  # Or with options
  python train_bc.py --data training/spec_sessions --epochs 10 --batch-size 32 \\
                     --ckpt browsermind_policy_v2.pt --resume
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from model.agent_policy import AgentPolicy
from training.graph_dataset import GraphDataset, GraphSample, collate_graph_samples


# ------------------------------------------------------------------------------
#  Loss computation (single sample  graphs have variable N)
# ------------------------------------------------------------------------------

def compute_loss(
    policy:  AgentPolicy,
    sample:  GraphSample,
    device:  torch.device,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """
    Computes weighted BC loss for one sample.
    Returns (loss_tensor, metrics_dict)
    """
    out = policy.forward(sample.nodes, sample.edges, sample.goal)

    # -- Action loss ----------------------------------------------------------
    action_target = torch.tensor([sample.action_id], dtype=torch.long, device=device)
    action_loss   = F.cross_entropy(out["action_logits"].unsqueeze(0), action_target)

    # -- Element loss (only when element_idx is not None AND success=True) ----
    element_loss = torch.tensor(0.0, device=device)
    if sample.element_idx is not None:
        n = out["element_scores"].shape[0]
        if sample.element_idx < n:
            elem_target  = torch.tensor([sample.element_idx], dtype=torch.long, device=device)
            element_loss = F.cross_entropy(
                out["element_scores"].unsqueeze(0), elem_target
            )

    total_loss = sample.weight * (action_loss + 0.5 * element_loss)

    # Accuracy signals (no grad)
    with torch.no_grad():
        pred_action  = int(out["action_logits"].argmax().item())
        action_correct = float(pred_action == sample.action_id)

        elem_acc1 = elem_acc3 = float("nan")
        if sample.element_idx is not None and out["element_scores"].shape[0] > 0:
            k      = min(3, out["element_scores"].shape[0])
            top3   = torch.topk(out["element_scores"], k).indices.tolist()
            top1   = top3[0] if top3 else -1
            elem_acc1 = float(top1 == sample.element_idx)
            elem_acc3 = float(sample.element_idx in top3)

    return total_loss, {
        "action_loss":   float(action_loss.item()),
        "element_loss":  float(element_loss.item()),
        "total_loss":    float(total_loss.item()),
        "action_correct": action_correct,
        "elem_acc1":     elem_acc1,
        "elem_acc3":     elem_acc3,
    }


# ------------------------------------------------------------------------------
#  Epoch helpers
# ------------------------------------------------------------------------------

def _accumulate_metrics(all_metrics: List[Dict]) -> Dict[str, float]:
    """Average all metrics across a list of per-sample dicts."""
    totals: Dict[str, float] = {}
    counts: Dict[str, int]   = {}
    for m in all_metrics:
        for k, v in m.items():
            if math.isnan(v):
                continue
            totals[k] = totals.get(k, 0.0) + v
            counts[k] = counts.get(k, 0) + 1
    return {k: totals[k] / counts[k] for k in totals if counts[k] > 0}


def run_epoch(
    policy:    AgentPolicy,
    dataset:   GraphDataset,
    optimizer: Optional[torch.optim.Optimizer],
    device:    torch.device,
    batch_size: int = 32,
    grad_clip:  float = 1.0,
    train:     bool = True,
) -> Dict[str, float]:
    """Run one full pass over the dataset. train=False -> eval mode."""
    if train:
        policy.train()
    else:
        policy.eval()

    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=train,
        collate_fn=collate_graph_samples,
        drop_last=False,
    )

    all_metrics: List[Dict] = []
    n_batches = len(dataloader)

    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for batch_idx, batch in enumerate(dataloader):
            batch_loss = torch.tensor(0.0, device=device, requires_grad=train)
            batch_metrics: List[Dict] = []

            for sample in batch:
                loss, metrics = compute_loss(policy, sample, device)
                batch_loss    = batch_loss + loss
                batch_metrics.append(metrics)

            if train and len(batch) > 0:
                optimizer.zero_grad()
                (batch_loss / len(batch)).backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), grad_clip)
                optimizer.step()

            all_metrics.extend(batch_metrics)

            if train and (batch_idx + 1) % max(1, n_batches // 5) == 0:
                partial = _accumulate_metrics(all_metrics)
                print(
                    f"    [{batch_idx+1:>3}/{n_batches}] "
                    f"loss={partial.get('total_loss', 0):.4f}  "
                    f"action_acc={partial.get('action_correct', 0):.3f}  "
                    f"elem@3={partial.get('elem_acc3', float('nan')):.3f}"
                )

    return _accumulate_metrics(all_metrics)


# ------------------------------------------------------------------------------
#  Main BC training function
# ------------------------------------------------------------------------------

def train_bc(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}")
    print(f"  BrowserMind  Phase 1: Behavioral Cloning")
    print(f"{'='*60}")
    print(f"  Data      : {args.data}")
    print(f"  Device    : {device}")
    print(f"  Epochs    : {args.epochs}")
    print(f"  Batch     : {args.batch_size}")
    print(f"  LR        : {args.lr}")
    print(f"  Checkpoint: {args.ckpt}")
    print(f"{'='*60}\n")

    report_path = Path(args.audit_report) if args.audit_report else Path(args.data) / "dataset_report.json"
    if not args.allow_unaudited:
        if not report_path.exists():
            print("\n[BLOCKED] dataset_report.json is required before training.")
            print(f"          Expected: {report_path}")
            print("          Run: python scripts/build_dataset_report.py --out "
                  f"{report_path} {args.data}")
            return
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            gate = report.get("training_gate", {})
            if gate and gate.get("training_allowed") is False:
                print("\n[BLOCKED] dataset_report.json failed training gates.")
                print(json.dumps(gate, indent=2, ensure_ascii=False))
                return
        except Exception as exc:
            print(f"\n[BLOCKED] Could not read dataset audit report: {exc}")
            return

        data_path = Path(args.data)
        gold_report_path = Path(args.gold_report) if args.gold_report else data_path / "gold_report.json"
        requires_gold_report = (
            gold_report_path.exists()
            or data_path.name.lower().startswith("gold")
            or (data_path / "samples.json").exists()
        )
        if requires_gold_report and not gold_report_path.exists():
            print("\n[BLOCKED] gold_report.json is required before training on gold/sample datasets.")
            print(f"          Expected: {gold_report_path}")
            print("          Run: python training/gold_dataset.py "
                  f"{args.data} --out-dir {args.data}")
            return

        if gold_report_path.exists():
            try:
                gold_report = json.loads(gold_report_path.read_text(encoding="utf-8"))
                evidence_coverage = float(gold_report.get("evidence_coverage", 0.0))
                accepted = int(gold_report.get("accepted_samples", 0))
                gold_gate = gold_report.get("gold_gate", {})
                if evidence_coverage < 0.95 or accepted <= 0 or gold_gate.get("passes") is False:
                    print("\n[BLOCKED] gold_report.json failed gold dataset gates.")
                    print(json.dumps({
                        "accepted_samples": accepted,
                        "evidence_coverage": evidence_coverage,
                        "required_evidence_coverage": 0.95,
                        "gold_gate": gold_gate,
                    }, indent=2, ensure_ascii=False))
                    return
            except Exception as exc:
                print(f"\n[BLOCKED] Could not read gold report: {exc}")
                return

            meta_report_path = (
                Path(args.meta_verifier_report)
                if args.meta_verifier_report
                else Path(args.data) / "meta_verifier_report.json"
            )
            if not meta_report_path.exists():
                print("\n[BLOCKED] meta_verifier_report.json is required before training on gold data.")
                print(f"          Expected: {meta_report_path}")
                print("          Run: python audits/meta_verifier.py "
                      f"{args.data} --out {meta_report_path}")
                return
            try:
                meta_report = json.loads(meta_report_path.read_text(encoding="utf-8"))
                quality_gates = meta_report.get("quality_gates", {})
                if quality_gates.get("passes") is not True:
                    print("\n[BLOCKED] meta_verifier_report.json failed verifier quality gates.")
                    print(json.dumps(quality_gates, indent=2, ensure_ascii=False))
                    return
            except Exception as exc:
                print(f"\n[BLOCKED] Could not read meta verifier report: {exc}")
                return

    # -- Datasets --------------------------------------------------------------
    train_ds = GraphDataset(
        args.data,
        split="train",
        val_ratio=args.val_ratio,
        seed=args.seed,
        augment=not args.no_augment,
    )
    val_ds = GraphDataset(
        args.data,
        split="val",
        val_ratio=args.val_ratio,
        seed=args.seed,
        augment=not args.no_augment,
    )
    train_ds.print_stats()
    val_ds.print_stats()

    if len(train_ds) == 0:
        print("\n[!] No training samples found.")
        print("    Run: python -m training.session_adapter --input training/sessions --output training/spec_sessions")
        return

    # -- Model + Optimizer -----------------------------------------------------
    policy    = AgentPolicy().to(device)
    optimizer = torch.optim.AdamW(
        policy.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    start_epoch = 0
    best_val_loss = float("inf")
    no_improve    = 0

    ckpt_path = Path(args.ckpt)

    if args.resume and ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=device)
        policy.load_state_dict(ckpt["model_state"])
        if ckpt.get("optimizer_state") and optimizer:
            optimizer.load_state_dict(ckpt["optimizer_state"])
        start_epoch   = ckpt.get("epoch", 0)
        best_val_loss = ckpt.get("_best_val_loss", float("inf"))
        print(f"  Resumed from {ckpt_path} (epoch {start_epoch})\n")

    print(f"  Trainable params: {policy.count_parameters():,}\n")

    # -- Training loop ---------------------------------------------------------
    for epoch in range(start_epoch, args.epochs):
        t0 = time.time()
        print(f"\n-- Epoch {epoch+1}/{args.epochs} ------------------------------------")

        train_metrics = run_epoch(
            policy, train_ds, optimizer, device,
            batch_size=args.batch_size, grad_clip=args.grad_clip, train=True
        )

        # Validation
        if len(val_ds) > 0:
            val_metrics = run_epoch(
                policy, val_ds, None, device,
                batch_size=args.batch_size, train=False
            )
        else:
            val_metrics = train_metrics

        elapsed = time.time() - t0

        # Print epoch summary
        print(
            f"\n  TRAIN  loss={train_metrics.get('total_loss', 0):.4f}  "
            f"action_acc={train_metrics.get('action_correct', 0):.3f}  "
            f"elem@1={train_metrics.get('elem_acc1', float('nan')):.3f}  "
            f"elem@3={train_metrics.get('elem_acc3', float('nan')):.3f}"
        )
        print(
            f"  VAL    loss={val_metrics.get('total_loss', 0):.4f}  "
            f"action_acc={val_metrics.get('action_correct', 0):.3f}  "
            f"elem@1={val_metrics.get('elem_acc1', float('nan')):.3f}  "
            f"elem@3={val_metrics.get('elem_acc3', float('nan')):.3f}  "
            f"({elapsed:.1f}s)"
        )

        val_loss     = val_metrics.get("total_loss", 0.0)
        val_acc      = val_metrics.get("action_correct", 0.0)
        val_elem_acc3 = val_metrics.get("elem_acc3", 0.0)

        # Checkpoint every 5 epochs
        if (epoch + 1) % 5 == 0:
            policy.save(
                path=str(ckpt_path).replace(".pt", f"_ep{epoch+1}.pt"),
                optimizer=optimizer,
                epoch=epoch + 1,
                phase="bc",
                val_action_acc=val_acc,
                val_element_acc3=val_elem_acc3,
            )

        # Best val checkpoint
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            no_improve    = 0
            extra = {"_best_val_loss": best_val_loss}
            policy.save(
                path=str(ckpt_path),
                optimizer=optimizer,
                epoch=epoch + 1,
                phase="bc",
                val_action_acc=val_acc,
                val_element_acc3=val_elem_acc3,
            )
            print(f"  [OK]  New best -> {ckpt_path}")
        else:
            no_improve += 1
            print(f"  [!]   No improvement ({no_improve}/{args.patience})")

        # Early-stop target for action accuracy (configurable for polish runs).
        if val_acc >= args.target_action_acc:
            print(
                f"\n  Target reached: val_action_acc={val_acc:.3f} "
                f">= {args.target_action_acc:.3f}"
            )
            break
        if no_improve >= args.patience:
            print(f"\n[stop]   Early stop: val_loss didn't improve for {args.patience} epochs")
            break

    print(f"\n{'='*60}")
    print(f"  Phase 1 complete.")
    print(f"  Best val_loss      : {best_val_loss:.4f}")
    print(f"  Checkpoint saved   : {ckpt_path}")
    print(f"  Next step          : python train_dagger.py --ckpt {ckpt_path}")
    print(f"{'='*60}\n")


# ------------------------------------------------------------------------------
#  CLI
# ------------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="BrowserMind Phase 1  Behavioral Cloning"
    )
    p.add_argument("--data",         default="training/spec_sessions",
                   help="Directory with spec-format JSON session files")
    p.add_argument("--ckpt",         default="browsermind_policy_v2.pt",
                   help="Output checkpoint path")
    p.add_argument("--resume",       action="store_true",
                   help="Resume from existing checkpoint")
    p.add_argument("--epochs",       type=int,   default=10)
    p.add_argument("--batch-size",   type=int,   default=32)
    p.add_argument("--lr",           type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--grad-clip",    type=float, default=1.0)
    p.add_argument("--patience",     type=int,   default=3,
                   help="Early-stop patience (epochs without val_loss improvement)")
    p.add_argument("--val-ratio",    type=float, default=0.2)
    p.add_argument("--seed",         type=int,   default=42)
    p.add_argument(
        "--target-action-acc",
        type=float,
        default=0.70,
        help="Stop training when validation action accuracy reaches this threshold",
    )
    p.add_argument(
        "--no-augment",
        action="store_true",
        help="Disable goal paraphrase augmentation (recommended for polishing on curated data)",
    )
    p.add_argument(
        "--audit-report",
        default="",
        help="Path to dataset_report.json. Defaults to <data>/dataset_report.json",
    )
    p.add_argument(
        "--gold-report",
        default="",
        help="Optional path to gold_report.json. Defaults to <data>/gold_report.json when present.",
    )
    p.add_argument(
        "--meta-verifier-report",
        default="",
        help="Optional path to meta_verifier_report.json. Defaults to <data>/meta_verifier_report.json when gold_report.json exists.",
    )
    p.add_argument(
        "--allow-unaudited",
        action="store_true",
        help="Bypass dataset_report.json gate for local experiments only.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train_bc(args)
