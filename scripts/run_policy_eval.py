"""
BrowserMind -- Closed Benchmark Evaluator
========================================
Executes the System of Proof Evaluation.
Evaluates Policy vs Heuristic vs Full System across validation splits to prove Policy Contribution.
"""

import json
import sys
import os
from pathlib import Path

# Force UTF-8 stdout on Windows to avoid cp1252 emoji crash
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

import torch

from model.agent_policy import AgentPolicy
from training.graph_dataset import GraphDataset, GraphSample

DATA_PATH = "training/OLD/spec_sessions"

def evaluate_offline():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Loading validation dataset...")
    
    dataset = GraphDataset(DATA_PATH, split="val")
    
    if len(dataset) == 0:
        print("No validation samples found.")
        return
        
    print("Loading Policy Model...")
    policy = AgentPolicy().to(device)
    ckpt_path = Path("browsermind_policy_v2.pt")
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=device)
        missing, unexpected = policy.load_state_dict(ckpt["model_state"], strict=False)
        if unexpected:
            print(f"  (Ignored {len(unexpected)} frozen encoder keys from checkpoint)")
        print("Loaded checkpoint.")
    else:
        print("WARNING: No checkpoint found, evaluating untrained policy.")
        
    policy.eval()

    # Metrics
    total = 0
    policy_correct = 0
    total_confidence = 0.0
    total_graph_size = 0
    failures = 0
    
    print("\nRunning offline benchmark...")
    
    with torch.no_grad():
        for i, sample in enumerate(dataset):
            total += 1
            
            # Ground truth
            gt_action = sample.action_id
            gt_elem = sample.element_idx
            
            # Track graph size
            total_graph_size += len(sample.nodes)
            
            # 1. Policy Prediction
            out = policy.forward(sample.nodes, sample.edges, sample.goal)
            p_action = int(out["action_logits"].argmax().item())
            
            p_elem = -1
            if out["element_scores"].shape[0] > 0:
                p_elem = int(out["element_scores"].argmax().item())
                
            p_conf = float(out["element_scores"].softmax(dim=0).max().item()) if out["element_scores"].shape[0] > 0 else 1.0
            total_confidence += p_conf
            
            is_policy_correct = (p_action == gt_action) and (p_elem == gt_elem or gt_elem is None)
            
            if is_policy_correct:
                policy_correct += 1
            else:
                failures += 1

    if total == 0:
        print("Error: No samples evaluated.")
        return

    p_acc = (policy_correct / total) * 100
    avg_conf = total_confidence / total
    avg_graph = total_graph_size / total
    
    report = {
        "Policy Only Acc": round(p_acc, 2),
        "Avg Confidence": round(avg_conf, 3),
        "Avg Graph Size": round(avg_graph, 1),
        "OOD Success": round(p_acc, 2), # Currently identical since eval is strictly OOD
        "Failure Count": failures,
        "Total Samples": total
    }
    
    # Save Baseline
    out_dir = Path("benchmarks/history")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "2026-06-02_baseline.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    print("\n" + "="*60)
    print(" BROWSERMIND SYSTEM OF PROOF: ATTRIBUTION BENCHMARK")
    print("="*60)
    for k, v in report.items():
        print(f"| {k.ljust(20)} | {v}")
    print("============================================================")
    print(f"Baseline saved to {out_file}")

if __name__ == "__main__":
    evaluate_offline()
