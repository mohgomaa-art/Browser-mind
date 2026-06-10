"""
BrowserMind -- Phase 0.5C: Graph Integrity Audit
=================================================
After Role Budgeting fix, verify that:
  1. Textboxes and searchboxes now survive into the graph
  2. Edges are being built (not 0)
  3. Connected components reflect real interaction zones
  4. Observation coverage is healthy

Key question: does the largest component now contain
meaningful zones (textbox + button) instead of isolated links?
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
    ("https://github.com/login",     "auth"),
    ("https://www.google.com",       "search"),
    ("https://duckduckgo.com",       "search"),
    ("https://en.wikipedia.org/wiki/Python_(programming_language)", "article"),
    ("https://www.reddit.com",       "feed"),
    ("https://www.reddit.com/login", "auth"),
    ("https://discord.com/login",    "auth"),
    ("https://www.amazon.com",       "ecommerce"),
]

_INTERACTIVE = frozenset({'button', 'link', 'textbox', 'combobox',
                           'checkbox', 'radio', 'menuitem', 'searchbox'})


def connected_components(nodes, edges):
    """Compute connected components over ALL node types."""
    idx_set = {n['idx'] for n in nodes}
    adj = collections.defaultdict(set)
    for edge in edges:
        if len(edge) >= 2:
            a, b = edge[0], edge[1]
            adj[a].add(b)
            adj[b].add(a)
    visited = set()
    components = []
    for start in idx_set:
        if start in visited:
            continue
        comp = []
        queue = [start]
        while queue:
            cur = queue.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.append(cur)
            queue.extend(adj.get(cur, []))
        components.append(comp)
    return sorted(components, key=len, reverse=True)


async def audit():
    print("Phase 0.5C: Graph Integrity Audit\n")
    print(f"{'Domain':<45} {'nodes':>6} {'edges':>6} {'comps':>6} {'largest':>8} "
          f"{'inp_raw':>8} {'inp_sel':>8} {'inp_cov':>8}")
    print("-" * 115)

    details = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        for url, category in TARGETS:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                graph = await build_graph_from_page(page)
                nodes = graph.get("nodes", [])
                edges = graph.get("edges", [])
                cov   = graph.get("observation_coverage", {})

                role_dist  = collections.Counter(n.get('role','') for n in nodes)
                components = connected_components(nodes, edges)
                largest    = len(components[0]) if components else 0

                # Largest component role breakdown
                node_by_idx = {n['idx']: n for n in nodes}
                if components:
                    lc_roles = collections.Counter(
                        node_by_idx[i].get('role','') for i in components[0] if i in node_by_idx
                    )
                else:
                    lc_roles = {}

                raw_cov  = cov.get("raw", {})
                sel_cov  = cov.get("selected", {})
                pct_cov  = cov.get("coverage", {})

                inp_raw = raw_cov.get("input", 0)
                inp_sel = sel_cov.get("input", 0)
                inp_pct = pct_cov.get("input", 0.0)

                print(f"{url[:43]:<45} {len(nodes):>6} {len(edges):>6} {len(components):>6} "
                      f"{largest:>8} {inp_raw:>8} {inp_sel:>8} {inp_pct:>8.0%}")

                details.append({
                    "url": url,
                    "category": category,
                    "nodes": len(nodes),
                    "edges": len(edges),
                    "components": len(components),
                    "largest_component": largest,
                    "largest_component_roles": dict(lc_roles),
                    "role_distribution": dict(role_dist),
                    "observation_coverage": cov,
                })

                await page.close()

            except Exception as e:
                print(f"{url[:43]:<45} ERROR: {e}")

        await browser.close()

    # -- Summary ---------------------------------------------------------------
    print("\n\n" + "=" * 70)
    print("GRAPH INTEGRITY AUDIT -- Detailed Report")
    print("=" * 70)

    all_pass = True
    for d in details:
        has_inputs  = d["role_distribution"].get("textbox", 0) + \
                      d["role_distribution"].get("searchbox", 0) + \
                      d["role_distribution"].get("combobox", 0) > 0
        has_edges   = d["edges"] > 0
        lc_has_form = (d["largest_component_roles"].get("textbox", 0) +
                       d["largest_component_roles"].get("button", 0)) >= 2

        status_inputs = "PASS" if has_inputs  else "FAIL"
        status_edges  = "PASS" if has_edges   else "FAIL"
        status_lc     = "PASS" if lc_has_form else "WARN"

        flag = "OK" if (has_inputs and has_edges) else "!!"
        all_pass = all_pass and has_inputs and has_edges

        print(f"\n[{flag}] {d['url'][:60]}")
        print(f"     inputs in graph : {status_inputs}  "
              f"(textbox={d['role_distribution'].get('textbox',0)}, "
              f"searchbox={d['role_distribution'].get('searchbox',0)})")
        print(f"     edges built     : {status_edges}  ({d['edges']} edges)")
        print(f"     largest comp    : {d['largest_component']} nodes  "
              f"roles={d['largest_component_roles']}  [{status_lc}]")
        print(f"     inp_coverage    : raw={d['observation_coverage'].get('raw',{}).get('input',0)} "
              f"sel={d['observation_coverage'].get('selected',{}).get('input',0)} "
              f"pct={d['observation_coverage'].get('coverage',{}).get('input',0):.0%}")

    print("\n" + "=" * 70)
    if all_pass:
        print("VERDICT: PASS -- Role Budgeting fixed the observation bottleneck.")
        print("Next: Re-run State Taxonomy Census.")
    else:
        print("VERDICT: FAIL -- Some sites still missing inputs or edges.")
        print("Next: Inspect failures above before census.")

if __name__ == "__main__":
    asyncio.run(audit())
