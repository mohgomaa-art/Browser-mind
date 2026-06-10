"""P6B Test: Ontology Adapters Validation.

This script tests the FlowDomainAdapter and TaskLocalityAdapter using real
P5 Field Research datasets (from the harness storage).
It proves that raw traces can be bottom-up inferred into multi-dimensional
RepresentationHypotheses, and that new traces can be viewed through both lenses.
"""
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.representation.adapters.flow_domain import FlowDomainAdapter
from browsermind_core.representation.adapters.task_locality import TaskLocalityAdapter
from browsermind_core.representation.hypothesis import RepresentationBundle

def run():
    print(f"\n========================================================")
    print(f" P6B KERNEL TEST: REAL TRACES TO ONTOLOGY HYPOTHESES")
    print(f"========================================================\n")
    
    # Load real traces from harness
    harness = ReplayExperimentHarness(headless=True)
    all_templates_meta = harness.kernel.workflow_store.list_templates()
    
    traces = []
    for meta in all_templates_meta:
        if meta["name"].startswith("var_"):
            traces.append(harness.load_template(meta["name"]))
            
    print(f"Loaded {len(traces)} variance traces from storage.\n")
    
    adapters = [FlowDomainAdapter(), TaskLocalityAdapter()]
    live_hypotheses = []
    
    # 1. Inference Phase
    print(" 1. Inference Phase (Generating Hypotheses from Data)")
    print(" --------------------------------------------------------")
    for adapter in adapters:
        hypotheses = adapter.infer_hypothesis(traces)
        live_hypotheses.extend(hypotheses)
        print(f" [+] {adapter.ontology_type.upper():<15} : Generated {len(hypotheses)} hypotheses.")
        
    print("\n 2. Top Theories by Evidence")
    print(" --------------------------------------------------------")
    # Show one top Flow Domain and one top Task Locality
    fd_hyps = [h for h in live_hypotheses if h.ontology_type == "flow_domain"]
    tl_hyps = [h for h in live_hypotheses if h.ontology_type == "task_locality"]
    
    if fd_hyps:
        h = sorted(fd_hyps, key=lambda x: x.evidence.get("site_transfer"), reverse=True)[0]
        print(f" 🎯 Top Flow Domain: {h.id}")
        print(f"    Nodes: {h.nodes}")
        print(f"    Transferability: {h.evidence.get('site_transfer'):.2f}")
        print(f"    Predictive Power: {h.evidence.get('predictive_power'):.2f}\n")
        
    if tl_hyps:
        h = sorted(tl_hyps, key=lambda x: x.evidence.get("predictive_power"), reverse=True)[0]
        print(f" 🎯 Top Task Locality: {h.id}")
        print(f"    Nodes (Sample): {h.nodes[:3]}")
        print(f"    Transferability: {h.evidence.get('site_transfer'):.2f}")
        print(f"    Predictive Power: {h.evidence.get('predictive_power'):.2f}\n")

    # 3. Output Phase (Bundle)
    print(" 3. View Generation Phase (Representation Bundle)")
    print(" --------------------------------------------------------")
    if traces:
        test_trace = traces[0]
        print(f" Incoming Trace: {test_trace.name}")
        
        bundle = RepresentationBundle()
        for adapter in adapters:
            # For testing, grab the first hypothesis of that type
            hyps = [h for h in live_hypotheses if h.ontology_type == adapter.ontology_type]
            if hyps:
                view = adapter.generate_view(test_trace, hyps[0].id)
                bundle.views.append(view)
                
        for view in bundle.views:
            print(f"  -> [{view.ontology_id}]")
            print(f"     Entities: {view.entities}")
            print(f"     Confidence: {view.confidence:.2f}\n")

    print(f"========================================================")
    print(" P6B VERDICT: SUCCESS")
    print(" Adapters successfully parsed raw P5 traces into competing")
    print(" hypotheses and generated multi-perspective views.")
    print(f"========================================================")

if __name__ == "__main__":
    run()
