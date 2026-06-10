"""
BrowserMind -- Phase 1: State Taxonomy Discovery Census
=======================================================
Crawls 50 domains. Discovers ALL Interaction Opportunity Zones.
Reports family distribution, Shannon entropy, and unclassified_rate.

No samples generated. Pure taxonomy discovery.
"""
import asyncio
import json
import sys
import os
import collections
import math

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler import StateFamilyBuilder

TARGETS = [
    # Auth (must ALL -> login_form)
    ("https://github.com/login",                                        "auth"),
    ("https://www.reddit.com/login",                                    "auth"),
    ("https://www.linkedin.com/login",                                  "auth"),
    ("https://discord.com/login",                                       "auth"),
    ("https://www.netflix.com/login",                                   "auth"),
    ("https://slack.com/signin",                                        "auth"),
    ("https://www.dropbox.com/login",                                   "auth"),
    ("https://www.twitch.tv/login",                                     "auth"),

    # Search (must -> search_interface)
    ("https://www.google.com",                                          "search"),
    ("https://www.bing.com",                                            "search"),
    ("https://duckduckgo.com",                                          "search"),
    ("https://www.youtube.com",                                         "search"),
    ("https://www.amazon.com",                                          "search"),
    ("https://www.ebay.com",                                            "search"),

    # Article / Content
    ("https://en.wikipedia.org/wiki/Python_(programming_language)",     "article"),
    ("https://www.nytimes.com",                                         "article"),
    ("https://www.bbc.com",                                             "article"),
    ("https://news.ycombinator.com",                                    "article"),

    # Navigation Hubs
    ("https://www.python.org",                                          "nav"),
    ("https://www.github.com",                                          "nav"),
    ("https://www.apple.com",                                           "nav"),
    ("https://www.microsoft.com",                                       "nav"),
    ("https://stackoverflow.com",                                       "nav"),

    # E-commerce / Product
    ("https://www.walmart.com",                                         "ecommerce"),
    ("https://www.target.com",                                          "ecommerce"),
    ("https://www.imdb.com",                                            "ecommerce"),
    ("https://www.zillow.com",                                          "ecommerce"),

    # Settings / Multi-Field Forms
    ("https://github.com/settings/profile",                             "settings"),

    # Developer Docs
    ("https://docs.python.org/3/",                                      "docs"),
    ("https://developer.mozilla.org/en-US/",                            "docs"),
    ("https://pypi.org",                                                "docs"),
    ("https://huggingface.co",                                          "docs"),

    # Social / Feed
    ("https://www.reddit.com",                                          "feed"),
    ("https://news.google.com",                                         "feed"),

    # Sign Up / Registration
    ("https://github.com/signup",                                       "signup"),
    ("https://www.reddit.com/register",                                 "signup"),
]


async def run_census():
    builder = StateFamilyBuilder()

    # Track ALL zones discovered across all pages
    zone_counter   = collections.Counter()   # family -> count of zones
    page_results   = []                      # raw per-page data
    total_zones    = 0
    unclassified   = 0
    pages_crawled  = 0

    print(f"Phase 1 Census -- {len(TARGETS)} domains\n")
    print(f"{'Domain':<52} {'Cat':<10} {'Zones Discovered'}")
    print("-" * 100)

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

                ax_graph = await build_graph_from_page(page)
                result   = builder.identify_zones(ax_graph)

                zones = result.get("zones", [])
                unclassified += result.get("unclassified_count", 0)
                pages_crawled += 1
                total_zones += len(zones)

                zone_families = []
                for z in zones:
                    family = z["family"]
                    zone_counter[family] += 1
                    zone_families.append(family)

                primary = result.get("primary_zone")
                primary_name = primary["family"] if primary else "none"

                zone_summary = " | ".join(zone_families[:5])
                if len(zone_families) > 5:
                    zone_summary += f" (+{len(zone_families)-5} more)"

                print(f"{url[:50]:<52} {category:<10} [{primary_name}]  {zone_summary}")

                page_results.append({
                    "url": url,
                    "category": category,
                    "zones": zones,
                    "primary": primary_name,
                    "zone_count": len(zones)
                })

                await page.close()

            except Exception as e:
                print(f"{url[:50]:<52} {category:<10} [ERROR] {str(e)[:40]}")

        await browser.close()

    # -- Census Report --------------------------------------------------------
    print("\n\n" + "=" * 70)
    print("TAXONOMY CENSUS REPORT -- Phase 1")
    print("=" * 70)

    total_classified = sum(
        v for k, v in zone_counter.items()
        if k not in ("generic_interactive", "generic_page", "empty_page")
    )
    unclassified_rate = round(
        (unclassified / total_zones) if total_zones > 0 else 0.0, 4
    )

    # Shannon Entropy over zone distribution
    entropy = 0.0
    if total_zones > 0:
        for count in zone_counter.values():
            p = count / total_zones
            if p > 0:
                entropy -= p * math.log2(p)

    report = {
        "pages_crawled":            pages_crawled,
        "total_zones_discovered":   total_zones,
        "distinct_families":        len(zone_counter),
        "state_family_entropy":     round(entropy, 4),
        "unclassified_rate":        unclassified_rate,
        "taxonomy_version":         "1.0",
        "families": [
            {
                "name":  k,
                "count": v,
                "share": round(v / total_zones, 3)
            }
            for k, v in zone_counter.most_common()
        ]
    }

    # Write taxonomy_report_v2.json
    out_path = os.path.join(os.path.dirname(__file__), '..', 'taxonomy_report_v2.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {out_path}\n")
    print(json.dumps(report, indent=2))

    # -- Failure Checks --------------------------------------------------------
    print("\n" + "=" * 70)
    print("FAILURE ANALYSIS")
    print("=" * 70)

    # Auth pages that did NOT have a login_form zone at all
    auth_missing = [
        r for r in page_results
        if r['category'] == 'auth'
        and not any(z['family'] == 'login_form' for z in r['zones'])
    ]
    auth_total = sum(1 for _, c in TARGETS if c == 'auth')
    print(f"\nAuth pages missing login_form zone: {len(auth_missing)}/{auth_total}")
    for r in auth_missing:
        families = [z['family'] for z in r['zones']]
        print(f"  {r['url'][:55]}  -> zones: {families}")

    # Search pages that did NOT have a search_interface zone
    search_missing = [
        r for r in page_results
        if r['category'] == 'search'
        and not any(z['family'] == 'search_interface' for z in r['zones'])
    ]
    search_total = sum(1 for _, c in TARGETS if c == 'search')
    print(f"\nSearch pages missing search_interface zone: {len(search_missing)}/{search_total}")
    for r in search_missing:
        families = [z['family'] for z in r['zones']]
        print(f"  {r['url'][:55]}  -> zones: {families}")

    # Generic fallback rate
    print(f"\nunclassified_rate: {unclassified_rate:.1%}")
    if unclassified_rate <= 0.05:
        print("  -> PASS (<=5%)")
    elif unclassified_rate <= 0.15:
        print("  -> MARGINAL (5-15%): review generic zones")
    else:
        print("  -> FAIL (>15%): taxonomy is missing families")

    # Entropy check
    print(f"\nstate_family_entropy: {entropy:.4f}")
    if entropy >= 2.5:
        print("  -> PASS: high diversity")
    elif entropy >= 1.5:
        print("  -> MARGINAL: moderate diversity")
    else:
        print("  -> FAIL: taxonomy is collapsed into few families")

    print("\n[DONE]")
    print("\nNext step: If PASS -> issue TAXONOMY FREEZE v1.0")
    print("           If FAIL -> revisit classification rules before harvesting")


if __name__ == "__main__":
    asyncio.run(run_census())
