"""
P7G-B2.5 — Multi-Target Requirement Enumeration Test

Simulates the real scenario where `verification_code` maps to two 
target states: [email.opened, vault.otp_generated].
Both are present in the graph. The Planner must find ALL paths
across ALL target states and report them together.
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry


def build_full_verification_graph() -> AssetGraph:
    """
    Graph with BOTH email path and vault path available.
    All external assets are provided.
    """
    graph = AssetGraph()

    # External assets
    graph.add_node("email_account",    "AssetType")
    graph.add_node("goal_context",     "AssetType")
    graph.add_node("credential_asset", "AssetType")

    # Path A: email chain
    graph.add_node("search_email", "Capability", {
        "inputs": ["email_account", "goal_context"],
        "outputs": ["email_id"],
        "consumes_state": [],
        "produces_state": ["email.selected"]
    })
    graph.add_node("read_email", "Capability", {
        "inputs": ["email_id"],
        "outputs": ["email_content"],
        "consumes_state": ["email.selected"],
        "produces_state": ["email.opened"]
    })

    # Path B: vault chain
    graph.add_node("retrieve_credential", "Capability", {
        "inputs": ["credential_asset"],
        "outputs": ["credential_id"],
        "consumes_state": [],
        "produces_state": ["vault.credentials_unlocked"]
    })
    graph.add_node("generate_otp", "Capability", {
        "inputs": ["credential_id"],
        "outputs": ["otp_code"],
        "consumes_state": ["vault.credentials_unlocked"],
        "produces_state": ["vault.otp_generated"]
    })

    return graph


def enumerate_all_paths_for_requirement(requirement: str, graph: AssetGraph) -> dict:
    """
    Enumerates ALL candidate paths for a requirement by querying
    each of its target states independently and merging the results.
    """
    registry = RequirementStateRegistry()
    planner  = BackwardStatePlanner()

    target_states = registry.get_target_states(requirement)
    all_candidate_paths = []
    binding_failures  = []    # missing_states (structural — a target state has no producer)
    planning_failures = []    # missing_assets (data — a structural path fails data verification)

    per_state_results = {}
    for t_state in target_states:
        res = planner.check_reachability(t_state, graph)
        per_state_results[t_state] = res

        if res["reachable"]:
            for path in res["candidate_paths"]:
                if path not in all_candidate_paths:
                    all_candidate_paths.append(path)
        else:
            binding_failures.extend(res.get("missing_states", []))
            planning_failures.extend(res.get("missing_assets", []))

    return {
        "requirement": requirement,
        "target_states_checked": target_states,
        "total_candidate_paths": len(all_candidate_paths),
        "candidate_paths": all_candidate_paths,
        "binding_failures":  list(set(binding_failures)),   # states with no producer
        "planning_failures": list(set(planning_failures)),  # missing assets
        "per_state": per_state_results,
    }


def main():
    print("=" * 60)
    print("  P7G-B2.5  Multi-Target Requirement Enumeration")
    print("=" * 60)

    graph = build_full_verification_graph()
    result = enumerate_all_paths_for_requirement("verification_code", graph)

    print(f"\nRequirement: {result['requirement']}")
    print(f"Target states checked: {result['target_states_checked']}")
    print(f"Total candidate paths: {result['total_candidate_paths']}")
    print()
    for i, path in enumerate(result["candidate_paths"]):
        print(f"  Path {i+1}: {' -> '.join(path)}")
    print()
    print(f"binding_failures  (states with no producer): {result['binding_failures']}")
    print(f"planning_failures (data/asset missing)      : {result['planning_failures']}")

    # Per-state breakdown
    print("\nPer-state results:")
    for state, res in result["per_state"].items():
        status = "REACHABLE" if res["reachable"] else "UNREACHABLE"
        paths  = [" -> ".join(p) for p in res["candidate_paths"]]
        print(f"  {state}: {status} — paths={paths}")

    # Assertions
    assert result["total_candidate_paths"] == 2, (
        f"Expected 2 candidate paths, got {result['total_candidate_paths']}"
    )
    paths_flat = [" -> ".join(p) for p in result["candidate_paths"]]
    assert "search_email -> read_email"             in paths_flat, "Email path missing"
    assert "retrieve_credential -> generate_otp"    in paths_flat, "Vault path missing"
    assert result["binding_failures"]  == [],  f"Unexpected binding failures: {result['binding_failures']}"
    assert result["planning_failures"] == [],  f"Unexpected planning failures: {result['planning_failures']}"

    print("\n[PASS] All multi-target enumeration assertions passed.")
    print("[PASS] binding_failures and planning_failures are correctly separated.")
    print("[CONFIRMED] Planner finds ALL paths across ALL target states.")


if __name__ == "__main__":
    main()
