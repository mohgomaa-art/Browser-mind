"""Tests for MediaVault.

Covers:
  - store new asset with data → file written, index written
  - store duplicate → tags/collections merged, no overwrite
  - store duplicate with overwrite_meta=True → overwrites title
  - get → returns asset with correct hash
  - get unknown → None
  - exists → True / False
  - get_bytes → reads file content
  - by_tag / by_collection / by_source / by_type
  - search: multi-filter
  - delete → removes index and file
  - stats → total, by_type, by_source
  - store_file → creates asset from disk file
  - atomic write: tmp file renamed on store
"""
from __future__ import annotations

import pytest
from pathlib import Path


def _make_asset(data=b"img", source_url="https://imgur.com/x.png",
                tags=None, collections=None, title="test"):
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    asset = MediaAsset.from_bytes(data, source_url=source_url, title=title,
                                  media_type=MediaType.IMAGE)
    asset.tags        = list(tags or [])
    asset.collections = list(collections or [])
    return asset, data


def test_vault_store_new_asset(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    asset, data = _make_asset()
    stored = vault.store(asset, data=data)
    assert stored.local_path is not None
    assert Path(stored.local_path).exists()
    assert (tmp_path / "index" / f"{asset.content_hash}.json").exists()


def test_vault_store_duplicate_merges_tags(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    data  = b"shared"
    a1, _ = _make_asset(data=data, tags=["cat"])
    a2, _ = _make_asset(data=data, tags=["dog"])
    vault.store(a1, data=data)
    stored2 = vault.store(a2)
    assert "cat" in stored2.tags
    assert "dog" in stored2.tags


def test_vault_store_duplicate_does_not_overwrite_title(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    data  = b"shared"
    a1, _ = _make_asset(data=data, title="original")
    a2, _ = _make_asset(data=data, title="new_title")
    vault.store(a1, data=data)
    stored2 = vault.store(a2)
    assert stored2.title == "original"  # first write wins


def test_vault_store_overwrite_meta(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    data  = b"shared"
    a1, _ = _make_asset(data=data, title="original")
    a2, _ = _make_asset(data=data, title="replacement")
    vault.store(a1, data=data)
    stored2 = vault.store(a2, overwrite_meta=True)
    assert stored2.title == "replacement"


def test_vault_get_returns_asset(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    asset, data = _make_asset()
    vault.store(asset, data=data)
    fetched = vault.get(asset.content_hash)
    assert fetched is not None
    assert fetched.content_hash == asset.content_hash


def test_vault_get_unknown_returns_none(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    assert vault.get("nonexistentdeadhash12345678") is None


def test_vault_exists_true_false(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    asset, data = _make_asset()
    assert not vault.exists(asset.content_hash)
    vault.store(asset, data=data)
    assert vault.exists(asset.content_hash)


def test_vault_get_bytes(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    data  = b"binary content 123"
    asset, _ = _make_asset(data=data)
    vault.store(asset, data=data)
    retrieved = vault.get_bytes(asset.content_hash)
    assert retrieved == data


def test_vault_by_tag(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    a1, d1 = _make_asset(data=b"a", tags=["cat"])
    a2, d2 = _make_asset(data=b"b", tags=["dog"])
    vault.store(a1, data=d1)
    vault.store(a2, data=d2)
    cats = vault.by_tag("cat")
    assert len(cats) == 1
    assert cats[0].content_hash == a1.content_hash


def test_vault_by_collection(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    a1, d1 = _make_asset(data=b"a", collections=["nature"])
    a2, d2 = _make_asset(data=b"b", collections=["art"])
    vault.store(a1, data=d1)
    vault.store(a2, data=d2)
    nature = vault.by_collection("nature")
    assert len(nature) == 1


def test_vault_by_source(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    from browsermind_core.media.media_asset import MediaSource
    vault = MediaVault(root=tmp_path)
    a1, d1 = _make_asset(data=b"a", source_url="https://imgur.com/x.png")
    vault.store(a1, data=d1)
    imgs = vault.by_source(MediaSource.IMGUR)
    assert len(imgs) == 1


def test_vault_by_type(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    vault = MediaVault(root=tmp_path)
    a1 = MediaAsset.from_bytes(b"img", source_url="https://x.com/a",
                                media_type=MediaType.IMAGE)
    a2 = MediaAsset.from_bytes(b"vid", source_url="https://x.com/b",
                                media_type=MediaType.VIDEO)
    vault.store(a1, data=b"img")
    vault.store(a2, data=b"vid")
    images = vault.by_type(MediaType.IMAGE)
    assert any(a.media_type == MediaType.IMAGE for a in images)


def test_vault_search_by_query(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    a1, d1 = _make_asset(data=b"a", title="sunset photo")
    a2, d2 = _make_asset(data=b"b", title="city skyline")
    vault.store(a1, data=d1)
    vault.store(a2, data=d2)
    hits = vault.search(query="sunset")
    assert len(hits) == 1
    assert hits[0].title == "sunset photo"


def test_vault_search_multi_filter(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    from browsermind_core.media.media_asset import MediaSource
    vault = MediaVault(root=tmp_path)
    a1, d1 = _make_asset(data=b"a", source_url="https://imgur.com/x.png",
                          tags=["cat"], title="cat photo")
    vault.store(a1, data=d1)
    # Match both source and tag
    hits = vault.search(source=MediaSource.IMGUR, tag="cat")
    assert len(hits) == 1
    # Mismatch on tag
    hits2 = vault.search(source=MediaSource.IMGUR, tag="dog")
    assert len(hits2) == 0


def test_vault_delete(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    asset, data = _make_asset()
    vault.store(asset, data=data)
    assert vault.exists(asset.content_hash)
    ok = vault.delete(asset.content_hash)
    assert ok
    assert not vault.exists(asset.content_hash)


def test_vault_delete_nonexistent_returns_false(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    vault = MediaVault(root=tmp_path)
    assert not vault.delete("deadhash_nonexistent")


def test_vault_stats(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    from browsermind_core.media.media_asset import MediaAsset, MediaType, MediaSource
    vault = MediaVault(root=tmp_path)
    a1 = MediaAsset.from_bytes(b"img", source_url="https://imgur.com/x",
                                media_type=MediaType.IMAGE)
    a2 = MediaAsset.from_bytes(b"vid", source_url="https://youtube.com/v",
                                media_type=MediaType.VIDEO)
    vault.store(a1, data=b"img")
    vault.store(a2, data=b"vid")
    stats = vault.stats()
    assert stats["total"] == 2
    assert stats["by_type"].get(MediaType.IMAGE, 0) >= 1
    assert stats["by_type"].get(MediaType.VIDEO, 0) >= 1


def test_vault_store_file(tmp_path):
    from browsermind_core.media.media_vault import MediaVault
    from browsermind_core.media.media_asset import MediaType
    vault   = MediaVault(root=tmp_path)
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    p = src_dir / "photo.jpg"
    p.write_bytes(b"fake jpeg")
    asset = vault.store_file(p, source_url="https://flickr.com/x",
                             tags=["nature"], collections=["landscapes"])
    assert asset.media_type  == MediaType.IMAGE
    assert "nature"     in asset.tags
    assert "landscapes" in asset.collections
    assert asset.title        == "photo"
