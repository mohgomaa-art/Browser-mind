"""Tests for media acquisition adapters.

Covers:
  - AcquisitionResult.ok / fail constructors
  - GenericHTTPAdapter.can_handle
  - GenericHTTPAdapter.acquire — success path (mocked urllib)
  - GenericHTTPAdapter.acquire — HTTP error path
  - GenericHTTPAdapter.acquire — stores to vault when vault provided
  - YouTubeAdapter.can_handle
  - YouTubeAdapter._extract_id — standard, youtu.be, shorts
  - YouTubeAdapter.acquire falls back to thumbnail when yt-dlp absent
  - PinterestAdapter.can_handle
  - PinterestAdapter.acquire without page → error
  - InstagramAdapter.can_handle
  - InstagramAdapter.acquire without page → error
  - DiscordAdapter.can_handle
  - DiscordAdapter.acquire CDN URL → GenericHTTP path
  - DiscordAdapter.acquire non-CDN without page → error
  - MediaAdapter.acquire_to_vault convenience method
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── AcquisitionResult ─────────────────────────────────────────────────────────

def test_acquisition_result_ok():
    from browsermind_core.media.adapters.base import AcquisitionResult
    from browsermind_core.media.media_asset import MediaAsset
    asset  = MediaAsset.from_bytes(b"x", source_url="https://example.com/x")
    result = AcquisitionResult.ok(asset)
    assert result.success is True
    assert result.asset is asset
    assert result.error is None


def test_acquisition_result_fail():
    from browsermind_core.media.adapters.base import AcquisitionResult
    result = AcquisitionResult.fail("https://example.com/x", "HTTP 404")
    assert result.success is False
    assert result.error == "HTTP 404"
    assert result.source_url == "https://example.com/x"


# ── GenericHTTPAdapter ────────────────────────────────────────────────────────

def test_generic_can_handle_http():
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    a = GenericHTTPAdapter()
    assert a.can_handle("https://example.com/img.png")
    assert a.can_handle("http://example.com/img.png")
    assert not a.can_handle("ftp://example.com/img.png")


@pytest.mark.asyncio
async def test_generic_acquire_success():
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    from browsermind_core.media.media_asset import MediaType

    fake_data = b"fake image bytes"

    class _FakeResp:
        headers = {"Content-Type": "image/png"}
        def read(self):
            return fake_data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        result = await GenericHTTPAdapter().acquire("https://example.com/img.png")

    assert result.success is True
    assert result.asset.media_type == MediaType.IMAGE
    assert result.asset.content_hash != ""


@pytest.mark.asyncio
async def test_generic_acquire_http_error():
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        url="x", code=404, msg="Not Found", hdrs={}, fp=None
    )):
        result = await GenericHTTPAdapter().acquire("https://example.com/missing.png")

    assert result.success is False
    assert "404" in result.error


@pytest.mark.asyncio
async def test_generic_acquire_stores_to_vault(tmp_path):
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    from browsermind_core.media.media_vault import MediaVault

    vault     = MediaVault(root=tmp_path)
    fake_data = b"image bytes"

    class _FakeResp:
        headers = {"Content-Type": "image/jpeg"}
        def read(self):
            return fake_data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        result = await GenericHTTPAdapter().acquire(
            "https://example.com/pic.jpg", vault=vault
        )

    assert result.success
    assert vault.exists(result.asset.content_hash)


# ── YouTubeAdapter ────────────────────────────────────────────────────────────

def test_youtube_can_handle():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    assert a.can_handle("https://www.youtube.com/watch?v=abc123")
    assert a.can_handle("https://youtu.be/abc123")
    assert not a.can_handle("https://vimeo.com/123")


def test_youtube_extract_id_standard():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    assert a._extract_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_extract_id_short():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    assert a._extract_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_extract_id_shorts():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    assert a._extract_id("https://www.youtube.com/shorts/abc123") == "abc123"


def test_youtube_extract_id_invalid():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    assert a._extract_id("https://example.com/not-youtube") is None


@pytest.mark.asyncio
async def test_youtube_acquire_falls_back_to_thumbnail():
    from browsermind_core.media.adapters.youtube import YouTubeAdapter

    fake_data = b"thumbnail bytes"

    class _FakeResp:
        headers = {"Content-Type": "image/jpeg"}
        def read(self):
            return fake_data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    # Force the thumbnail fallback regardless of yt-dlp availability
    async def _raise_import(*args, **kwargs):
        raise ImportError("yt-dlp not available")

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        with patch.object(YouTubeAdapter, "_acquire_with_ytdlp", _raise_import):
            result = await YouTubeAdapter().acquire(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )

    assert result.success is True
    assert result.asset.metadata.get("acquired_as") == "thumbnail_only"


# ── PinterestAdapter ──────────────────────────────────────────────────────────

def test_pinterest_can_handle():
    from browsermind_core.media.adapters.pinterest import PinterestAdapter
    a = PinterestAdapter()
    assert a.can_handle("https://www.pinterest.com/pin/123456")
    assert a.can_handle("https://pin.it/abc")
    assert not a.can_handle("https://twitter.com/x")


@pytest.mark.asyncio
async def test_pinterest_acquire_no_page_returns_error():
    from browsermind_core.media.adapters.pinterest import PinterestAdapter
    result = await PinterestAdapter().acquire("https://www.pinterest.com/pin/123")
    assert result.success is False
    assert "page" in result.error.lower()


# ── InstagramAdapter ──────────────────────────────────────────────────────────

def test_instagram_can_handle():
    from browsermind_core.media.adapters.instagram import InstagramAdapter
    a = InstagramAdapter()
    assert a.can_handle("https://www.instagram.com/p/abc")
    assert not a.can_handle("https://twitter.com/x")


@pytest.mark.asyncio
async def test_instagram_acquire_no_page_returns_error():
    from browsermind_core.media.adapters.instagram import InstagramAdapter
    result = await InstagramAdapter().acquire("https://www.instagram.com/p/abc")
    assert result.success is False
    assert "page" in result.error.lower()


# ── DiscordAdapter ────────────────────────────────────────────────────────────

def test_discord_can_handle():
    from browsermind_core.media.adapters.discord import DiscordAdapter
    a = DiscordAdapter()
    assert a.can_handle("https://cdn.discordapp.com/attachments/123/456/file.png")
    assert a.can_handle("https://discord.com/channels/123/456")
    assert not a.can_handle("https://telegram.org/file/abc")


@pytest.mark.asyncio
async def test_discord_acquire_cdn_url():
    from browsermind_core.media.adapters.discord import DiscordAdapter
    from browsermind_core.media.media_asset import MediaSource

    fake_data = b"discord image"

    class _FakeResp:
        headers = {"Content-Type": "image/png"}
        def read(self):
            return fake_data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    cdn_url = "https://cdn.discordapp.com/attachments/123/456/img.png"
    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        result = await DiscordAdapter().acquire(cdn_url)

    assert result.success is True
    assert result.asset.source == MediaSource.DISCORD


@pytest.mark.asyncio
async def test_discord_acquire_non_cdn_no_page_returns_error():
    from browsermind_core.media.adapters.discord import DiscordAdapter
    result = await DiscordAdapter().acquire("https://discord.com/channels/123/456/789")
    assert result.success is False
    assert "page" in result.error.lower() or "CDN" in result.error


# ── MediaAdapter.acquire_to_vault ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acquire_to_vault_stores_asset(tmp_path):
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    from browsermind_core.media.media_vault import MediaVault

    vault     = MediaVault(root=tmp_path)
    fake_data = b"vault image"

    class _FakeResp:
        headers = {"Content-Type": "image/png"}
        def read(self):
            return fake_data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        result = await GenericHTTPAdapter().acquire_to_vault(
            "https://example.com/img.png", vault=vault, tags=["wall"]
        )

    assert result.success
    stored = vault.get(result.asset.content_hash)
    assert stored is not None
    assert "wall" in stored.tags
