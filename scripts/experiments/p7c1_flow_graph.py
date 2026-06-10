# scripts/experiments/p7c1_flow_graph.py
"""P7C.1: Goal to Flow Graph Inference Evaluation.

Measures decomposition accuracy of the FlowInferenceEngine across 10 composite
unstructured user goals.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.inference import FlowInferenceEngine

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def main():
    print(f"\n========================================================")
    print(f" P7C.1: GOAL TO FLOW GRAPH DECOMPOSITION EVALUATION")
    print(f"========================================================\n")
    
    engine = FlowInferenceEngine()
    
    # 10 standard evaluation goals representing composite flows
    eval_set = [
        (
            "Buy a laptop under $1000", 
            ["SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"]
        ),
        (
            "Update my GitHub profile picture", 
            ["AUTH_FLOW", "PROFILE_FLOW"]
        ),
        (
            "Login and enable dark mode", 
            ["AUTH_FLOW", "SETTINGS_FLOW"]
        ),
        (
            "Find playwright and read reviews", 
            ["SEARCH_FLOW", "DISCOVERY_FLOW"]
        ),
        (
            "Navigate to my settings page and change password",
            ["AUTH_FLOW", "NAVIGATION_FLOW", "SETTINGS_FLOW"]
        ),
        (
            "Find a red shirt by size M and pay for it",
            ["SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"]
        ),
        (
            "Go to Wikipedia and discover news feed articles",
            ["NAVIGATION_FLOW", "DISCOVERY_FLOW"]
        ),
        (
            "Sign up to GitHub and update my bio description",
            ["AUTH_FLOW", "PROFILE_FLOW"]
        ),
        (
            "Search python syntax and view articles feed",
            ["SEARCH_FLOW", "DISCOVERY_FLOW"]
        ),
        (
            "Go to checkout cart page and pay for purchase",
            ["NAVIGATION_FLOW", "CHECKOUT_FLOW"]
        )
    ]
    
    results = []
    correct_count = 0
    
    for goal, expected in eval_set:
        graph = engine.infer_flow_graph(goal)
        is_correct = (graph == expected)
        if is_correct:
            correct_count += 1
        results.append({
            "goal": goal,
            "expected": expected,
            "inferred": graph,
            "status": "PASS" if is_correct else "FAIL"
        })
        
    accuracy = (correct_count / len(eval_set)) * 100
    
    print(f"[ Flow Graph Decomposition Matrix ]")
    print("-" * 110)
    print(f"| {'Goal':<48} | {'Expected Flow Graph':<25} | {'Inferred Flow Graph':<25} | {'Status':<6} |")
    print("-" * 110)
    for r in results:
        status_str = f"PASS" if r["status"] == "PASS" else "FAIL"
        exp_str = ", ".join([f.split("_")[0] for f in r["expected"]])
        inf_str = ", ".join([f.split("_")[0] for f in r["inferred"]])
        print(f"| {r['goal']:<48} | {exp_str:<25} | {inf_str:<25} | {status_str:<6} |")
    print("-" * 110)
    
    print(f"\nEvaluation Summary:")
    print(f"  Total Goals Evaluated: {len(eval_set)}")
    print(f"  Correct Decompositions: {correct_count}/{len(eval_set)}")
    print(f"  Decomposition Accuracy: {accuracy:.2f}%")
    
    if accuracy >= 90.0:
        print(f"\nVERDICT: SUCCESS. Decomposition Accuracy is {accuracy:.2f}% (>= 90%).")
        print("FlowInferenceEngine successfully decomposes goals to logical Flow Graph sequences.")
    else:
        print(f"\nVERDICT: FAILED. Decomposition accuracy fell below target.")
    print("========================================================\n")

if __name__ == "__main__":
    main()
