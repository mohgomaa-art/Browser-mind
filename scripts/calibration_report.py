from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.agent_policy import ACTION_TYPES, AgentPolicy
from training.graph_dataset import GraphDataset


def _ece(points: List[Dict], bins: int) -> tuple[float, List[Dict]]:
    if not points:
        return 0.0, []
    total = len(points)
    ece = 0.0
    curve = []
    for i in range(bins):
        lo = i / bins
        hi = (i + 1) / bins
        bucket = [
            p for p in points
            if (lo <= p["confidence"] < hi) or (i == bins - 1 and p["confidence"] <= hi)
        ]
        if not bucket:
            curve.append({"bin": i, "lo": lo, "hi": hi, "count": 0})
            continue
        acc = sum(p["correct"] for p in bucket) / len(bucket)
        conf = sum(p["confidence"] for p in bucket) / len(bucket)
        gap = abs(acc - conf)
        ece += (len(bucket) / total) * gap
        curve.append(
            {
                "bin": i,
                "lo": round(lo, 3),
                "hi": round(hi, 3),
                "count": len(bucket),
                "accuracy": round(acc, 4),
                "confidence": round(conf, 4),
                "gap": round(gap, 4),
            }
        )
    return ece, curve


@torch.no_grad()
def calibration_report(args) -> Dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    policy = AgentPolicy.load(args.ckpt, map_location=str(device)).to(device)
    dataset = GraphDataset(args.data, split=args.split, augment=args.augment)

    action_points: List[Dict] = []
    element_points: List[Dict] = []
    action_brier_total = 0.0
    element_brier_total = 0.0
    action_seen = 0
    element_seen = 0

    policy.eval()
    for idx, sample in enumerate(dataset.samples):
        if args.max_samples and idx >= args.max_samples:
            break
        out = policy.forward(sample.nodes, sample.edges, sample.goal)

        action_probs = F.softmax(out["action_logits"], dim=0)
        pred_action = int(action_probs.argmax().item())
        action_conf = float(action_probs[pred_action].item())
        action_correct = int(pred_action == sample.action_id)
        target = torch.zeros_like(action_probs)
        if 0 <= sample.action_id < target.numel():
            target[sample.action_id] = 1.0
        action_brier_total += float(torch.mean((action_probs - target) ** 2).item())
        action_seen += 1
        action_points.append({"confidence": action_conf, "correct": action_correct})

        if sample.element_idx is not None and out["element_scores"].numel() > 0:
            elem_probs = F.softmax(out["element_scores"], dim=0)
            pred_elem = int(elem_probs.argmax().item())
            elem_conf = float(elem_probs[pred_elem].item())
            elem_correct = int(pred_elem == sample.element_idx)
            elem_target = torch.zeros_like(elem_probs)
            if 0 <= sample.element_idx < elem_target.numel():
                elem_target[sample.element_idx] = 1.0
            element_brier_total += float(torch.mean((elem_probs - elem_target) ** 2).item())
            element_seen += 1
            element_points.append({"confidence": elem_conf, "correct": elem_correct})

    action_ece, action_curve = _ece(action_points, args.bins)
    element_ece, element_curve = _ece(element_points, args.bins)

    return {
        "checkpoint": args.ckpt,
        "data": args.data,
        "split": args.split,
        "samples": action_seen,
        "element_samples": element_seen,
        "action_ece": round(action_ece, 4),
        "action_brier": round(action_brier_total / max(action_seen, 1), 4),
        "action_accuracy": round(sum(p["correct"] for p in action_points) / max(len(action_points), 1), 4),
        "element_ece": round(element_ece, 4),
        "element_brier": round(element_brier_total / max(element_seen, 1), 4),
        "element_accuracy": round(sum(p["correct"] for p in element_points) / max(len(element_points), 1), 4),
        "fallback_threshold_gate": {
            "target_action_ece": 0.10,
            "passes": action_ece < 0.10,
            "rule": "Only reduce fallback threshold after calibration passes.",
        },
        "reliability_curve": {
            "action": action_curve,
            "element": element_curve,
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Compute ECE, Brier score, and reliability curves.")
    parser.add_argument("--ckpt", default="browsermind_policy_v2.pt")
    parser.add_argument("--data", default="training/OLD/spec_sessions")
    parser.add_argument("--split", default="val")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--augment", action="store_true")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = calibration_report(args)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
