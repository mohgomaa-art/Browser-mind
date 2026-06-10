"""
BrowserMind -- Phase 1C: Region Debugging
========================================
Outputs the raw region segmentation data for 8 domains.
"""
import asyncio
import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler.region_segmenter import RegionSegmenter

TARGETS = [
    "https://www.google.com",
    "https://duckduckgo.com",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://github.com/login",
    "https://www.reddit.com",
    "https://stackoverflow.com",
    "https://www.linkedin.com",
    "https://www.facebook.com"
]

async def audit():
    print("====================================================")
    print("PHASE 1C: REGION SEGMENTATION DEBUG REPORT")
    print("====================================================\n")

    segmenter = RegionSegmenter()

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

                graph = await build_graph_from_page(page)
                regions = segmenter.segment(graph)

                print(f"[{url}]")
                if not regions:
                    print("  No regions found.\n")
                    await page.close()
                    continue

                for r in regions:
                    print(f"  - Region: {r['region_type']:<15} | Nodes: {r['node_count']:<3} | "
                          f"Interactive: {r['interactive_count']:<3} | Roles: {r['roles']}")
                
                print()
                await page.close()

            except Exception as e:
                print(f"[{url}] ERROR: {e}\n")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(audit())
