# scripts/experiments/p7g_capability_dependency.py
"""
P7G-A: Capability Dependency Planner — Benchmark

Measures:
    - dependency_paths   : how many (provider, consumer) pairs were found
    - unsatisfied_inputs : inputs that no capability in the graph produces
    - cycles_detected    : whether the dependency graph is acyclic
    - max_depth          : longest capability chain

Success criteria:
    NOT "how many goals were resolved"
    BUT "how accurately the dependency graph was built"

This benchmark runs the full pipeline (Goal → Capability) for each test
goal, then hands the capability-enriched graph to CapabilityDependencyPlanner.
"""
import sys
import json

sys.path.insert(0, ".")

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine
from browsermind_core.agent.capability_dependency_planner import CapabilityDependencyPlanner


# ── Test goals ──────────────────────────────────────────────────────────────

TEST_GOALS = [
    # Auth / credential chain goals (should produce search_email → read_email)
    "Reset my GitHub password via email",
    "Log in to Slack using 2FA",
    "Sign in to my corporate VPN with 2FA",

    # Checkout / payment goals (wallet capabilities should appear)
    "Buy a laptop on WebArena using my personal card",
    "Checkout corporate cart on WebArena",

    # Profile / identity goals
    "Update my shipping address on Amazon",
    "Change my display name on GitHub",

    # Search / navigation goals (context_bridge should appear)
    "Find the cheapest flight from Cairo to Dubai",
    "Search for Python books on O'Reilly",

    # Mixed goals
    "Book a hotel in Paris and pay with my work card",
    "Download my invoice from last month",
]


# ── Pipeline helpers ─────────────────────────────────────────────────────────

def run_pipeline(goal: str):
    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()
    planner = CapabilityDependencyPlanner()

    flows = engine.infer_flow_graph(goal)
    candidates = engine.infer_requirement_candidates(goal, flows)
    graph = resolver.build_graph(goal, flows, candidates)
    bound = binder.bind_graph(graph, goal)
    cap_graph = cap_engine.bind_capabilities(bound)
    result = planner.plan(cap_graph)
    return result


# ── Benchmark ────────────────────────────────────────────────────────────────

def run_benchmark():
    print("=" * 66)
    print("  P7G-A  Capability Dependency Planner — Benchmark")
    print("=" * 66)

    aggregate = {
        "total_goals": len(TEST_GOALS),
        "total_dependency_paths": 0,
        "total_unsatisfied_inputs": 0,
        "cycles_detected_any": False,
        "max_depth_overall": 0,
        "goals_with_no_deps": 0,
        "goals_with_unsatisfied": 0,
        "goals_with_unresolved_assets": 0,
        "errors": 0,
    }

    for goal in TEST_GOALS:
        print(f"\nGoal: {goal!r}")
        try:
            result = run_pipeline(goal)
            s = result.summary()

            # Count UNRESOLVED asset nodes in the graph
            from browsermind_core.agent.inference import FlowInferenceEngine
            from browsermind_core.agent.asset_graph import AssetGraphResolver
            from browsermind_core.agent.environment_binder import EnvironmentBinder
            from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine

            _engine = FlowInferenceEngine()
            _resolver = AssetGraphResolver()
            _binder = EnvironmentBinder()
            _cap_engine = CapabilityDiscoveryEngine()
            _flows = _engine.infer_flow_graph(goal)
            _cands = _engine.infer_requirement_candidates(goal, _flows)
            _g = _resolver.build_graph(goal, _flows, _cands)
            _bg = _binder.bind_graph(_g, goal)
            unresolved_count = sum(
                1 for nd in _bg.nodes.values() if nd["type"] == "UNRESOLVED"
            )

            print(f"  dependency_paths   : {s['dependency_paths']}")
            print(f"  unsatisfied_states : {s['unsatisfied_states']}")
            if s["unsatisfied_states_detail"]:
                print(f"    detail: {s['unsatisfied_states_detail']}")
            print(f"  unsatisfied_inputs : {s['unsatisfied_inputs']}")
            if s["unsatisfied_inputs_detail"]:
                print(f"    detail: {s['unsatisfied_inputs_detail']}")
            print(f"  unresolved_assets  : {unresolved_count}")
            print(f"  cycles_detected    : {s['cycles_detected']}")
            print(f"  max_depth          : {s['max_depth']}")

            aggregate["total_dependency_paths"] += s["dependency_paths"]
            aggregate["total_unsatisfied_inputs"] += s["unsatisfied_inputs"]
            if s["cycles_detected"]:
                aggregate["cycles_detected_any"] = True
            aggregate["max_depth_overall"] = max(
                aggregate["max_depth_overall"], s["max_depth"]
            )
            if s["dependency_paths"] == 0:
                aggregate["goals_with_no_deps"] += 1
            if s["unsatisfied_inputs"] > 0:
                aggregate["goals_with_unsatisfied"] += 1
            if unresolved_count > 0:
                aggregate["goals_with_unresolved_assets"] += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            aggregate["errors"] += 1

    print("\n" + "=" * 66)
    print("  AGGREGATE SUMMARY")
    print("=" * 66)
    for k, v in aggregate.items():
        print(f"  {k:<32}: {v}")

    print("\n  Health check:")
    ok = True
    if aggregate["cycles_detected_any"]:
        print("  [FAIL] Cycles detected in dependency graph!")
        ok = False
    else:
        print("  [PASS] No cycles — dependency graph is a DAG")
    if aggregate["errors"] > 0:
        print(f"  [WARN] {aggregate['errors']} goal(s) raised exceptions")
    if aggregate["goals_with_no_deps"] == aggregate["total_goals"]:
        print("  [WARN] No dependency paths found for any goal — check capability graph")
    else:
        print(f"  [PASS] {aggregate['total_goals'] - aggregate['goals_with_no_deps']} / "
              f"{aggregate['total_goals']} goals produced at least one dependency path")


if __name__ == "__main__":
    run_benchmark()
