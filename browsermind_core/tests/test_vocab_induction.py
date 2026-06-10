"""Tests for Vocabulary Induction pipeline.

Covers:
  - FallbackLedger: record, load, as_logger, stats
  - extract_name_fragment: fallback token parsing
  - similarity(): trigram+word Jaccard
  - cluster_fallbacks(): grouping by semantic similarity
  - propose_vocab_expansions(): threshold filtering
  - VocabProposalStore: save, confirm, reject, extensions rebuild
  - PrimitiveNormalizer: load_vocab_extensions() runtime extension
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest


# ── extract_name_fragment ─────────────────────────────────────────────────────

def test_extract_name_fragment_basic():
    from browsermind_core.representation.fallback_ledger import extract_name_fragment
    assert extract_name_fragment("CLICK_BUTTON_add_to_wishlist") == "add to wishlist"


def test_extract_name_fragment_multi_word_role():
    from browsermind_core.representation.fallback_ledger import extract_name_fragment
    # Role is single word: FILL_TEXTBOX_newsletter_email
    assert extract_name_fragment("FILL_TEXTBOX_newsletter_email") == "newsletter email"


def test_extract_name_fragment_hover():
    from browsermind_core.representation.fallback_ledger import extract_name_fragment
    result = extract_name_fragment("HOVER_DIV_tooltip_content")
    assert "tooltip" in result


# ── FallbackLedger ────────────────────────────────────────────────────────────

def test_fallback_ledger_record_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.fallback_ledger import FallbackLedger
        ledger = FallbackLedger(path=Path(tmp) / "ledger.json")
        ledger.record("hover", "div", "tooltip content", site_key="site_a",
                      raw_token="HOVER_DIV_tooltip_content")
        entries = ledger.all()
        assert len(entries) == 1
        entry = next(iter(entries.values()))
        assert entry.frequency == 1
        assert "site_a" in entry.sites


def test_fallback_ledger_merges_same_fragment():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.fallback_ledger import FallbackLedger
        ledger = FallbackLedger(path=Path(tmp) / "ledger.json")
        # Same fragment, two different sites
        ledger.record("hover", "div", "tooltip content", site_key="site_a",
                      raw_token="HOVER_DIV_tooltip_content")
        ledger.record("hover", "div", "tooltip content", site_key="site_b",
                      raw_token="HOVER_DIV_tooltip_content")
        entries = ledger.all()
        assert len(entries) == 1
        entry = next(iter(entries.values()))
        assert entry.frequency == 2
        assert set(entry.sites) == {"site_a", "site_b"}


def test_fallback_ledger_as_logger():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.fallback_ledger import FallbackLedger
        from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer

        ledger = FallbackLedger(path=Path(tmp) / "ledger.json")
        norm = PrimitiveNormalizer(logger=ledger.as_logger(site_key="github"))

        norm.normalize("hover",  "div",    "tooltip hint")   # fallback
        norm.normalize("scroll", "main",   "page content")   # fallback
        norm.normalize("click",  "button", "Sign in")        # known → NOT recorded

        entries = ledger.all()
        assert len(entries) == 2   # only the 2 fallbacks


def test_fallback_ledger_stats():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.fallback_ledger import FallbackLedger
        ledger = FallbackLedger(path=Path(tmp) / "ledger.json")
        ledger.record("hover", "div", "tooltip", site_key="a", raw_token="HOVER_DIV_tooltip")
        ledger.record("hover", "div", "tooltip", site_key="b", raw_token="HOVER_DIV_tooltip")
        ledger.record("scroll", "main", "content", site_key="a", raw_token="SCROLL_MAIN_content")

        s = ledger.stats()
        assert s["unique_fragments"] == 2
        assert s["total_observations"] == 3
        assert s["multi_site_fragments"] == 1  # only "tooltip" spans 2 sites


# ── similarity ────────────────────────────────────────────────────────────────

def test_similarity_identical():
    from browsermind_core.representation.vocab_inductor import similarity
    assert similarity("add to wishlist", "add to wishlist") == 1.0


def test_similarity_similar():
    from browsermind_core.representation.vocab_inductor import similarity
    score = similarity("add to wishlist", "add to favourites")
    assert score > 0.3   # clearly related


def test_similarity_unrelated():
    from browsermind_core.representation.vocab_inductor import similarity
    score = similarity("add to wishlist", "sign in")
    assert score < 0.25


# ── cluster_fallbacks ─────────────────────────────────────────────────────────

def _make_entries(fragments_sites):
    from browsermind_core.representation.fallback_ledger import FallbackEntry
    entries = {}
    for frag, sites, freq in fragments_sites:
        e = FallbackEntry(frag)
        e.sites = list(sites)
        e.frequency = freq
        entries[frag] = e
    return entries


def test_cluster_fallbacks_groups_similar():
    from browsermind_core.representation.vocab_inductor import cluster_fallbacks

    entries = _make_entries([
        ("add to wishlist",   ["a", "b"], 10),
        ("add to favourites", ["a", "c"], 8),
        ("save for later",    ["b", "d"], 6),
        ("sign in now",       ["a", "b"], 12),
    ])
    clusters = cluster_fallbacks(entries, similarity_threshold=0.25)

    # "add to wishlist" and "add to favourites" should cluster together
    wishlist_cluster = next(
        (c for c in clusters if "add to wishlist" in c.members), None
    )
    assert wishlist_cluster is not None
    assert "add to favourites" in wishlist_cluster.members


def test_cluster_fallbacks_separates_unrelated():
    from browsermind_core.representation.vocab_inductor import cluster_fallbacks

    entries = _make_entries([
        ("add to wishlist", ["a"], 5),
        ("sign in now",     ["b"], 5),
    ])
    clusters = cluster_fallbacks(entries, similarity_threshold=0.3)
    assert len(clusters) == 2   # no grouping for unrelated fragments


def test_cluster_fallbacks_returns_sorted_by_frequency():
    from browsermind_core.representation.vocab_inductor import cluster_fallbacks

    entries = _make_entries([
        ("x rare phrase",     ["a"],       1),
        ("add to wishlist",   ["a", "b"], 20),
    ])
    clusters = cluster_fallbacks(entries)
    assert clusters[0].total_frequency >= clusters[-1].total_frequency


# ── propose_vocab_expansions ──────────────────────────────────────────────────

def test_propose_vocab_expansions_threshold_filter():
    from browsermind_core.representation.vocab_inductor import (
        FallbackCluster, propose_vocab_expansions
    )

    # Cluster with only 1 site → below min_sites=2
    low_cluster = FallbackCluster(
        cluster_id="abc", members=["add to wishlist"], sites=["one_site"],
        total_frequency=50, proposed_name="ADD_WISHLIST",
        l1_category="INTERACT_OBJECT", cohesion=1.0, example_names=[]
    )
    # Cluster meeting thresholds
    good_cluster = FallbackCluster(
        cluster_id="def", members=["subscribe now", "follow user"],
        sites=["site_a", "site_b", "site_c"],
        total_frequency=15, proposed_name="FOLLOW_USER",
        l1_category="INTERACT_OBJECT", cohesion=0.5, example_names=[]
    )

    proposals = propose_vocab_expansions(
        [low_cluster, good_cluster], min_sites=2, min_freq=5
    )
    assert len(proposals) == 1
    assert proposals[0].proposed_name == "FOLLOW_USER"


# ── VocabProposalStore ────────────────────────────────────────────────────────

def test_vocab_proposal_store_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.vocab_inductor import (
            VocabProposalStore, VocabProposal
        )
        store = VocabProposalStore(
            proposals_path=Path(tmp) / "proposals.json",
            extensions_path=Path(tmp) / "extensions.json",
        )
        p = VocabProposal(
            proposal_id="test-001",
            proposed_name="WISHLIST_ITEM",
            l1_category="INTERACT_OBJECT",
            name_patterns=["add to wishlist", "save for later"],
            cluster_id="abc",
            cluster_members=["add to wishlist", "save for later"],
            cluster_sites=["site_a", "site_b"],
            total_frequency=20,
        )
        store.save(p)
        all_p = store.all()
        assert len(all_p) == 1
        assert all_p[0].proposed_name == "WISHLIST_ITEM"


def test_vocab_proposal_store_confirm_writes_extensions():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.vocab_inductor import (
            VocabProposalStore, VocabProposal
        )
        ext_path = Path(tmp) / "extensions.json"
        store = VocabProposalStore(
            proposals_path=Path(tmp) / "proposals.json",
            extensions_path=ext_path,
        )
        p = VocabProposal(
            proposal_id="test-002",
            proposed_name="WISHLIST_ITEM",
            l1_category="INTERACT_OBJECT",
            name_patterns=["add to wishlist"],
            cluster_id="abc",
            cluster_members=["add to wishlist"],
            cluster_sites=["a", "b"],
            total_frequency=10,
        )
        store.save(p)
        confirmed = store.confirm("test-002")
        assert confirmed is not None
        assert confirmed.status == "CONFIRMED"
        # extensions.json must have been written
        assert ext_path.exists()
        exts = json.loads(ext_path.read_text())
        assert len(exts) == 1
        assert exts[0]["l0_name"] == "WISHLIST_ITEM"


def test_vocab_proposal_store_reject():
    with tempfile.TemporaryDirectory() as tmp:
        from browsermind_core.representation.vocab_inductor import (
            VocabProposalStore, VocabProposal
        )
        store = VocabProposalStore(
            proposals_path=Path(tmp) / "proposals.json",
            extensions_path=Path(tmp) / "ext.json",
        )
        p = VocabProposal(
            proposal_id="test-003",
            proposed_name="WHATEVER",
            l1_category="SELECT",
            name_patterns=["whatever"],
            cluster_id="xyz",
            cluster_members=["whatever"],
            cluster_sites=["a", "b"],
            total_frequency=5,
        )
        store.save(p)
        rejected = store.reject("test-003", "site-specific noise")
        assert rejected.status == "REJECTED"
        assert rejected.rejected_reason == "site-specific noise"


# ── PrimitiveNormalizer runtime extension ─────────────────────────────────────

def test_load_vocab_extensions_activates_pattern():
    with tempfile.TemporaryDirectory() as tmp:
        import browsermind_core.representation.primitive_normalizer as _mod
        from browsermind_core.representation.primitive_normalizer import (
            PrimitiveNormalizer, load_vocab_extensions
        )

        ext_path = Path(tmp) / "vocab_extensions.json"
        # Use a pattern that does NOT match any existing base vocab
        ext_path.write_text(json.dumps([{
            "l0_name":  "SAVE_TO_READING_LIST",
            "l1_name":  "INTERACT_OBJECT",
            "patterns": ["add to reading list", "save to read later"],
            "proposal_id": "test-001",
        }]), encoding="utf-8")

        n = load_vocab_extensions(path=ext_path)
        assert n == 1

        norm = PrimitiveNormalizer(collapse_level=0)
        result = norm.normalize("click", "button", "Add to Reading List")
        assert result == "SAVE_TO_READING_LIST"

        # After this extension is loaded, it should not be flagged as fallback
        records = []
        norm2 = PrimitiveNormalizer(logger=records.append)
        norm2.normalize("click", "button", "Add to Reading List")
        assert records[0]["is_fallback"] is False

        # Clean up: reset module state
        _mod._RUNTIME_PATTERNS = []
        _mod._RUNTIME_L0 = set()
