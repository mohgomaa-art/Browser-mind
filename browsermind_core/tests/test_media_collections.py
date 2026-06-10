"""Tests for MediaCollection and CollectionManager.

Covers:
  - MediaCollection.to_dict / from_dict round-trip
  - CollectionManager.create — returns MediaCollection, persists to disk
  - CollectionManager.get — retrieves by name
  - CollectionManager.get unknown → None
  - CollectionManager.all — returns list
  - CollectionManager.add_asset — appends hash, no duplicates
  - CollectionManager.remove_asset — removes hash
  - CollectionManager.remove_asset when hash not present → False
  - CollectionManager.auto_classify — matches by title
  - CollectionManager.auto_classify — matches by tag
  - CollectionManager.auto_classify — no match → empty list
  - CollectionManager.apply_auto_classify — mutates asset.collections
  - CollectionManager.delete — removes file, returns True
  - CollectionManager.delete unknown → False
  - auto_tag_rules case-insensitive matching
"""
from __future__ import annotations

import pytest
from pathlib import Path


def _make_manager(tmp_path):
    from browsermind_core.media.collections.collection import CollectionManager
    return CollectionManager(root=tmp_path / "collections")


# ── MediaCollection.to_dict / from_dict ───────────────────────────────────────

def test_collection_round_trip_dict():
    from browsermind_core.media.collections.collection import MediaCollection
    col = MediaCollection(
        name="4K Wallpapers",
        description="High resolution",
        tags=["wallpaper"],
        auto_tag_rules=["4k", "wallpaper"],
        asset_hashes=["abc123"],
        created_at="2024-01-01T00:00:00",
    )
    d      = col.to_dict()
    cloned = MediaCollection.from_dict(d)
    assert cloned.name           == "4K Wallpapers"
    assert cloned.description    == "High resolution"
    assert cloned.auto_tag_rules == ["4k", "wallpaper"]
    assert cloned.asset_hashes   == ["abc123"]


def test_collection_from_dict_defaults():
    from browsermind_core.media.collections.collection import MediaCollection
    col = MediaCollection.from_dict({"name": "minimal"})
    assert col.description    == ""
    assert col.auto_tag_rules == []
    assert col.asset_hashes   == []


# ── CollectionManager.create ──────────────────────────────────────────────────

def test_create_persists_to_disk(tmp_path):
    mgr = _make_manager(tmp_path)
    col = mgr.create("Nature Photos", description="Outdoor shots")
    assert col.name == "Nature Photos"
    assert mgr.get("Nature Photos") is not None


def test_create_with_auto_tag_rules(tmp_path):
    mgr = _make_manager(tmp_path)
    col = mgr.create("Sunsets", auto_tag_rules=["sunset", "dusk"])
    assert col.auto_tag_rules == ["sunset", "dusk"]


# ── CollectionManager.get ─────────────────────────────────────────────────────

def test_get_returns_collection(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Test Collection")
    fetched = mgr.get("Test Collection")
    assert fetched is not None
    assert fetched.name == "Test Collection"


def test_get_unknown_returns_none(tmp_path):
    mgr = _make_manager(tmp_path)
    assert mgr.get("does_not_exist") is None


# ── CollectionManager.all ─────────────────────────────────────────────────────

def test_all_returns_list(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("A")
    mgr.create("B")
    all_cols = mgr.all()
    names    = [c.name for c in all_cols]
    assert "A" in names
    assert "B" in names


# ── add_asset / remove_asset ──────────────────────────────────────────────────

def test_add_asset(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Photos")
    ok = mgr.add_asset("Photos", "hash_abc")
    assert ok
    col = mgr.get("Photos")
    assert "hash_abc" in col.asset_hashes


def test_add_asset_no_duplicates(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Photos")
    mgr.add_asset("Photos", "hash_abc")
    mgr.add_asset("Photos", "hash_abc")
    col = mgr.get("Photos")
    assert col.asset_hashes.count("hash_abc") == 1


def test_add_asset_unknown_collection_returns_false(tmp_path):
    mgr = _make_manager(tmp_path)
    ok  = mgr.add_asset("nonexistent", "hash_abc")
    assert not ok


def test_remove_asset(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Photos")
    mgr.add_asset("Photos", "hash_abc")
    ok = mgr.remove_asset("Photos", "hash_abc")
    assert ok
    col = mgr.get("Photos")
    assert "hash_abc" not in col.asset_hashes


def test_remove_asset_not_present_returns_false(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Photos")
    ok = mgr.remove_asset("Photos", "missing_hash")
    assert not ok


# ── auto_classify ─────────────────────────────────────────────────────────────

def test_auto_classify_by_title(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Sunsets", auto_tag_rules=["sunset"])
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                  title="Beautiful sunset over the ocean")
    matched = mgr.auto_classify(asset)
    assert "Sunsets" in matched


def test_auto_classify_by_tag(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Cats", auto_tag_rules=["cat"])
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x", title="Photo")
    asset.tags = ["cat", "animal"]
    matched    = mgr.auto_classify(asset)
    assert "Cats" in matched


def test_auto_classify_no_match(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Dogs", auto_tag_rules=["dog"])
    asset   = MediaAsset.from_bytes(b"x", source_url="https://x.com/x", title="Mountain")
    matched = mgr.auto_classify(asset)
    assert "Dogs" not in matched


def test_auto_classify_case_insensitive(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Wallpapers", auto_tag_rules=["wallpaper"])
    asset   = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                    title="4K WALLPAPER night city")
    matched = mgr.auto_classify(asset)
    assert "Wallpapers" in matched


# ── apply_auto_classify ───────────────────────────────────────────────────────

def test_apply_auto_classify_mutates_asset(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Nature", auto_tag_rules=["forest"])
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                  title="Deep forest trail photo")
    matched = mgr.apply_auto_classify(asset)
    assert "Nature" in matched
    assert "Nature" in asset.collections


def test_apply_auto_classify_updates_collection_file(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    mgr  = _make_manager(tmp_path)
    mgr.create("Art", auto_tag_rules=["painting"])
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                  title="Classic painting from 1800s")
    mgr.apply_auto_classify(asset)
    col = mgr.get("Art")
    assert asset.content_hash in col.asset_hashes


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_collection(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.create("Temp")
    ok = mgr.delete("Temp")
    assert ok
    assert mgr.get("Temp") is None


def test_delete_unknown_returns_false(tmp_path):
    mgr = _make_manager(tmp_path)
    assert not mgr.delete("nonexistent_collection")
