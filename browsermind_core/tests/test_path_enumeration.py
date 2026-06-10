"""
P7G-B2.5 — Path Enumeration Indictment Test

Builds a graph with THREE independent paths to the same target states:
  email.opened   <- Path A: search_email -> read_email
  vault.otp_generated <- Path B: retrieve_credential -> generate_otp

Both are valid target states for `verification_code`.

Then asks check_reachability for each and asserts that
ALL structural paths are returned, not just one.
"""
import sys
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import AssetGraph
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner


def build_multi_path_graph() -> AssetGraph:
    """
    Graph with two full capability chains reaching different target states.
    Both chains are provided with all required external assets.
    """
    graph = AssetGraph()

    # External assets
    graph.add_node("email_account",    "AssetType")
    graph.add_node("goal_context",     "AssetType")
    graph.add_node("credential_asset", "AssetType")
    graph.add_node("credential_id",    "AssetType")   # output of retrieve_credential, treat as asset

    # Path A: search_email -> read_email  (produces email.opened)
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

    # Path B: retrieve_credential -> generate_otp  (produces vault.otp_generated)
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


def build_convergent_graph() -> AssetGraph:
    """
    Graph where TWO independent capabilities both produce the SAME target state.
    This tests whether the planner finds both producers of a single state.

    Path A: search_email -> read_email -> email.opened
    Path B: archive_search -> archive_read -> email.opened  (a hypothetical second email client)
    """
    graph = AssetGraph()
    graph.add_node("email_account",    "AssetType")
    graph.add_node("goal_context",     "AssetType")

    # Path A (gmail)
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

    # Path B (a second email client: archive-style access)
    graph.add_node("archive_search", "Capability", {
        "inputs": ["email_account"],
        "outputs": ["archive_email_id"],
        "consumes_state": [],
        "produces_state": ["archive.email.selected"]
    })
    graph.add_node("archive_read", "Capability", {
        "inputs": ["archive_email_id"],
        "outputs": ["archive_email_content"],
        "consumes_state": ["archive.email.selected"],
        "produces_state": ["email.opened"]   # same target state
    })

    return graph


def run_test(name: str, graph: AssetGraph, target_state: str, expected_path_count: int):
    planner = BackwardStatePlanner()
    result = planner.check_reachability(target_state, graph)

    print(f"\n  [{name}] target_state={target_state}")
    print(f"    reachable       : {result['reachable']}")
    print(f"    candidate_paths : {result['candidate_paths']}")
    print(f"    missing_states  : {result['missing_states']}")
    print(f"    missing_assets  : {result['missing_assets']}")

    actual = len(result["candidate_paths"])
    if actual == expected_path_count:
        print(f"    [PASS] Found {actual}/{expected_path_count} expected paths.")
    else:
        print(f"    [FAIL] Expected {expected_path_count} paths, found {actual}.")
        sys.exit(1)


def main():
    print("=" * 60)
    print("  P7G-B2.5  Path Enumeration Indictment Test")
    print("=" * 60)

    # Test 1: Two independent targets from separate graphs
    # We test each target state independently — each has exactly 1 valid path.
    g1 = build_multi_path_graph()
    run_test("Path-A: email chain",   g1, "email.opened",       expected_path_count=1)
    run_test("Path-B: vault chain",   g1, "vault.otp_generated", expected_path_count=1)

    # Test 2: Two DIFFERENT capabilities producing the SAME target state
    # This is the real convergence test — the planner must find BOTH paths.
    g2 = build_convergent_graph()
    run_test("Convergent: two paths to email.opened", g2, "email.opened", expected_path_count=2)

    print("\n[ALL ENUMERATION TESTS PASSED]")


if __name__ == "__main__":
    main()
