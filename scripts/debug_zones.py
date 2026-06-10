"""
Debug: Show the actual AX graph nodes and zones for specific pages.
Run this before fixing classification rules.
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
from training.compiler import StateFamilyBuilder

DEBUG_URLS = [
    "https://github.com",
    "https://github.com/login",
    "https://www.google.com",
    "https://duckduckgo.com",
]

async def debug():
    builder = StateFamilyBuilder()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        for url in DEBUG_URLS:
            print("\n" + "=" * 70)
            print(f"URL: {url}")
            print("=" * 70)

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            ax_graph = await build_graph_from_page(page)
            nodes = ax_graph.get("nodes", [])
            edges = ax_graph.get("edges", [])

            print(f"\nTotal nodes: {len(nodes)}, Total edges: {len(edges)}")

            # Role distribution
            role_counts = collections.Counter(n.get('role', '') for n in nodes)
            print(f"\nRole Distribution:")
            for role, count in role_counts.most_common():
                print(f"  {role:<20} {count}")

            # Show edge types
            edge_types = collections.Counter(
                e[2] if len(e) > 2 else 'unknown' for e in edges
            )
            print(f"\nEdge Types: {dict(edge_types)}")

            # Show nodes that have names and are interactive
            print(f"\nNamed Interactive Nodes:")
            interactive_roles = {'button', 'link', 'textbox', 'combobox',
                                  'checkbox', 'radio', 'menuitem', 'searchbox'}
            for n in nodes:
                if n.get('role', '') in interactive_roles and n.get('name', '').strip():
                    print(f"  idx={n['idx']:<4} role={n['role']:<15} name={n['name'][:50]!r}")

            # Run the zone detector and show raw zones
            print(f"\nZones detected by StateFamilyBuilder:")
            fam = builder.identify_family(ax_graph)
            print(f"\nPage state_family: {fam['state_family']}  confidence={fam['confidence']}")

            result = builder.identify_zones(ax_graph)
            for i, zone in enumerate(result["zones"][:5]):
                print(
                    f"  Zone {i}: family={zone['family']:<22} "
                    f"conf={zone['confidence']:.2f} score={zone['zone_score']:<6} "
                    f"roles={zone['role_counts']}"
                )

            await page.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug())
