"""
BrowserMind -- Zone Census Debugger
====================================
RAW DATA ONLY. No classification. No fixes.

Shows the actual content of every interactive zone discovered
so we can diagnose: Bad Clustering? Bad Filtering? Bad Classification?
"""
import asyncio
import json
import sys
import os
import collections

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page

TARGETS = [
    "https://github.com/login",
    "https://www.google.com",
    "https://duckduckgo.com",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://www.reddit.com",
]

_INTERACTIVE_ROLES = frozenset({
    'button', 'link', 'textbox', 'combobox', 'checkbox',
    'radio', 'menuitem', 'searchbox'
})


def build_tree(nodes, edges):
    """Build parent->children and parent maps from edges."""
    children_map = collections.defaultdict(list)
    parent_map = {}
    for edge in edges:
        if len(edge) >= 2:
            src, tgt = edge[0], edge[1]
            children_map[src].append(tgt)
            parent_map[tgt] = src
    return dict(children_map), parent_map


def get_all_descendants(idx, children_map):
    """BFS: all descendant idxs of a node."""
    visited = []
    queue = [idx]
    while queue:
        cur = queue.pop(0)
        visited.append(cur)
        queue.extend(children_map.get(cur, []))
    return visited


def cluster_by_ancestor(interactive_idxs, parent_map, node_by_idx, depth):
    """Group interactive nodes by ancestor at given depth."""
    groups = collections.defaultdict(list)
    for idx in interactive_idxs:
        ancestor = idx
        for _ in range(depth):
            p = parent_map.get(ancestor)
            if p is None:
                break
            ancestor = p
        groups[ancestor].append(idx)
    return dict(groups)


async def debug_page(url, page, zone_count_target=5):
    ax_graph = await build_graph_from_page(page)
    nodes = ax_graph.get("nodes", [])
    edges = ax_graph.get("edges", [])

    node_by_idx = {n['idx']: n for n in nodes if 'idx' in n}
    children_map, parent_map = build_tree(nodes, edges)

    # -- 1. Global stats ------------------------------------------------
    role_dist = collections.Counter(n.get('role', '') for n in nodes)
    edge_types = collections.Counter(
        e[2] if len(e) > 2 else 'no_type' for e in edges
    )

    print(f"\n{'='*70}")
    print(f"URL: {url}")
    print(f"{'='*70}")
    print(f"  Total nodes : {len(nodes)}")
    print(f"  Total edges : {len(edges)}")
    print(f"  Edge types  : {dict(edge_types)}")
    print(f"  Role dist   : {dict(role_dist.most_common(10))}")

    # -- 2. Named vs unnamed interactive nodes -------------------------
    named   = [n for n in nodes if n.get('role','') in _INTERACTIVE_ROLES and n.get('name','').strip()]
    unnamed = [n for n in nodes if n.get('role','') in _INTERACTIVE_ROLES and not n.get('name','').strip()]
    all_interactive = named + unnamed

    print(f"\n  Interactive nodes total : {len(all_interactive)}")
    print(f"    -> named   : {len(named)}")
    print(f"    -> unnamed : {len(unnamed)}  <- potential filter victim")

    # Show unnamed roles distribution
    if unnamed:
        unnamed_roles = collections.Counter(n.get('role','') for n in unnamed)
        print(f"    -> unnamed role dist: {dict(unnamed_roles)}")

    # -- 3. Test clustering at DIFFERENT depths -------------------------
    print(f"\n  Clustering test (using ALL interactive nodes, not just named):")
    all_interactive_idxs = [n['idx'] for n in all_interactive]

    for depth in [2, 3, 4, 5, 6]:
        groups = cluster_by_ancestor(all_interactive_idxs, parent_map, node_by_idx, depth)
        print(f"    depth={depth} -> {len(groups)} groups  "
              f"(sizes: {sorted([len(v) for v in groups.values()], reverse=True)[:8]})")

    # -- 4. Show actual zone contents at depth=4, all interactive ------
    print(f"\n  Zone details (depth=4, ALL interactive nodes, top {zone_count_target} zones):")
    groups_d4 = cluster_by_ancestor(all_interactive_idxs, parent_map, node_by_idx, 4)
    # Sort groups by size
    sorted_groups = sorted(groups_d4.items(), key=lambda x: len(x[1]), reverse=True)

    for zone_id, (anc_idx, member_idxs) in enumerate(sorted_groups[:zone_count_target]):
        member_nodes = [node_by_idx[idx] for idx in member_idxs if idx in node_by_idx]
        role_counts  = dict(collections.Counter(n.get('role','') for n in member_nodes))
        top_labels   = [n.get('name','')[:40] for n in member_nodes if n.get('name','').strip()][:6]
        depth_values = [n.get('depth', 0) for n in member_nodes]
        avg_depth    = round(sum(depth_values)/len(depth_values), 1) if depth_values else 0

        print(f"\n    Zone {zone_id}:")
        print(f"      ancestor_idx : {anc_idx}")
        print(f"      node_count   : {len(member_nodes)}")
        print(f"      role_dist    : {role_counts}")
        print(f"      avg_depth    : {avg_depth}")
        print(f"      top_labels   : {top_labels}")

    # -- 5. Connected Components on Interactive subgraph ---------------
    print(f"\n  Connected Components analysis (interactive-only subgraph):")
    interactive_set = set(n['idx'] for n in all_interactive)

    # Build adjacency only among interactive nodes (direct edge OR shared parent)
    adj = collections.defaultdict(set)
    for edge in edges:
        if len(edge) >= 2:
            a, b = edge[0], edge[1]
            if a in interactive_set and b in interactive_set:
                adj[a].add(b)
                adj[b].add(a)
    # Also connect siblings that share the same direct parent
    for node in all_interactive:
        idx = node['idx']
        par = parent_map.get(idx)
        if par is not None:
            for sibling in children_map.get(par, []):
                if sibling != idx and sibling in interactive_set:
                    adj[idx].add(sibling)
                    adj[sibling].add(idx)

    visited_cc = set()
    components = []
    for start in interactive_set:
        if start in visited_cc:
            continue
        comp = []
        queue = [start]
        while queue:
            cur = queue.pop()
            if cur in visited_cc:
                continue
            visited_cc.add(cur)
            comp.append(cur)
            queue.extend(adj.get(cur, []))
        components.append(comp)

    components.sort(key=len, reverse=True)
    print(f"    Total components: {len(components)}")
    for i, comp in enumerate(components[:5]):
        comp_nodes  = [node_by_idx[idx] for idx in comp if idx in node_by_idx]
        comp_roles  = dict(collections.Counter(n.get('role','') for n in comp_nodes))
        comp_labels = [n.get('name','')[:30] for n in comp_nodes if n.get('name','').strip()][:4]
        print(f"    Component {i}: size={len(comp)} roles={comp_roles} labels={comp_labels}")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        for url in TARGETS:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                await debug_page(url, page)
                await page.close()
            except Exception as e:
                print(f"\n[ERROR] {url}: {e}")
        await browser.close()

    print("\n\n" + "="*70)
    print("DIAGNOSIS GUIDE")
    print("="*70)
    print("  If depth=4 groups are huge (>20 nodes each) -> BAD CLUSTERING")
    print("  If unnamed >> named for textbox/searchbox   -> BAD FILTERING")
    print("  If components match expected zones          -> USE CONNECTED COMPONENTS")
    print("  If components are also chaotic              -> DEEPER PROBLEM")

if __name__ == "__main__":
    asyncio.run(main())
