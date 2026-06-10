"""
BrowserMind -- Hard Negative Generator (Phase 4.5)
=================================================
For every sample with action=click or action=type, extracts 3 semantically 
similar but incorrect nodes from the same graph.

Example:
Correct:  button "Login"
Negatives: button "Register", link "Sign In", button "Continue"

This forces the Contrastive Ranking Loss (Phase 6) to learn semantic 
discrimination rather than simple button pattern-matching.
"""

import json
from pathlib import Path
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    print("WARNING: sentence-transformers or scikit-learn not installed.")
    print("Run: pip install sentence-transformers scikit-learn")
    SentenceTransformer = None

def generate_hard_negatives(dataset_dir: str = "training/dataset_v2"):
    if SentenceTransformer is None:
        print("Cannot run without sentence-transformers.")
        return

    print("Loading MiniLM...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    dir_path = Path(dataset_dir)
    files = list(dir_path.glob("*.json"))
    
    modified_files = 0
    total_samples = 0
    samples_with_negatives = 0

    for fp in files:
        changed = False
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            samples = data if isinstance(data, list) else data.get("samples", [data])
            
            for s in samples:
                total_samples += 1
                ea = s.get("expert_action", {})
                if not ea:
                    continue
                    
                atype = ea.get("type") or ea.get("action_type", "unknown")
                if atype not in ("click", "type"):
                    continue
                    
                target_idx = ea.get("element_idx")
                if target_idx is None:
                    continue
                    
                nodes = s.get("graph", {}).get("nodes", [])
                if not nodes or target_idx >= len(nodes):
                    continue
                    
                target_node = nodes[target_idx]
                target_name = target_node.get("name", "").strip()
                if not target_name:
                    continue
                
                # We want negatives that are also interactive
                candidate_indices = []
                candidate_names = []
                
                for i, n in enumerate(nodes):
                    if i == target_idx:
                        continue
                    role = n.get("role", "")
                    
                    # Strict Role Similarity
                    is_role_match = (role == target_node.get("role", ""))
                    is_interactive = role in ("button", "link", "menuitem", "textbox", "checkbox", "radio", "combobox")
                    
                    if is_interactive:
                        name = n.get("name", "").strip()
                        if name:
                            # Prioritize exact role matches by passing them separately if needed
                            # but for now we just require it's an interactive element,
                            # and we'll boost similarity score for role match later.
                            candidate_indices.append(i)
                            candidate_names.append(name)
                            
                if len(candidate_indices) < 3:
                    # Fallback to any node with text if not enough interactive ones
                    for i, n in enumerate(nodes):
                        if i == target_idx or i in candidate_indices:
                            continue
                        name = n.get("name", "").strip()
                        if name:
                            candidate_indices.append(i)
                            candidate_names.append(name)

                if not candidate_indices:
                    continue
                    
                # Embed target and candidates
                target_emb = model.encode([target_name])
                cand_embs = model.encode(candidate_names)
                
                # Compute similarities
                sims = cosine_similarity(target_emb, cand_embs)[0]
                
                # Apply Role Bonus (+0.3) for exact role match to enforce confusable candidates
                for idx_in_cand, real_idx in enumerate(candidate_indices):
                    cand_role = nodes[real_idx].get("role", "")
                    if cand_role == target_node.get("role", ""):
                        sims[idx_in_cand] += 0.3
                
                # Get top 3 indices
                top_k = min(3, len(candidate_indices))
                top_indices = np.argsort(sims)[-top_k:][::-1]
                
                hard_negatives = [int(candidate_indices[i]) for i in top_indices]
                
                # Inject
                ea["hard_negatives"] = hard_negatives
                s["expert_action"] = ea
                changed = True
                samples_with_negatives += 1

            if changed:
                fp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                modified_files += 1
                
        except Exception as e:
            print(f"Error processing {fp.name}: {e}")

    print("\n--- Hard Negative Generation Complete ---")
    print(f"Total samples processed:   {total_samples}")
    print(f"Samples with negatives:    {samples_with_negatives}")
    print(f"Files modified:            {modified_files}")


if __name__ == "__main__":
    generate_hard_negatives()
