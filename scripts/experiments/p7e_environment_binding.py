# scripts/experiments/p7e_environment_binding.py
"""P7E: Environment Binding & Ambiguity Validation Benchmark.

Evaluates EnvironmentBinder's context-aware mappings and explicit ambiguity detection (raising AmbiguousAssetError)
across 14 representative goals. Reports standard OS metrics: resolved, ambiguous, and incorrect counts.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder, AmbiguousAssetError

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    print(f"\n========================================================")
    print(f" P7E: ENVIRONMENT BINDING & AMBIGUITY BENCHMARK")
    print(f"========================================================\n")

    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()
    binder = EnvironmentBinder()

    # Evaluation dataset with clear context goals and deliberate ambiguous tasks
    dataset = [
        {
            "goal": "Forgot my personal GitHub password",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["gmail_primary"],
            "expected_environments": ["gmail"],
            "rationale": "Goal specifies 'personal' context, resolving to gmail_primary."
        },
        {
            "goal": "Forgot my work email password",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["outlook_work"],
            "expected_environments": ["outlook"],
            "rationale": "Goal specifies 'work' context, resolving to outlook_work."
        },
        {
            "goal": "Forgot my university portal password",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["gmail_school"],
            "expected_environments": ["gmail"],
            "rationale": "Goal specifies 'university' context, resolving to gmail_school."
        },
        {
            "goal": "Modify my secure recovery settings",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["vault_local", "session_active"],
            "expected_environments": ["credential_vault", "local_profile"],
            "rationale": "'secure' context resolves credentials to vault_local, session to session_active."
        },
        {
            "goal": "Modify my settings configuration on local vault",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["vault_local", "session_active"],
            "expected_environments": ["credential_vault", "local_profile"],
            "rationale": "'local' context resolves credential_asset to vault_local, session to session_active."
        },
        {
            "goal": "Update company password preferences",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["1password_work", "session_active"],
            "expected_environments": ["onepassword", "local_profile"],
            "rationale": "'company' context resolves credential_asset to 1password_work, session to session_active."
        },
        {
            "goal": "Buy a laptop on WebArena using my personal card",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["visa_personal"],
            "expected_environments": ["stripe_wallet"],
            "rationale": "'personal' context resolves payment_asset to visa_personal."
        },
        {
            "goal": "Checkout corporate cart on WebArena",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["amex_corporate"],
            "expected_environments": ["stripe_wallet"],
            "rationale": "'corporate' context resolves payment_asset to amex_corporate."
        },
        {
            "goal": "Create personal GitHub account",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["profile_personal", "vault_local"],
            "expected_environments": ["local_profile", "credential_vault"],
            "rationale": "'personal' context resolves vault to vault_local, profile is profile_personal."
        },
        {
            "goal": "Search python documentation",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["goal_parameters"],
            "expected_environments": ["user_prompt"],
            "rationale": "Only one goal_context asset exists, resolving directly without ambiguity."
        },
        {
            "goal": "Login to my corporate portal",
            "expected_outcome": "RESOLVED",
            "expected_instances": ["1password_work"],
            "expected_environments": ["onepassword"],
            "rationale": "'corporate' context resolves credentials to 1password_work."
        },
        {
            "goal": "Forgot my password",
            "expected_outcome": "AMBIGUOUS",
            "expected_instances": [],
            "expected_environments": [],
            "rationale": "No context is specified for email_account, triggering explicit AmbiguousAssetError."
        },
        {
            "goal": "Reset my credentials",
            "expected_outcome": "AMBIGUOUS",
            "expected_instances": [],
            "expected_environments": [],
            "rationale": "No context is specified for credential_vault, triggering explicit AmbiguousAssetError."
        },
        {
            "goal": "Buy a book",
            "expected_outcome": "AMBIGUOUS",
            "expected_instances": [],
            "expected_environments": [],
            "rationale": "No context is specified for payment card, triggering explicit AmbiguousAssetError."
        }
    ]

    metrics = {
        "asset_types": 0,
        "instances": 0,
        "resolved": 0,
        "ambiguous": 0,
        "incorrect": 0
    }

    print(f"{'Goal':<48} | {'Expected Outcome':<16} | {'Actual Outcome':<16} | {'Status'}")
    print("-" * 100)

    for item in dataset:
        goal = item["goal"]
        expected_outcome = item["expected_outcome"]
        
        # 1. Compile Asset Graph
        flows = engine.infer_flow_graph(goal)
        candidates = engine.infer_requirement_candidates(goal, flows)
        graph = resolver.build_graph(goal, flows, candidates)
        
        # Update metrics for asset types evaluated
        asset_types_in_graph = [n for n, d in graph.nodes.items() if d["type"] == "AssetType"]
        metrics["asset_types"] += len(asset_types_in_graph)

        actual_outcome = ""
        is_pass = False
        
        # 2. Try Binding Graph
        try:
            bound_graph = binder.bind_graph(graph, goal)
            actual_outcome = "RESOLVED"
            
            # Check correctness of bindings
            graph_dict = bound_graph.to_dict()
            bound_insts = [n for n, d in graph_dict["nodes"].items() if d["type"] == "AssetInstance"]
            bound_envs = [n for n, d in graph_dict["nodes"].items() if d["type"] == "Environment"]
            
            metrics["instances"] += len(bound_insts)
            
            is_correct = True
            for expected_inst in item["expected_instances"]:
                if expected_inst not in bound_insts:
                    is_correct = False
            for expected_env in item["expected_environments"]:
                if expected_env not in bound_envs:
                    is_correct = False
                    
            if is_correct:
                is_pass = (expected_outcome == "RESOLVED")
                if is_pass:
                    metrics["resolved"] += 1
            else:
                actual_outcome = f"INCORRECT_BINDING"
                metrics["incorrect"] += 1
                
        except AmbiguousAssetError as e:
            actual_outcome = "AMBIGUOUS"
            is_pass = (expected_outcome == "AMBIGUOUS")
            if is_pass:
                metrics["ambiguous"] += 1
            else:
                metrics["incorrect"] += 1
        except Exception as e:
            actual_outcome = f"ERROR: {type(e).__name__}"
            metrics["incorrect"] += 1

        status_str = "PASS" if is_pass else "FAIL"
        print(f"{goal:<48} | {expected_outcome:<16} | {actual_outcome:<16} | {status_str}")
        if not is_pass:
            print(f"  [WARNING] Rationale: {item['rationale']}")
            print(f"  [WARNING] Failed alignment: expected {expected_outcome}, got {actual_outcome}")

    print("-" * 100)
    print("\n========================================================")
    print(" P7E ENVIRONMENT BINDING METRICS SUMMARY")
    print("========================================================")
    print(f"Total Asset Types Processed: {metrics['asset_types']}")
    print(f"Total Asset Instances Bound: {metrics['instances']}")
    print(f"Successfully Resolved Tasks: {metrics['resolved']}")
    print(f"Correctly Flagged Ambiguous: {metrics['ambiguous']}")
    print(f"Incorrect / Failed Tasks   : {metrics['incorrect']}")
    print("========================================================\n")

    if metrics["incorrect"] == 0:
        print("VERDICT: SUCCESS. Environment Binder resolved context and ambiguity correctly.")
        sys.exit(0)
    else:
        print("VERDICT: FAILED. Evaluation errors encountered.")
        sys.exit(1)


if __name__ == "__main__":
    main()
