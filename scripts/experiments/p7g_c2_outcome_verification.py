"""
P7G-C2: Outcome Verification Experiment

Answers the crucial question: "How often was the planner wrong?"
Simulates 100 execution contexts to measure Planner Quality vs Reality.
"""
import sys
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.path_utility import PathUtilityScorer
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry
from browsermind_core.execution.outcome_verifier import OutcomeVerifier
from browsermind_core.execution.execution_coordinator import ExecutionCoordinator
from scripts.experiments.execution_simulator import ExecutionSimulator

def build_verification_graph() -> AssetGraph:
    """Builds a static graph for `verification_code`."""
    graph = AssetGraph()
    assets = ["email_account", "goal_context", "credential_asset"]
    for a in assets: graph.add_node(a, "AssetType")

    # Path 2: Email (OBSERVATION)
    graph.add_node("search_email", "Capability", {"inputs": ["email_account", "goal_context"], "outputs": ["email_id"], "consumes_state": [], "produces_state": ["email.selected"]})
    graph.add_node("read_email", "Capability", {"inputs": ["email_id"], "outputs": ["email_content"], "consumes_state": ["email.selected"], "produces_state": ["email.opened"]})

    # Path 1: Vault (AVAILABILITY)
    graph.add_node("retrieve_credential", "Capability", {"inputs": ["credential_asset"], "outputs": ["credential_id"], "consumes_state": [], "produces_state": ["vault.credentials_unlocked"]})
    graph.add_node("generate_otp", "Capability", {"inputs": ["credential_id"], "outputs": ["otp_code"], "consumes_state": ["vault.credentials_unlocked"], "produces_state": ["vault.otp_generated"]})

    return graph


def run_outcome_verification():
    planner = BackwardStatePlanner()
    scorer = PathUtilityScorer()
    registry = RequirementStateRegistry()
    
    graph = build_verification_graph()
    requirement = "verification_code"
    
    # --- 1. Planning Phase (Prediction) ---
    target_states = registry.get_target_states(requirement)
    all_paths = []
    path_state_map = {}
    for t_state in target_states:
        res = planner.check_reachability(t_state, graph)
        if res["reachable"]:
            for p in res["candidate_paths"]:
                if tuple(p) not in all_paths:
                    all_paths.append(tuple(p))
                    path_state_map[tuple(p)] = t_state
                    
    scored_paths = []
    for p in all_paths:
        score = scorer.score_path(list(p), path_state_map[p], graph)
        scored_paths.append((p, score))
        
    scored_paths.sort(key=lambda x: scorer.get_sort_key(x[1]), reverse=True)
    ranked_paths = [list(p[0]) for p in scored_paths]
    
    # --- 2. Execution Phase (Reality) ---
    verifier = OutcomeVerifier()
    coordinator = ExecutionCoordinator(verifier)
    
    execution_context = {
        "validation_contract": {
            "required_keys": ["otp"],
            "constraints": {
                "expired": False
            }
        }
    }
    
    stats = {
        "executions": 100,
        "rank1_success": 0,
        "fallback_success": 0,
        "complete_failure": 0
    }
    
    print("======================================================")
    print("  P7G-C2: Planner Quality vs Reality (100 Executions)")
    print("======================================================")

    for i in range(stats["executions"]):
        # Simulate Reality: Vault OTP is valid 70% of the time. Email OTP is valid 80% of the time.
        vault_valid = random.random() < 0.70
        email_valid = random.random() < 0.80
        
        vault_artifact = {"otp": "123456", "expired": not vault_valid}
        email_artifact = {"otp": "654321", "expired": not email_valid} if email_valid else {} # Missing artifact if false randomly

        mock_scenarios = {
            ("retrieve_credential", "generate_otp"): vault_artifact,
            ("search_email", "read_email"): email_artifact
        }
        
        simulator = ExecutionSimulator(mock_scenarios)
        
        # Execute Coordinator (Strict Boundary: No Planner calls)
        result = coordinator.execute_with_fallback(ranked_paths, simulator, execution_context)
        
        if result["success"]:
            if result["resolved_at_rank"] == 1:
                stats["rank1_success"] += 1
            else:
                stats["fallback_success"] += 1
        else:
            stats["complete_failure"] += 1

    print(json.dumps(stats, indent=2))
    
    # Save Report
    with open("p7g_c2_planner_quality_report.json", "w") as f:
        json.dump(stats, f, indent=2)

if __name__ == "__main__":
    run_outcome_verification()
