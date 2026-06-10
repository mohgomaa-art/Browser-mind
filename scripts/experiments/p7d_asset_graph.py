# scripts/experiments/p7d_asset_graph.py
"""P7D: Asset Graph Compilation & Validation Benchmark.

Evaluates compilation accuracy of the AssetGraphResolver across 15 representative user goals.
Reports mapping correctness from user goal down to abstract Asset Types (email_account, credential_asset, etc.).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    print(f"\n========================================================")
    print(f" P7D: ASSET GRAPH COMPILATION & VALIDATION BENCHMARK")
    print(f"========================================================\n")

    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()

    # 15 test goals mapping to flows, requirement candidates, and abstract asset types
    dataset = [
        {
            "goal": "Change my GitHub password",
            "expected_assets": ["credential_asset", "session_token"],
            "rationale": "Password change settings require a valid logged-in session (session_token) and current credentials."
        },
        {
            "goal": "Enable dark mode on Reddit",
            "expected_assets": ["session_token"],
            "rationale": "Toggling public interface settings maps to session_token (validated or refuted at execution time)."
        },
        {
            "goal": "Buy a laptop under $1000 on WebArena",
            "expected_assets": ["payment_asset", "goal_context"],
            "rationale": "Product purchase requires payment credentials, and price filtering requires search parameters."
        },
        {
            "goal": "Create GitHub account",
            "expected_assets": ["identity_profile", "credential_asset"],
            "rationale": "Account registration requires identity details and password configurations."
        },
        {
            "goal": "Login to my Upwork account",
            "expected_assets": ["credential_asset"],
            "rationale": "Logging in requests account credentials from a vault."
        },
        {
            "goal": "Search python syntax",
            "expected_assets": ["goal_context"],
            "rationale": "Search queries derive from the goal_context."
        },
        {
            "goal": "Go to wikipedia.org",
            "expected_assets": ["goal_context"],
            "rationale": "Target navigation URLs derive from the goal_context."
        },
        {
            "goal": "Filter products by size XL",
            "expected_assets": ["goal_context"],
            "rationale": "Filter criteria derive from the goal_context."
        },
        {
            "goal": "Configure my Upwork profile bio",
            "expected_assets": ["session_token", "credential_asset"],
            "rationale": "Profile bio configuration requires auth session and profile access credentials."
        },
        {
            "goal": "Forgot my Reddit password",
            "expected_assets": ["email_account"],
            "rationale": "Password recovery requires access to email client (email_account)."
        },
        {
            "goal": "Modify settings configuration",
            "expected_assets": ["session_token"],
            "rationale": "Settings modification maps to session_token (session checking)."
        },
        {
            "goal": "Checkout my shopping cart items",
            "expected_assets": ["payment_asset", "goal_context"],
            "rationale": "Checkout requires payment methods and search queries for purchase verification."
        },
        {
            "goal": "Update profile picture",
            "expected_assets": ["session_token", "credential_asset"],
            "rationale": "Profile update requires session tokens and credentials."
        },
        {
            "goal": "Lost access to my Upwork profile",
            "expected_assets": ["session_token", "email_account"],
            "rationale": "Lost access to profile requires recovery email checks and login checks."
        },
        {
            "goal": "Search for freelancer and visit profile",
            "expected_assets": ["session_token", "credential_asset", "goal_context"],
            "rationale": "Searching and visiting profiles requires target URLs, query inputs, and profile access credentials."
        }
    ]

    print(f"{'Goal':<40} | {'Expected Asset Types':<35} | {'Extracted Asset Types':<35} | {'Match'}")
    print("-" * 123)

    correct_count = 0
    total_goals = len(dataset)

    for item in dataset:
        goal = item["goal"]
        expected = sorted(item["expected_assets"])
        
        # Extracted candidates
        flows = engine.infer_flow_graph(goal)
        candidates = engine.infer_requirement_candidates(goal, flows)
        
        # Compile graph and extract AssetType nodes
        graph = resolver.build_graph(goal, flows, candidates)
        extracted = []
        for name, data in graph.nodes.items():
            if data["type"] == "AssetType":
                extracted.append(name)
        extracted = sorted(list(set(extracted)))
        
        is_match = (expected == extracted)
        if is_match:
            correct_count += 1
            
        match_str = "PASS" if is_match else "FAIL"
        exp_str = ", ".join(expected)
        ext_str = ", ".join(extracted)
        
        print(f"{goal:<40} | {exp_str:<35} | {ext_str:<35} | {match_str}")
        if not is_match:
            print(f"  [WARNING] Rationale: {item['rationale']}")
            print(f"  [WARNING] Mismatch! Expected: {expected}, Got: {extracted}")

    accuracy = (correct_count / total_goals) * 100
    print("-" * 123)
    print(f"Asset Graph Compilation Accuracy: {correct_count}/{total_goals} ({accuracy:.2f}%)")
    print("========================================================\n")

    if accuracy >= 80.0:
        print(f"VERDICT: SUCCESS. P7D Asset Graph maps parameters successfully.")
        sys.exit(0)
    else:
        print(f"VERDICT: FAILED. Asset graph compilation accuracy fell below 80%.")
        sys.exit(1)


if __name__ == "__main__":
    main()
