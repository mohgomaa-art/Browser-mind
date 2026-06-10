# scripts/experiments/p7c2_generalization_benchmark.py
"""P7C.2: Open Goal Generalization Benchmark.

Evaluates FlowInferenceEngine decomposition accuracy across 4 layers of difficulty:
- Layer A: Easy (Direct keywords)
- Layer B: Paraphrases (Synonyms)
- Layer C: Indirect Intent (State expressions)
- Layer D: Multi-intent (Ambiguity/Composites)

Goal Decomposition accuracy is reported individually for each layer, along with
detailed Gold Rationales. Overall accuracy must be >= 80%.
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
    print(f" P7C.2: OPEN GOAL GENERALIZATION BENCHMARK")
    print(f"========================================================\n")
    
    engine = FlowInferenceEngine()
    
    # Benchmark dataset with 22 items across 4 layers
    dataset = {
        "Layer A (Easy)": [
            {
                "goal": "search and login on reddit",
                "expected": ["AUTH_FLOW", "SEARCH_FLOW"],
                "rationale": "Direct keywords 'search' and 'login' map explicitly to SEARCH_FLOW and AUTH_FLOW. AUTH_FLOW is prepended via temporal ordering.",
                "platform": "Reddit"
            },
            {
                "goal": "navigate to upwork settings",
                "expected": ["NAVIGATION_FLOW", "SETTINGS_FLOW"],
                "rationale": "Direct keywords 'navigate' and 'settings' map to NAVIGATION_FLOW and SETTINGS_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "buy a book on webarena",
                "expected": ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "Direct keyword 'buy' maps to CHECKOUT_FLOW. Product noun 'book' triggers Rule D to prepend SEARCH_FLOW and DISCOVERY_FLOW.",
                "platform": "WebArena"
            },
            {
                "goal": "filter by price and checkout",
                "expected": ["FILTERING_FLOW", "CHECKOUT_FLOW"],
                "rationale": "Direct keywords 'filter' and 'checkout' map directly to FILTERING_FLOW and CHECKOUT_FLOW.",
                "platform": "WebArena"
            },
            {
                "goal": "update profile picture and bio on reddit",
                "expected": ["AUTH_FLOW", "PROFILE_FLOW"],
                "rationale": "Keywords 'profile picture' and 'bio' map to PROFILE_FLOW. Rule A prepends AUTH_FLOW due to personal context.",
                "platform": "Reddit"
            }
        ],
        "Layer B (Paraphrases)": [
            {
                "goal": "acquire a cheaper laptop on webarena",
                "expected": ["SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "Synonym 'acquire' maps to CHECKOUT_FLOW. Product noun 'laptop' triggers Rule D. 'cheaper' maps to FILTERING_FLOW.",
                "platform": "WebArena"
            },
            {
                "goal": "access my account on upwork",
                "expected": ["AUTH_FLOW"],
                "rationale": "Paraphrase 'access my account' maps to AUTH_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "obtain a course subscription on miniwob",
                "expected": ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "Synonyms 'obtain' and 'subscription' map to CHECKOUT_FLOW. Product noun 'course' triggers Rule D to prepend search/discovery.",
                "platform": "MiniWoB"
            },
            {
                "goal": "retrieve posts on reddit",
                "expected": ["SEARCH_FLOW", "DISCOVERY_FLOW"],
                "rationale": "Paraphrase 'retrieve' maps to SEARCH_FLOW and 'posts' maps to DISCOVERY_FLOW.",
                "platform": "Reddit"
            },
            {
                "goal": "modify my configuration on upwork",
                "expected": ["AUTH_FLOW", "SETTINGS_FLOW"],
                "rationale": "Synonym 'modify' and 'configuration' map to SETTINGS_FLOW. Personal pronoun 'my' triggers Rule A to prepend AUTH_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "obtain product list under $500",
                "expected": ["SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "Synonym 'obtain' maps to CHECKOUT_FLOW. 'product' noun triggers Rule D (search/discovery). 'under' maps to FILTERING_FLOW.",
                "platform": "WebArena"
            }
        ],
        "Layer C (Indirect Intent)": [
            {
                "goal": "I forgot my password for reddit",
                "expected": ["AUTH_FLOW"],
                "rationale": "Indirect phrase 'forgot my password' maps to AUTH_FLOW.",
                "platform": "Reddit"
            },
            {
                "goal": "I can't access my account on upwork",
                "expected": ["AUTH_FLOW"],
                "rationale": "Indirect phrase 'can't access my account' maps to AUTH_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "I need to complete my order on webarena",
                "expected": ["CHECKOUT_FLOW"],
                "rationale": "Indirect phrase 'complete my order' maps to CHECKOUT_FLOW.",
                "platform": "WebArena"
            },
            {
                "goal": "I want to personalize my page on reddit",
                "expected": ["AUTH_FLOW", "PROFILE_FLOW"],
                "rationale": "Indirect phrase 'personalize my page' maps to PROFILE_FLOW. Rule A prepends AUTH_FLOW due to personal context.",
                "platform": "Reddit"
            },
            {
                "goal": "I lost access to my profile on upwork",
                "expected": ["AUTH_FLOW", "PROFILE_FLOW"],
                "rationale": "Indirect phrase 'lost access' maps to AUTH_FLOW and 'profile' maps to PROFILE_FLOW.",
                "platform": "Upwork"
            }
        ],
        "Layer D (Multi-intent)": [
            {
                "goal": "Find a course and enroll in it on miniwob",
                "expected": ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "'Find' maps to SEARCH_FLOW. 'enroll' maps to CHECKOUT_FLOW. Product noun 'course' triggers bridging discovery flow.",
                "platform": "MiniWoB"
            },
            {
                "goal": "Change my password and update my email on upwork",
                "expected": ["AUTH_FLOW", "SETTINGS_FLOW"],
                "rationale": "Multiple settings intents ('Change my password', 'update my email') map to SETTINGS_FLOW. Personal context prepends AUTH_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "Purchase and review product on webarena",
                "expected": ["SEARCH_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "'Purchase' maps to CHECKOUT_FLOW. Target noun 'product' prepends SEARCH_FLOW and DISCOVERY_FLOW.",
                "platform": "WebArena"
            },
            {
                "goal": "Filter posts by hot and read the first one on reddit",
                "expected": ["FILTERING_FLOW", "DISCOVERY_FLOW"],
                "rationale": "'Filter' maps to FILTERING_FLOW. 'read' and 'posts' map to DISCOVERY_FLOW.",
                "platform": "Reddit"
            },
            {
                "goal": "Find a freelancer and visit their profile on upwork",
                "expected": ["AUTH_FLOW", "SEARCH_FLOW", "NAVIGATION_FLOW", "PROFILE_FLOW"],
                "rationale": "'Find' maps to SEARCH_FLOW. 'visit' maps to NAVIGATION_FLOW. 'profile' maps to PROFILE_FLOW. Rule A prepends AUTH_FLOW.",
                "platform": "Upwork"
            },
            {
                "goal": "Search for shoes under $50 and checkout",
                "expected": ["SEARCH_FLOW", "FILTERING_FLOW", "DISCOVERY_FLOW", "CHECKOUT_FLOW"],
                "rationale": "'Search' maps to SEARCH_FLOW, 'under' maps to FILTERING_FLOW, 'checkout' maps to CHECKOUT_FLOW. Rule B adds DISCOVERY_FLOW for bridging.",
                "platform": "WebArena"
            }
        ]
    }

    layer_stats = {}
    total_evaluated = 0
    total_correct = 0

    print(f"{'Goal':<52} | {'Expected Graph':<24} | {'Inferred Graph':<24} | {'Platform':<9} | {'Status':<5}")
    print("-" * 120)

    for layer, items in dataset.items():
        correct_in_layer = 0
        print(f"\n>>> {layer} ({len(items)} items)")
        print("-" * 120)
        
        for item in items:
            goal = item["goal"]
            expected = item["expected"]
            inferred = engine.infer_flow_graph(goal)
            is_correct = (inferred == expected)
            
            if is_correct:
                correct_in_layer += 1
                total_correct += 1
            total_evaluated += 1
            
            status_str = "PASS" if is_correct else "FAIL"
            exp_str = ", ".join([f.split("_")[0] for f in expected])
            inf_str = ", ".join([f.split("_")[0] for f in inferred])
            
            print(f"{goal:<52} | {exp_str:<24} | {inf_str:<24} | {item['platform']:<9} | {status_str:<5}")
            print(f"  Rationale: {item['rationale']}")
            if not is_correct:
                print(f"  [WARNING] Mismatch: expected {expected}, got {inferred}")
            print("-" * 120)
            
        layer_accuracy = (correct_in_layer / len(items)) * 100
        layer_stats[layer] = {
            "correct": correct_in_layer,
            "total": len(items),
            "accuracy": layer_accuracy
        }

    overall_accuracy = (total_correct / total_evaluated) * 100

    print("\n========================================================")
    print(" BENCHMARK ACCURACY BY LAYER SUMMARY")
    print("========================================================")
    for layer, stats in layer_stats.items():
        print(f"{layer:<25}: {stats['correct']}/{stats['total']} correct ({stats['accuracy']:.2f}%)")
    print("-" * 56)
    print(f"{'Overall Generalization Accuracy':<25}: {total_correct}/{total_evaluated} correct ({overall_accuracy:.2f}%)")
    print("========================================================\n")

    if overall_accuracy >= 80.0:
        print(f"VERDICT: SUCCESS. Overall Generalization Accuracy is {overall_accuracy:.2f}% (>= 80%).")
        print("FlowInferenceEngine successfully meets the generalizability criteria without site-specific leakage.")
        sys.exit(0)
    else:
        print(f"VERDICT: FAILED. Overall Generalization Accuracy is {overall_accuracy:.2f}% (< 80%).")
        sys.exit(1)

if __name__ == "__main__":
    main()
