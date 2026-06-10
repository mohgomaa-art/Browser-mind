"""Tests for SiteRegistry.

Covers:
  - SITE_REGISTRY has entries for all 30 categories
  - SiteEntry dataclass defaults and serialisation
  - get() returns correct entry or None
  - by_category() filters correctly
  - by_difficulty() filters correctly
  - training_envs_for_family() returns correct keys
  - test_envs_for_family() returns correct keys
  - exploration_candidates() sorted by priority
  - exploration_candidates() filtered by category
  - register() adds custom site
  - All seed entries have non-empty url and category
  - transfer_family entries appear in training_envs or test_envs
  - saucedemo is a training env for authentication family
  - reddit is a training env for community family
  - google_search is a training env for search family
"""
from __future__ import annotations


EXPECTED_CATEGORIES = {
    "social_networks",
    "forums_communities",
    "chat_realtime",
    "video_platforms",
    "audio_platforms",
    "image_platforms",
    "news_publishing",
    "blogs_personal",
    "ecommerce",
    "marketplaces",
    "saas_applications",
    "productivity_systems",
    "knowledge_systems",
    "developer_platforms",
    "package_registries",
    "cloud_platforms",
    "authentication_systems",
    "email_systems",
    "government_portals",
    "banking_finance",
    "crypto_platforms",
    "education_platforms",
    "job_platforms",
    "cms_sitebuilders",
    "search_engines",
    "maps_local_discovery",
    "travel_systems",
    "ai_platforms",
    "dashboards_admin",
    "unknown_frontier",
}


# ── Registry completeness ─────────────────────────────────────────────────────

def test_all_30_categories_present():
    from browsermind_core.registry.site_registry import SITE_REGISTRY
    found = {e.category for e in SITE_REGISTRY.values()}
    for cat in EXPECTED_CATEGORIES:
        assert cat in found, f"Category '{cat}' has no registered sites"


def test_seed_entries_have_url_and_category():
    from browsermind_core.registry.site_registry import SITE_REGISTRY
    for key, entry in SITE_REGISTRY.items():
        assert entry.url, f"Site '{key}' has no URL"
        assert entry.category, f"Site '{key}' has no category"


def test_seed_entries_have_valid_difficulty():
    from browsermind_core.registry.site_registry import SITE_REGISTRY
    for key, entry in SITE_REGISTRY.items():
        assert 1 <= entry.difficulty <= 5, f"Site '{key}' difficulty {entry.difficulty} out of range"


def test_registry_has_reasonable_size():
    from browsermind_core.registry.site_registry import SITE_REGISTRY
    assert len(SITE_REGISTRY) >= 50, "Expected at least 50 seed entries"


# ── SiteEntry API ─────────────────────────────────────────────────────────────

def test_get_returns_entry():
    from browsermind_core.registry.site_registry import get
    e = get("github")
    assert e is not None
    assert e.key == "github"
    assert e.category == "developer_platforms"


def test_get_returns_none_for_unknown():
    from browsermind_core.registry.site_registry import get
    assert get("nonexistent_site_xyz") is None


def test_by_category_returns_subset():
    from browsermind_core.registry.site_registry import by_category
    entries = by_category("search_engines")
    assert len(entries) >= 3
    for e in entries:
        assert e.category == "search_engines"


def test_by_difficulty_filters():
    from browsermind_core.registry.site_registry import by_difficulty
    easy = by_difficulty(max_difficulty=2)
    for e in easy:
        assert e.difficulty <= 2


def test_site_entry_serialise_round_trip():
    from browsermind_core.registry.site_registry import get, SiteEntry
    e = get("github")
    e2 = SiteEntry.from_dict(e.to_dict())
    assert e2.key == e.key
    assert e2.url == e.url
    assert e2.category == e.category
    assert e2.difficulty == e.difficulty
    assert e2.auth_required == e.auth_required
    assert e2.known_capabilities == e.known_capabilities
    assert e2.transfer_family == e.transfer_family
    assert e2.is_training_env == e.is_training_env


# ── Transfer family membership ────────────────────────────────────────────────

def test_training_envs_for_authentication():
    from browsermind_core.registry.site_registry import training_envs_for_family
    envs = training_envs_for_family("authentication")
    assert "saucedemo" in envs
    assert "github" in envs


def test_test_envs_for_authentication():
    from browsermind_core.registry.site_registry import test_envs_for_family
    envs = test_envs_for_family("authentication")
    assert "gitlab" in envs
    assert "huggingface" in envs


def test_training_envs_for_search():
    from browsermind_core.registry.site_registry import training_envs_for_family
    envs = training_envs_for_family("search")
    assert "google_search" in envs
    assert "bing" in envs
    assert "duckduckgo" in envs


def test_training_envs_for_community():
    from browsermind_core.registry.site_registry import training_envs_for_family
    envs = training_envs_for_family("community")
    assert "reddit" in envs


def test_no_site_in_both_training_and_test_for_same_family():
    from browsermind_core.registry.site_registry import (
        training_envs_for_family, test_envs_for_family
    )
    for family in ["authentication", "search", "community", "form_fill"]:
        training = set(training_envs_for_family(family))
        test = set(test_envs_for_family(family))
        overlap = training & test
        assert not overlap, f"Family '{family}' has sites in both train and test: {overlap}"


# ── exploration_candidates() ──────────────────────────────────────────────────

def test_exploration_candidates_sorted_by_priority():
    from browsermind_core.registry.site_registry import exploration_candidates
    candidates = exploration_candidates()
    priorities = [e.exploration_priority for e in candidates]
    assert priorities == sorted(priorities, reverse=True)


def test_exploration_candidates_filtered_by_category():
    from browsermind_core.registry.site_registry import exploration_candidates
    search_candidates = exploration_candidates(category="search_engines")
    assert all(e.category == "search_engines" for e in search_candidates)


def test_exploration_candidates_filtered_by_difficulty():
    from browsermind_core.registry.site_registry import exploration_candidates
    easy = exploration_candidates(max_difficulty=2)
    assert all(e.difficulty <= 2 for e in easy)


def test_exploration_candidates_min_priority():
    from browsermind_core.registry.site_registry import exploration_candidates
    high_prio = exploration_candidates(min_priority=8)
    assert all(e.exploration_priority >= 8 for e in high_prio)


# ── register() custom entry ───────────────────────────────────────────────────

def test_register_custom_site():
    from browsermind_core.registry.site_registry import register, get, SiteEntry
    custom = SiteEntry(
        key="my_intranet",
        url="http://intranet.local",
        category="unknown_frontier",
        difficulty=5,
    )
    register(custom)
    found = get("my_intranet")
    assert found is not None
    assert found.url == "http://intranet.local"


# ── SiteEntry field defaults ──────────────────────────────────────────────────

def test_site_entry_defaults():
    from browsermind_core.registry.site_registry import SiteEntry
    e = SiteEntry(key="minimal", url="https://example.com", category="unknown_frontier")
    assert e.difficulty == 2
    assert e.auth_required is False
    assert e.known_capabilities == []
    assert e.exploration_priority == 5
    assert e.exploration_budget == 200
    assert e.transfer_family is None
    assert e.is_training_env is False
    assert e.is_test_env is False


def test_site_entry_from_dict_forward_compat():
    from browsermind_core.registry.site_registry import SiteEntry
    old = {"key": "test_site", "url": "https://test.com", "category": "ecommerce"}
    e = SiteEntry.from_dict(old)
    assert e.difficulty == 2
    assert e.auth_required is False
    assert e.exploration_budget == 200
