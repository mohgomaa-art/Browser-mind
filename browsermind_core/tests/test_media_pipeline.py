"""Tests for MediaPipeline, PipelineStep subclasses, and PipelineResult.

Covers:
  - Step dataclasses exist and have expected fields
  - PipelineResult defaults
  - run() with AcquireStep → calls adapter.acquire
  - run() with TagStep → mutates asset.tags and .collections
  - run() with AcquireStep + TagStep — end-to-end with mocked adapter
  - run() stops on first failure and reports step index
  - run() with no steps and pre-supplied asset → success
  - _default_adapter returns correct type per source
  - _default_uploader loads correct type per destination
  - UploadStep failure → pipeline error
  - step_log populated for each step
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Step dataclasses ──────────────────────────────────────────────────────────

def test_acquire_step_has_url():
    from browsermind_core.media.pipeline import AcquireStep
    step = AcquireStep(url="https://example.com/img.png")
    assert step.url == "https://example.com/img.png"
    assert step.adapter_source is None


def test_transform_step_defaults():
    from browsermind_core.media.pipeline import TransformStep
    step = TransformStep()
    assert step.resize is None
    assert step.strip_metadata is False


def test_upload_step_has_destination():
    from browsermind_core.media.pipeline import UploadStep
    step = UploadStep(destination="discord")
    assert step.destination == "discord"
    assert step.kwargs == {}


def test_tag_step_defaults():
    from browsermind_core.media.pipeline import TagStep
    step = TagStep()
    assert step.tags == []
    assert step.collections == []


# ── PipelineResult ────────────────────────────────────────────────────────────

def test_pipeline_result_defaults():
    from browsermind_core.media.pipeline import PipelineResult
    r = PipelineResult(success=True)
    assert r.final_asset is None
    assert r.steps_completed == 0
    assert r.error is None
    assert r.step_log == []


# ── run() with pre-supplied asset and no steps ────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_no_steps_returns_supplied_asset():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.media_asset import MediaAsset
    asset    = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    pipeline = MediaPipeline([])
    result   = await pipeline.run(asset=asset)
    assert result.success is True
    assert result.final_asset is asset


# ── run() with AcquireStep ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_acquire_step_calls_adapter():
    from browsermind_core.media.pipeline import MediaPipeline, AcquireStep
    from browsermind_core.media.adapters.base import AcquisitionResult
    from browsermind_core.media.media_asset import MediaAsset

    fake_asset  = MediaAsset.from_bytes(b"data", source_url="https://x.com/x")
    mock_adapter = MagicMock()
    mock_adapter.acquire = AsyncMock(return_value=AcquisitionResult.ok(fake_asset))

    pipeline = MediaPipeline(
        [AcquireStep(url="https://x.com/x", adapter_source="direct")],
        adapters={"direct": mock_adapter},
    )
    result = await pipeline.run()
    assert result.success is True
    assert result.final_asset is fake_asset
    mock_adapter.acquire.assert_called_once()


# ── run() with TagStep ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_tag_step_mutates_asset():
    from browsermind_core.media.pipeline import MediaPipeline, TagStep
    from browsermind_core.media.media_asset import MediaAsset

    asset    = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    pipeline = MediaPipeline([TagStep(tags=["nature"], collections=["Outdoors"])])
    result   = await pipeline.run(asset=asset)
    assert result.success is True
    assert "nature" in result.final_asset.tags
    assert "Outdoors" in result.final_asset.collections


# ── Acquire + Tag combined ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_acquire_then_tag():
    from browsermind_core.media.pipeline import MediaPipeline, AcquireStep, TagStep
    from browsermind_core.media.adapters.base import AcquisitionResult
    from browsermind_core.media.media_asset import MediaAsset

    fake_asset   = MediaAsset.from_bytes(b"d", source_url="https://x.com/d")
    mock_adapter = MagicMock()
    mock_adapter.acquire = AsyncMock(return_value=AcquisitionResult.ok(fake_asset))

    pipeline = MediaPipeline(
        [
            AcquireStep(url="https://x.com/d", adapter_source="direct"),
            TagStep(tags=["photo"]),
        ],
        adapters={"direct": mock_adapter},
    )
    result = await pipeline.run()
    assert result.success is True
    assert "photo" in result.final_asset.tags
    assert result.steps_completed == 2


# ── Failure stops pipeline ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_stops_on_acquire_failure():
    from browsermind_core.media.pipeline import MediaPipeline, AcquireStep, TagStep
    from browsermind_core.media.adapters.base import AcquisitionResult

    mock_adapter = MagicMock()
    mock_adapter.acquire = AsyncMock(return_value=AcquisitionResult.fail("https://x.com/x", "HTTP 404"))

    pipeline = MediaPipeline(
        [
            AcquireStep(url="https://x.com/x", adapter_source="direct"),
            TagStep(tags=["should_not_run"]),
        ],
        adapters={"direct": mock_adapter},
    )
    result = await pipeline.run()
    assert result.success is False
    assert result.error is not None
    assert "Step 0" in result.error
    assert result.steps_completed == 0


# ── step_log ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_step_log_populated():
    from browsermind_core.media.pipeline import MediaPipeline, TagStep
    from browsermind_core.media.media_asset import MediaAsset

    asset    = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    pipeline = MediaPipeline([TagStep(tags=["a"]), TagStep(tags=["b"])])
    result   = await pipeline.run(asset=asset)
    assert len(result.step_log) == 2
    assert result.step_log[0]["ok"] is True
    assert result.step_log[1]["ok"] is True


@pytest.mark.asyncio
async def test_pipeline_step_log_records_failure():
    from browsermind_core.media.pipeline import MediaPipeline, AcquireStep
    from browsermind_core.media.adapters.base import AcquisitionResult

    mock_adapter = MagicMock()
    mock_adapter.acquire = AsyncMock(return_value=AcquisitionResult.fail("u", "boom"))

    pipeline = MediaPipeline(
        [AcquireStep(url="u", adapter_source="direct")],
        adapters={"direct": mock_adapter},
    )
    result = await pipeline.run()
    assert result.step_log[0]["ok"] is False
    assert "boom" in result.step_log[0]["error"]


# ── _default_adapter ──────────────────────────────────────────────────────────

def test_default_adapter_youtube():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.adapters.youtube import YouTubeAdapter
    from browsermind_core.media.media_asset import MediaSource
    p       = MediaPipeline([])
    adapter = p._default_adapter(MediaSource.YOUTUBE)
    assert isinstance(adapter, YouTubeAdapter)


def test_default_adapter_pinterest():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.adapters.pinterest import PinterestAdapter
    from browsermind_core.media.media_asset import MediaSource
    p       = MediaPipeline([])
    adapter = p._default_adapter(MediaSource.PINTEREST)
    assert isinstance(adapter, PinterestAdapter)


def test_default_adapter_generic_fallback():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.adapters.generic import GenericHTTPAdapter
    p       = MediaPipeline([])
    adapter = p._default_adapter("unknown_source")
    assert isinstance(adapter, GenericHTTPAdapter)


# ── _default_uploader ─────────────────────────────────────────────────────────

def test_default_uploader_discord():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.upload.discord_uploader import DiscordUploader
    p = MediaPipeline([])
    p._load_default_uploader("discord")
    assert isinstance(p._uploaders["discord"], DiscordUploader)


def test_default_uploader_github():
    from browsermind_core.media.pipeline import MediaPipeline
    from browsermind_core.media.upload.github_uploader import GitHubUploader
    p = MediaPipeline([])
    p._load_default_uploader("github")
    assert isinstance(p._uploaders["github"], GitHubUploader)


# ── UploadStep failure ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_upload_failure():
    from browsermind_core.media.pipeline import MediaPipeline, UploadStep
    from browsermind_core.media.media_asset import MediaAsset
    from browsermind_core.media.upload.base import UploadResult

    mock_uploader = MagicMock()
    mock_uploader.upload = AsyncMock(return_value=UploadResult.fail("upload failed"))

    asset    = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    pipeline = MediaPipeline(
        [UploadStep(destination="discord")],
        uploaders={"discord": mock_uploader},
    )
    result = await pipeline.run(asset=asset)
    assert result.success is False
    assert "upload failed" in result.error
