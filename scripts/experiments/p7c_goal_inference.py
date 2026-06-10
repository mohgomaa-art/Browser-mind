# scripts/experiments/p7c_goal_inference.py
"""P7C Goal to Flow Inference Evaluation.

Measures classification accuracy of the FlowInferenceEngine across 16 representative
unstructured user goals across all 8 flow domains.
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
    print(f" P7C: GOAL TO FLOW INFERENCE EVALUATION")
    print(f"========================================================\n")
    
    engine = FlowInferenceEngine()
    
    # 16 standard evaluation goals representing all 8 domains
    eval_set = [
        # Search
        ("Find microsoft/playwright repository", "SEARCH_FLOW"),
        ("Query python list comprehension syntax", "SEARCH_FLOW"),
        # Navigation
        ("Go to the Wikipedia homepage", "NAVIGATION_FLOW"),
        ("Navigate to github.com main view", "NAVIGATION_FLOW"),
        # Discovery
        ("Read the latest article feed", "DISCOVERY_FLOW"),
        ("Discover trending news stories", "DISCOVERY_FLOW"),
        # Filtering
        ("Filter shop catalog by XL sizes", "FILTERING_FLOW"),
        ("Sort products list by price range", "FILTERING_FLOW"),
        # Checkout
        ("Checkout my shopping cart items", "CHECKOUT_FLOW"),
        ("Buy this laptop product", "CHECKOUT_FLOW"),
        # Settings
        ("Enable dark mode in my settings page", "SETTINGS_FLOW"),
        ("Change password preferences", "SETTINGS_FLOW"),
        # Profile
        ("Update bio details on profile page", "PROFILE_FLOW"),
        ("Change profile picture details", "PROFILE_FLOW"),
        # Auth
        ("Login to my security account", "AUTH_FLOW"),
        ("Logout from my active session", "AUTH_FLOW"),
    ]
    
    results = []
    correct_count = 0
    
    for goal, expected in eval_set:
        flow, confidence = engine.infer_flow(goal)
        is_correct = (flow == expected)
        if is_correct:
            correct_count += 1
        results.append({
            "goal": goal,
            "expected": expected,
            "inferred": flow,
            "confidence": confidence,
            "status": "PASS" if is_correct else "FAIL"
        })
        
    accuracy = (correct_count / len(eval_set)) * 100
    
    print(f"[ Goal Inference Matrix ]")
    print("-" * 100)
    print(f"| {'Goal':<38} | {'Expected Flow':<17} | {'Inferred Flow':<17} | {'Conf.':<6} | {'Status':<6} |")
    print("-" * 100)
    for r in results:
        status_str = f"PASS" if r["status"] == "PASS" else "FAIL"
        print(f"| {r['goal']:<38} | {r['expected']:<17} | {r['inferred']:<17} | {r['confidence']:<6.2f} | {status_str:<6} |")
    print("-" * 100)
    
    print(f"\nEvaluation Summary:")
    print(f"  Total Goals Evaluated: {len(eval_set)}")
    print(f"  Correct Classifications: {correct_count}/{len(eval_set)}")
    print(f"  Goal Classification Accuracy: {accuracy:.2f}%")
    
    if accuracy >= 90.0:
        print(f"\nVERDICT: SUCCESS. Goal Classification Accuracy is {accuracy:.2f}% (>= 90%).")
        print("FlowInferenceEngine successfully resolves raw goals to structured Flow Domains.")
    else:
        print(f"\nVERDICT: FAILED. Classification accuracy fell below target.")
    print("========================================================\n")

if __name__ == "__main__":
    main()
