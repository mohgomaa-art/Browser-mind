"""
Full gold recompile -- Taxonomy v5 frozen.
Wipes gold_interaction / gold_extraction and rebuilds from census URL set.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler.gold_compiler import GoldCompiler

# Same URL set as state_family_census.py (36 domains)
URLS = [
    "https://github.com/login",
    "https://www.reddit.com/login",
    "https://www.linkedin.com/login",
    "https://discord.com/login",
    "https://www.netflix.com/login",
    "https://slack.com/signin",
    "https://www.dropbox.com/login",
    "https://www.twitch.tv/login",
    "https://www.google.com",
    "https://www.bing.com",
    "https://duckduckgo.com",
    "https://www.youtube.com",
    "https://www.amazon.com",
    "https://www.ebay.com",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://www.nytimes.com",
    "https://www.bbc.com",
    "https://news.ycombinator.com",
    "https://www.python.org",
    "https://www.github.com",
    "https://www.apple.com",
    "https://www.microsoft.com",
    "https://stackoverflow.com",
    "https://www.walmart.com",
    "https://www.target.com",
    "https://www.imdb.com",
    "https://www.zillow.com",
    "https://github.com/settings/profile",
    "https://docs.python.org/3/",
    "https://developer.mozilla.org/en-US/",
    "https://pypi.org",
    "https://huggingface.co",
    "https://www.reddit.com",
    "https://news.google.com",
    "https://github.com/signup",
    "https://www.reddit.com/register",
]


def wipe_gold_dirs(base_dir: str) -> None:
    for name in ("gold_interaction", "gold_extraction"):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
    print(f"Wiped and recreated gold dirs under {base_dir}")


async def main() -> None:
    base_dir = os.path.join(os.path.dirname(__file__), "..", "training")
    wipe_gold_dirs(base_dir)

    compiler = GoldCompiler(base_dir=base_dir)
    total_i = 0
    total_e = 0
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        for i, url in enumerate(URLS, 1):
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                ax_graph = await build_graph_from_page(page)
                ni, ne = compiler.process_state(url, ax_graph)
                total_i += ni
                total_e += ne
                print(f"[{i}/{len(URLS)}] {url[:55]:<55}  +{ni}i +{ne}e")
                await page.close()
            except Exception as e:
                errors.append({"url": url, "error": str(e)[:200]})
                print(f"[{i}/{len(URLS)}] {url[:55]:<55}  ERROR: {e}")

        await browser.close()

    print("\n========== RECOMPILE COMPLETE ==========")
    print(f"Interaction samples: {total_i}")
    print(f"Extraction samples:  {total_e}")
    print(f"Total:               {total_i + total_e}")
    print(f"Errors:              {len(errors)}")
    if errors:
        for err in errors:
            print(f"  - {err['url']}: {err['error']}")


if __name__ == "__main__":
    asyncio.run(main())
