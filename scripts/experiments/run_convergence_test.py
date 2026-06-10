"""P5B — Cross-Goal Convergence Harness.

Loads all generated Invariant Graphs from different goals and computes
the Convergence Matrix to test if Behavioral Primitives are universal.
"""
import sys
import json
import argparse
import statistics
from pathlib import Path

# Fix for charmap errors on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.convergence_metrics import calculate_node_convergence, calculate_edge_convergence

def run_test():
    invariants_dir = ROOT / "reports" / "invariants"
    if not invariants_dir.exists():
        print(f"No invariants directory found at {invariants_dir}")
        return
        
    graph_files = list(invariants_dir.glob("invariant_graph_*.json"))
    if not graph_files:
        print("No invariant graphs found. Run discover_invariants.py first.")
        return
        
    graphs = []
    for gf in graph_files:
        try:
            data = json.loads(gf.read_text(encoding="utf-8"))
            graphs.append(data)
        except Exception as e:
            print(f"Error loading {gf.name}: {e}")
            
    M = len(graphs)
    print(f"\n========================================================")
    print(f" P5B CONVERGENCE TEST")
    print(f" Loaded {M} Goal DAGs.")
    print(f"========================================================\n")
    
    if M < 2:
        print("WARNING: Need at least 2 Goal DAGs to calculate convergence.")
        print(f"Only found: {graphs[0]['goal_id'] if M == 1 else 'None'}")
        
    node_matrix = [[0.0]*M for _ in range(M)]
    edge_matrix = [[0.0]*M for _ in range(M)]
    
    for i in range(M):
        for j in range(M):
            if i == j:
                node_matrix[i][j] = 1.0
                edge_matrix[i][j] = 1.0
                continue
                
            g1 = graphs[i]
            g2 = graphs[j]
            
            # Nodes: Only compare 1.0 support Invariants
            node_conv = calculate_node_convergence(g1.get("invariants", []), g2.get("invariants", []))
            
            # Edges: Compare strict precedence rules
            edge_conv = calculate_edge_convergence(g1.get("partial_order_edges", []), g2.get("partial_order_edges", []))
            
            node_matrix[i][j] = node_conv
            edge_matrix[i][j] = edge_conv
            
    # Calculate Global Averages
    def avg_matrix(matrix):
        if M < 2: return 0.0
        vals = [matrix[i][j] for i in range(M) for j in range(M) if i < j]
        return statistics.mean(vals) if vals else 0.0
        
    avg_node_conv = avg_matrix(node_matrix)
    avg_edge_conv = avg_matrix(edge_matrix)
    
    print(f"--- GLOBAL CONVERGENCE RATE ---")
    print(f" Node Convergence (Intents) : {avg_node_conv:.2%}")
    print(f" Edge Convergence (DAGs)    : {avg_edge_conv:.2%}")
    print(f"-------------------------------\n")
    
    # Extract Global Invariants (Nodes present in > 70% of Goals)
    intent_counts = {}
    edge_counts = {}
    
    for g in graphs:
        for node in g.get("invariants", []):
            intent_counts[node] = intent_counts.get(node, 0) + 1
        for edge in g.get("partial_order_edges", []):
            edge_tup = tuple(edge)
            edge_counts[edge_tup] = edge_counts.get(edge_tup, 0) + 1
            
    global_intents = [node for node, count in intent_counts.items() if (count / M) >= 0.7]
    global_edges = [edge for edge, count in edge_counts.items() if (count / M) >= 0.7]
    
    print(f" [GLOBAL INVARIANTS] (Present in >= 70% of goals):")
    if not global_intents:
        print("   (None)")
    else:
        for node in sorted(global_intents):
            print(f"   -> {node}")
            
    print(f"\n [GLOBAL DAG] (Strict Precedence in >= 70% of goals):")
    if not global_edges:
        print("   (None)")
    else:
        for a, b in sorted(global_edges):
            print(f"   {a}  --->  {b}")
            
    print(f"\n========================================================")
    if avg_node_conv > 0.7:
        print(" => [ONTOLOGY VALIDATED] The Fundamental Unit has been discovered.")
    elif avg_node_conv > 0.3:
        print(" => [PARTIAL CONVERGENCE] Domain-specific patterns still dominate.")
    elif M >= 2:
        print(" => [ONTOLOGY FAILED] Goals did not collapse into shared primitives.")
    print(f"========================================================")
    
if __name__ == "__main__":
    run_test()
