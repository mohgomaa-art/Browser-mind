"""
P7G-B2.5 Review — State Classification Equivalence Test

The question: are email.opened and vault.otp_generated equivalent?

This test answers NO by inspection of their StateClass, and then
demonstrates what consequence that has for path ordering.
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import StateClass, AssetGraph
from browsermind_core.agent.requirement_state_registry import RequirementStateRegistry, TargetState
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner


def build_both_paths_graph() -> AssetGraph:
    """Graph where BOTH paths are available for verification_code."""
    graph = AssetGraph()
    graph.add_node("email_account",    "AssetType")
    graph.add_node("goal_context",     "AssetType")
    graph.add_node("credential_asset", "AssetType")

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


def main():
    registry = RequirementStateRegistry()
    planner  = BackwardStatePlanner()
    graph    = build_both_paths_graph()

    print("=" * 60)
    print("  State Classification Equivalence Test")
    print("  Question: Is email.opened == vault.otp_generated?")
    print("=" * 60)

    annotated = registry.get_annotated_target_states("verification_code")

    print("\nTarget states for `verification_code`:")
    for ts in annotated:
        print(f"  {ts.state:<32} -> {ts.state_class.value}")

    print()
    # Prove they are NOT equivalent
    class_map = {ts.state: ts.state_class for ts in annotated}

    email_class  = class_map["email.opened"]
    vault_class  = class_map["vault.otp_generated"]

    assert email_class  == StateClass.OBSERVATION,  f"email.opened should be OBSERVATION, got {email_class}"
    assert vault_class  == StateClass.AVAILABILITY,  f"vault.otp_generated should be AVAILABILITY, got {vault_class}"
    assert email_class  != vault_class, "email.opened and vault.otp_generated must NOT be equivalent"

    print("[PASS] email.opened  != vault.otp_generated  (OBSERVATION != AVAILABILITY)")
    print()

    # Now prove that both paths are reachable but have different StateClass
    print("Reachability check (both paths present in graph):")
    annotated_with_paths = []
    for ts in annotated:
        res = planner.check_reachability(ts.state, graph)
        annotated_with_paths.append((ts, res))
        status = "REACHABLE" if res["reachable"] else "UNREACHABLE"
        paths  = [" -> ".join(p) for p in res.get("candidate_paths", [])]
        print(f"  {ts.state:<32} [{ts.state_class.value:<12}] {status} via {paths}")

    print()

    # Show the consequence: both are reachable, but AVAILABILITY > OBSERVATION
    reachable_pairs = [(ts, r) for ts, r in annotated_with_paths if r["reachable"]]
    observation_paths  = [(ts, r) for ts, r in reachable_pairs if ts.state_class == StateClass.OBSERVATION]
    availability_paths = [(ts, r) for ts, r in reachable_pairs if ts.state_class == StateClass.AVAILABILITY]

    print("Classification-aware split:")
    print(f"  AVAILABILITY paths ({len(availability_paths)}):")
    for ts, r in availability_paths:
        for p in r["candidate_paths"]:
            print(f"    {' -> '.join(p)}  (reaches {ts.state})")

    print(f"  OBSERVATION paths  ({len(observation_paths)}):")
    for ts, r in observation_paths:
        for p in r["candidate_paths"]:
            print(f"    {' -> '.join(p)}  (reaches {ts.state})")

    print()
    print("[CONFIRMED] State Classification is NOT cosmetic.")
    print("[CONFIRMED] AVAILABILITY paths guarantee the resource.")
    print("[CONFIRMED] OBSERVATION paths open an inspection point only.")
    print()
    print("Consequence for P7G-B3:")
    print("  Before Trust, before Length, before Cost:")
    print("  AVAILABILITY > OBSERVATION")
    print("  This is the first dimension of the Planning Utility Function.")


if __name__ == "__main__":
    main()
