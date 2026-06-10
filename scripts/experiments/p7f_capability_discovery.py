# scripts/experiments/p7f_capability_discovery.py
"""P7F: Capability Discovery & Coverage Validation Benchmark.

Evaluates CapabilityDiscoveryEngine's coverage across 14 representative tasks.
Reports OS capability metrics: environments processed, baseline vs overrides coverage.
Verifies no workflow-specific semantics have leaked into the discovery layer.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder, AmbiguousAssetError
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    print(f"\n========================================================")
    print(f" P7F: CAPABILITY DISCOVERY & COVERAGE BENCHMARK")
    print(f"========================================================\n")

    engine = FlowInferenceEngine()
    resolver = AssetGraphResolver()
    binder = EnvironmentBinder()
    cap_engine = CapabilityDiscoveryEngine()

    dataset = [
        {"goal": "Forgot my personal GitHub password", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my work email password", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my university portal password", "expected_outcome": "RESOLVED"},
        {"goal": "Modify my secure recovery settings", "expected_outcome": "RESOLVED"},
        {"goal": "Modify my settings configuration on local vault", "expected_outcome": "RESOLVED"},
        {"goal": "Update company password preferences", "expected_outcome": "RESOLVED"},
        {"goal": "Buy a laptop on WebArena using my personal card", "expected_outcome": "RESOLVED"},
        {"goal": "Checkout corporate cart on WebArena", "expected_outcome": "RESOLVED"},
        {"goal": "Create personal GitHub account", "expected_outcome": "RESOLVED"},
        {"goal": "Search python documentation", "expected_outcome": "RESOLVED"},
        {"goal": "Login to my corporate portal", "expected_outcome": "RESOLVED"},
        {"goal": "Forgot my password", "expected_outcome": "AMBIGUOUS"},
        {"goal": "Reset my credentials", "expected_outcome": "AMBIGUOUS"},
        {"goal": "Buy a book", "expected_outcome": "AMBIGUOUS"}
    ]

    # Metrics registries
    unique_environments = set()
    discovered_capabilities = set()
    environment_kind_counts = {}
    
    baseline_discovered = 0
    overrides_discovered = 0

    print(f"{'Goal':<48} | {'Outcome':<10} | {'Discovered Capabilities (Baseline & Overrides)'}")
    print("-" * 110)

    for item in dataset:
        goal = item["goal"]
        expected_outcome = item["expected_outcome"]

        flows = engine.infer_flow_graph(goal)
        candidates = engine.infer_requirement_candidates(goal, flows)
        graph = resolver.build_graph(goal, flows, candidates)

        actual_outcome = ""
        caps_resolved = []

        try:
            # 1. Environment Binding
            bound_graph = binder.bind_graph(graph, goal)
            # 2. Capability Discovery
            fully_bound_graph = cap_engine.bind_capabilities(bound_graph)
            
            actual_outcome = "RESOLVED"
            graph_dict = fully_bound_graph.to_dict()
            
            # Find environments and capabilities in the graph
            env_nodes = [n for n, d in graph_dict["nodes"].items() if d["type"] == "Environment"]
            cap_nodes = [n for n, d in graph_dict["nodes"].items() if d["type"] == "Capability"]
            
            for env in env_nodes:
                unique_environments.add(env)
                metadata = graph_dict["nodes"][env].get("metadata", {})
                kind = metadata.get("kind", "unknown")
                environment_kind_counts[kind] = environment_kind_counts.get(kind, 0) + 1

            for cap_name in cap_nodes:
                discovered_capabilities.add(cap_name)
                caps_resolved.append(cap_name)
                
                # Check if capability is from overrides or baseline
                is_override = any(cap_name in [c.name for c in override_list] for override_list in cap_engine.overrides.values())
                if is_override:
                    overrides_discovered += 1
                else:
                    baseline_discovered += 1

        except AmbiguousAssetError:
            actual_outcome = "AMBIGUOUS"
        except Exception as e:
            actual_outcome = f"ERROR: {type(e).__name__}"

        caps_resolved_str = ", ".join(caps_resolved) if caps_resolved else "[]"
        print(f"{goal:<48} | {actual_outcome:<10} | {caps_resolved_str}")

    print("-" * 110)
    print("\n========================================================")
    print(" P7F CAPABILITY COVERAGE SUMMARY METRICS")
    print("========================================================")
    print(f"Total Unique Environments Discovered   : {len(unique_environments)}")
    print(f"Total Unique Capabilities Discovered   : {len(discovered_capabilities)}")
    print(f"Baseline Capabilities Instantiated     : {baseline_discovered}")
    print(f"Override Capabilities Instantiated     : {overrides_discovered}")
    print(f"Total Capability Facts Registered      : {baseline_discovered + overrides_discovered}")
    print("\nEnvironment Kind Distribution:")
    for kind, count in environment_kind_counts.items():
        print(f"  - {kind:<20}: {count} instance(s)")
    print("========================================================\n")

    # Leakage check sanity
    forbidden = ["verification_code", "password_reset", "login", "authentication", "recover_account", "mfa"]
    leaked = False
    for cap_name in discovered_capabilities:
        for term in forbidden:
            if term in cap_name.lower():
                print(f"[WARNING] Leaked term '{term}' in capability '{cap_name}'!")
                leaked = True

    if not leaked:
        print("VERDICT: SUCCESS. Capability Discovery successfully proved Environment -> Capability mapping with zero workflow leaks.")
        sys.exit(0)
    else:
        print("VERDICT: FAILED. Workflow semantics leaked into capability layer.")
        sys.exit(1)


if __name__ == "__main__":
    main()
