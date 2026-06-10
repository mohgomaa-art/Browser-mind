"""
Phase COV-1 — legacy wrapper; canonical seeds live in capability_seeds.json (COV-2).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

_SEEDS_PATH = os.path.join(os.path.dirname(__file__), "capability_seeds.json")


def _load_seeds() -> Dict[str, Any]:
    with open(_SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)

# (url, bucket) — baseline Y2 / V1.3 census URLs (search/auth/nav heavy)
BASELINE_TARGETS: List[Tuple[str, str]] = [
    ("https://github.com/login", "auth"),
    ("https://www.reddit.com/login", "auth"),
    ("https://www.linkedin.com/login", "auth"),
    ("https://discord.com/login", "auth"),
    ("https://www.netflix.com/login", "auth"),
    ("https://slack.com/signin", "auth"),
    ("https://www.dropbox.com/login", "auth"),
    ("https://www.twitch.tv/login", "auth"),
    ("https://www.google.com", "search"),
    ("https://www.bing.com", "search"),
    ("https://duckduckgo.com", "search"),
    ("https://www.youtube.com", "search"),
    ("https://www.amazon.com", "search"),
    ("https://www.ebay.com", "search"),
    ("https://en.wikipedia.org/wiki/Python_(programming_language)", "article"),
    ("https://www.nytimes.com", "article"),
    ("https://www.bbc.com", "article"),
    ("https://news.ycombinator.com", "article"),
    ("https://www.python.org", "nav"),
    ("https://www.github.com", "nav"),
    ("https://www.apple.com", "nav"),
    ("https://www.microsoft.com", "nav"),
    ("https://stackoverflow.com", "nav"),
    ("https://www.walmart.com", "ecommerce"),
    ("https://www.target.com", "ecommerce"),
    ("https://www.imdb.com", "ecommerce"),
    ("https://www.zillow.com", "ecommerce"),
    ("https://github.com/settings/profile", "settings"),
    ("https://docs.python.org/3/", "docs"),
    ("https://developer.mozilla.org/en-US/", "docs"),
    ("https://pypi.org", "docs"),
    ("https://huggingface.co", "docs"),
    ("https://www.reddit.com", "feed"),
    ("https://news.google.com", "feed"),
    ("https://github.com/signup", "signup"),
    ("https://www.reddit.com/register", "signup"),
]

def _cov1_from_seeds() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for cap_id, entry in _load_seeds().get("capabilities", {}).items():
        if cap_id in ("search", "auth_recovery", "filter", "account_creation"):
            continue
        for url in entry.get("urls", []):
            out.append(
                {
                    "url": url,
                    "bucket": cap_id,
                    "intended": [cap_id],
                }
            )
    return out


# COV-1 expansion — derived from capability_seeds.json
COV1_TARGETS: List[Dict[str, Any]] = _cov1_from_seeds()

# Aspirational minimums for full training corpus (COV-1 gate — not expected in one crawl)
CAPABILITY_CENSUS_TARGETS: Dict[str, int] = {
    "search": 150,
    "auth_recovery": 120,
    "upload": 90,
    "content_creation": 80,
    "settings": 70,
    "checkout": 60,
    "job_application": 50,
    "multi_field_form": 40,
    "filter": 30,
    "account_creation": 30,
    "navigation": 200,
    "legal": 20,
    "marketing": 20,
}

CORE_CURRICULUM_CAPS = (
    "search",
    "auth_recovery",
    "upload",
    "settings",
    "checkout",
    "job_application",
    "content_creation",
)


def resolve_targets(mode: str) -> List[Dict[str, Any]]:
    """mode: baseline | cov1 | full"""
    out: List[Dict[str, Any]] = []
    if mode in ("baseline", "full"):
        for url, bucket in BASELINE_TARGETS:
            out.append(
                {
                    "url": url,
                    "bucket": bucket,
                    "intended": [],
                    "source": "baseline",
                }
            )
    if mode in ("cov1", "full"):
        for entry in COV1_TARGETS:
            out.append({**entry, "source": "cov1"})
    return out
