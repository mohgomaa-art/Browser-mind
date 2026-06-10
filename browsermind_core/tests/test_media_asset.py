"""Tests for MediaAsset, MediaType, MediaSource, and _compute_hash.

Covers:
  - MediaType.from_extension / from_path / from_mime
  - MediaSource.from_url
  - _compute_hash — SHA-256 determinism
  - MediaAsset.from_bytes — hash, source detection, type setting
  - MediaAsset.from_path — reads file, computes hash from bytes
  - MediaAsset.to_dict / from_dict round-trip
  - MediaAsset.to_json
  - Content identity: same bytes → same hash
  - Default field values
"""
from __future__ import annotations

import hashlib
import json


# ── MediaType ─────────────────────────────────────────────────────────────────

def test_media_type_from_extension_image():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_extension(".jpg") == MediaType.IMAGE
    assert MediaType.from_extension(".PNG") == MediaType.IMAGE
    assert MediaType.from_extension(".webp") == MediaType.IMAGE


def test_media_type_from_extension_video():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_extension(".mp4") == MediaType.VIDEO
    assert MediaType.from_extension(".MOV") == MediaType.VIDEO


def test_media_type_from_extension_audio():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_extension(".mp3") == MediaType.AUDIO
    assert MediaType.from_extension(".flac") == MediaType.AUDIO


def test_media_type_from_extension_gif():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_extension(".gif") == MediaType.GIF


def test_media_type_from_extension_unknown():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_extension(".xyz") == MediaType.UNKNOWN


def test_media_type_from_path(tmp_path):
    from browsermind_core.media.media_asset import MediaType
    p = tmp_path / "photo.jpg"
    p.touch()
    assert MediaType.from_path(p) == MediaType.IMAGE


def test_media_type_from_mime_image():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("image/jpeg") == MediaType.IMAGE
    assert MediaType.from_mime("image/png") == MediaType.IMAGE


def test_media_type_from_mime_gif():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("image/gif") == MediaType.GIF


def test_media_type_from_mime_video():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("video/mp4") == MediaType.VIDEO


def test_media_type_from_mime_audio():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("audio/mpeg") == MediaType.AUDIO


def test_media_type_from_mime_with_params():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("image/png; charset=utf-8") == MediaType.IMAGE


def test_media_type_from_mime_unknown():
    from browsermind_core.media.media_asset import MediaType
    assert MediaType.from_mime("application/octet-stream") == MediaType.UNKNOWN


# ── MediaSource ───────────────────────────────────────────────────────────────

def test_media_source_from_url_youtube():
    from browsermind_core.media.media_asset import MediaSource
    assert MediaSource.from_url("https://www.youtube.com/watch?v=abc") == MediaSource.YOUTUBE
    assert MediaSource.from_url("https://youtu.be/abc") == MediaSource.YOUTUBE


def test_media_source_from_url_pinterest():
    from browsermind_core.media.media_asset import MediaSource
    assert MediaSource.from_url("https://www.pinterest.com/pin/123") == MediaSource.PINTEREST


def test_media_source_from_url_discord():
    from browsermind_core.media.media_asset import MediaSource
    assert MediaSource.from_url("https://cdn.discordapp.com/attachments/abc") == MediaSource.DISCORD


def test_media_source_from_url_reddit():
    from browsermind_core.media.media_asset import MediaSource
    assert MediaSource.from_url("https://reddit.com/r/python") == MediaSource.REDDIT


def test_media_source_from_url_direct_fallback():
    from browsermind_core.media.media_asset import MediaSource
    assert MediaSource.from_url("https://somerandomblog.com/img.png") == MediaSource.DIRECT


# ── _compute_hash ─────────────────────────────────────────────────────────────

def test_compute_hash_deterministic():
    from browsermind_core.media.media_asset import _compute_hash
    data = b"hello world"
    assert _compute_hash(data) == _compute_hash(data)


def test_compute_hash_is_sha256():
    from browsermind_core.media.media_asset import _compute_hash
    data = b"test content"
    expected = hashlib.sha256(data).hexdigest()
    assert _compute_hash(data) == expected


def test_compute_hash_different_for_different_data():
    from browsermind_core.media.media_asset import _compute_hash
    assert _compute_hash(b"aaa") != _compute_hash(b"bbb")


# ── MediaAsset.from_bytes ─────────────────────────────────────────────────────

def test_from_bytes_sets_content_hash():
    from browsermind_core.media.media_asset import MediaAsset, _compute_hash
    data  = b"fake image bytes"
    asset = MediaAsset.from_bytes(data, source_url="https://example.com/img.png")
    assert asset.content_hash == _compute_hash(data)


def test_from_bytes_detects_source():
    from browsermind_core.media.media_asset import MediaAsset, MediaSource
    asset = MediaAsset.from_bytes(b"x", source_url="https://youtube.com/watch?v=1")
    assert asset.source == MediaSource.YOUTUBE


def test_from_bytes_sets_media_type():
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    asset = MediaAsset.from_bytes(b"x", source_url="https://example.com/vid.mp4",
                                  media_type=MediaType.VIDEO)
    assert asset.media_type == MediaType.VIDEO


def test_from_bytes_generates_unique_asset_ids():
    from browsermind_core.media.media_asset import MediaAsset
    a1 = MediaAsset.from_bytes(b"data", source_url="https://x.com/a")
    a2 = MediaAsset.from_bytes(b"data", source_url="https://x.com/a")
    assert a1.asset_id != a2.asset_id  # UUIDs are unique
    assert a1.content_hash == a2.content_hash  # but hash is same


def test_from_bytes_acquired_at_set():
    from browsermind_core.media.media_asset import MediaAsset
    asset = MediaAsset.from_bytes(b"x", source_url="https://example.com/x")
    assert asset.acquired_at is not None


# ── MediaAsset.from_path ──────────────────────────────────────────────────────

def test_from_path_reads_bytes(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset, _compute_hash
    p = tmp_path / "test.png"
    p.write_bytes(b"png content")
    asset = MediaAsset.from_path(p)
    assert asset.content_hash == _compute_hash(b"png content")
    assert asset.local_path == str(p)


def test_from_path_sets_title_from_stem(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset
    p = tmp_path / "my_photo.jpg"
    p.write_bytes(b"jpg")
    asset = MediaAsset.from_path(p)
    assert asset.title == "my_photo"


def test_from_path_detects_media_type(tmp_path):
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"mp4")
    asset = MediaAsset.from_path(p)
    assert asset.media_type == MediaType.VIDEO


# ── to_dict / from_dict round-trip ────────────────────────────────────────────

def test_round_trip_dict():
    from browsermind_core.media.media_asset import MediaAsset
    asset = MediaAsset.from_bytes(b"data", source_url="https://imgur.com/x.png",
                                  title="Test Image", author="alice")
    asset.tags        = ["a", "b"]
    asset.collections = ["nature"]
    asset.uploaded_to = ["discord"]
    d      = asset.to_dict()
    cloned = MediaAsset.from_dict(d)
    assert cloned.content_hash  == asset.content_hash
    assert cloned.source        == asset.source
    assert cloned.title         == "Test Image"
    assert cloned.author        == "alice"
    assert cloned.tags          == ["a", "b"]
    assert cloned.collections   == ["nature"]
    assert cloned.uploaded_to   == ["discord"]


def test_to_json_is_valid_json():
    from browsermind_core.media.media_asset import MediaAsset
    asset = MediaAsset.from_bytes(b"x", source_url="https://example.com/x")
    parsed = json.loads(asset.to_json())
    assert "content_hash" in parsed
    assert "asset_id" in parsed


def test_from_dict_handles_missing_optional_fields():
    from browsermind_core.media.media_asset import MediaAsset
    d = {"content_hash": "abc123", "source_url": "https://x.com"}
    asset = MediaAsset.from_dict(d)
    assert asset.content_hash == "abc123"
    assert asset.tags == []
    assert asset.local_path is None
