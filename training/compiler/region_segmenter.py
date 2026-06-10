"""
BrowserMind — Region Segmenter
==============================
PHASE 1B: STRUCTURAL ANCHOR SEGMENTATION

Converts a giant connected graph of DOM nodes into discrete, semantic 
interaction regions using WAI-ARIA structural landmarks.

Candidate Anchors:
- main, navigation, search, form, dialog, complementary
- article, banner, contentinfo, region

Output:
[
  {
    "region_id": "...",
    "region_type": "...",
    "node_count": N,
    "interactive_count": M,
    "roles": {"textbox": 1, "button": 2},
    "nodes": [...]
  }
]
"""
import collections
from typing import Dict, Any, List

_ANCHOR_ROLES = frozenset({
    'main', 'navigation', 'search', 'form', 'dialog',
    'complementary', 'article', 'banner', 'contentinfo', 'region'
})

_INTERACTIVE_ROLES = frozenset({
    'button', 'link', 'textbox', 'combobox', 'checkbox',
    'radio', 'menuitem', 'searchbox'
})

class RegionSegmenter:
    def __init__(self):
        pass

    def segment(self, ax_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Takes the graph from graph_builder and partitions it into regions.
        """
        nodes = ax_graph.get("nodes", [])
        edges = ax_graph.get("edges", [])

        if not nodes:
            return []

        node_by_idx = {n['idx']: n for n in nodes}

        # Build adjacency for full tree traversal
        children_map = collections.defaultdict(list)
        parent_map = {}
        for edge in edges:
            if len(edge) >= 3 and edge[2] == "parent_child":
                src, tgt = edge[0], edge[1]
                children_map[src].append(tgt)
                parent_map[tgt] = src

        # 1. Identify all anchor candidates
        anchors = [n for n in nodes if n.get('role') in _ANCHOR_ROLES]
        anchor_idxs = {n['idx'] for n in anchors}

        regions = []
        covered_interactive = set()

        # 2. Assign descendants to nearest anchor via BFS
        # Note: If an anchor has a child anchor, we need to respect the child boundary.
        for anchor in anchors:
            a_idx = anchor['idx']
            a_role = anchor.get('role', 'unknown_anchor')

            descendants = []
            queue = list(children_map.get(a_idx, []))
            visited = {a_idx}
            
            while queue:
                cur = queue.pop(0)
                if cur in visited:
                    continue
                
                # Stop if we hit another anchor (the child anchor claims its own subtree)
                if cur in anchor_idxs:
                    continue
                    
                visited.add(cur)
                descendants.append(cur)
                queue.extend(children_map.get(cur, []))

            interactive_nodes = [
                node_by_idx[idx] for idx in descendants
                if idx in node_by_idx and node_by_idx[idx].get('role') in _INTERACTIVE_ROLES
            ]

            if interactive_nodes:
                role_counts = collections.Counter(n.get('role') for n in interactive_nodes)
                regions.append({
                    "region_id": f"region_{a_idx}_{a_role}",
                    "region_type": a_role,
                    "node_count": len(descendants) + 1,  # +1 for anchor
                    "interactive_count": len(interactive_nodes),
                    "roles": dict(role_counts),
                    "nodes": interactive_nodes
                })
                covered_interactive.update(n['idx'] for n in interactive_nodes)

        # 3. Handle unanchored interactive nodes (root region fallback)
        unanchored_interactive = [
            n for n in nodes 
            if n.get('role') in _INTERACTIVE_ROLES and n['idx'] not in covered_interactive
        ]

        if unanchored_interactive:
            role_counts = collections.Counter(n.get('role') for n in unanchored_interactive)
            regions.append({
                "region_id": "region_root_fallback",
                "region_type": "root",
                "node_count": len(unanchored_interactive),
                "interactive_count": len(unanchored_interactive),
                "roles": dict(role_counts),
                "nodes": unanchored_interactive
            })

        # 4. Merge tiny zones / Splitting
        # (For now, let's just return what we have to see baseline segmentation)
        # TODO: merge small adjacent root regions

        return regions
