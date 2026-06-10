"""MediaPipeline — compose acquisition, transformation, tagging, and upload.

A pipeline is a sequence of PipelineStep objects that each receive and return
a MediaAsset. Steps are executed in order; any failure stops the pipeline and
reports the failing step.

Example
───────
  from browsermind_core.media.pipeline import (
      MediaPipeline, AcquireStep, TransformStep, TagStep, UploadStep,
  )

  pipeline = MediaPipeline([
      AcquireStep(url="https://pinterest.com/pin/..."),
      TransformStep(resize=(1920, 1080), convert_to="jpg"),
      TagStep(tags=["wallpaper"], collections=["4K Wallpapers"]),
      UploadStep(destination="discord", kwargs={"message": "Here!"}),
  ])
  result = await pipeline.run(vault=vault, page=page)

Custom adapters / uploaders
───────────────────────────
  pipeline = MediaPipeline(steps, adapters={"youtube": MyCustomYTAdapter()})

When adapters/uploaders are not supplied, defaults from the adapters/ and
upload/ sub-packages are used automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from browsermind_core.media.media_asset import MediaAsset


# ── Step types ────────────────────────────────────────────────────────────────

@dataclass
class PipelineStep:
    pass


@dataclass
class AcquireStep(PipelineStep):
    url: str
    adapter_source: Optional[str] = None  # MediaSource constant; None = auto-detect


@dataclass
class TransformStep(PipelineStep):
    resize: Optional[tuple] = None
    convert_to: Optional[str] = None
    compress_quality: Optional[int] = None
    crop: Optional[tuple] = None
    watermark_text: Optional[str] = None
    strip_metadata: bool = False


@dataclass
class UploadStep(PipelineStep):
    destination: str
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TagStep(PipelineStep):
    tags: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    success: bool
    final_asset: Optional[MediaAsset] = None
    steps_completed: int = 0
    error: Optional[str] = None
    step_log: List[Dict[str, Any]] = field(default_factory=list)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class MediaPipeline:
    """Execute a sequence of PipelineStep objects against one MediaAsset."""

    def __init__(
        self,
        steps: List[PipelineStep],
        adapters: Optional[Dict[str, Any]] = None,
        uploaders: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._steps     = steps
        self._adapters  = dict(adapters or {})
        self._uploaders = dict(uploaders or {})

    async def run(
        self,
        vault=None,
        page=None,
        asset: Optional[MediaAsset] = None,
    ) -> PipelineResult:
        result  = PipelineResult(success=False)
        current = asset

        for i, step in enumerate(self._steps):
            step_type = type(step).__name__
            try:
                if isinstance(step, AcquireStep):
                    current = await self._run_acquire(step, vault, page)

                elif isinstance(step, TransformStep):
                    if current is None:
                        raise RuntimeError("TransformStep: no asset available")
                    current = self._run_transform(step, current)

                elif isinstance(step, TagStep):
                    if current is not None:
                        current.tags        = list(dict.fromkeys(current.tags + step.tags))
                        current.collections = list(dict.fromkeys(current.collections + step.collections))

                elif isinstance(step, UploadStep):
                    if current is None:
                        raise RuntimeError("UploadStep: no asset available")
                    current = await self._run_upload(step, current, page)

                result.step_log.append({"step": i, "type": step_type, "ok": True})
                result.steps_completed = i + 1

            except Exception as exc:
                result.step_log.append({"step": i, "type": step_type, "ok": False, "error": str(exc)})
                result.error = f"Step {i} ({step_type}): {exc}"
                return result

        result.success     = True
        result.final_asset = current
        return result

    # ── Step executors ─────────────────────────────────────────────────────────

    async def _run_acquire(
        self, step: AcquireStep, vault, page
    ) -> MediaAsset:
        from browsermind_core.media.media_asset import MediaSource
        source  = step.adapter_source or MediaSource.from_url(step.url)
        adapter = self._adapters.get(source) or self._default_adapter(source)
        result  = await adapter.acquire(step.url, page=page, vault=vault)
        if not result.success:
            raise RuntimeError(result.error or "acquisition failed")
        return result.asset  # type: ignore[return-value]

    def _run_transform(self, step: TransformStep, asset: MediaAsset) -> MediaAsset:
        from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
        opts   = TransformOptions(
            resize=step.resize,
            convert_to=step.convert_to,
            compress_quality=step.compress_quality,
            crop=step.crop,
            watermark_text=step.watermark_text,
            strip_metadata=step.strip_metadata,
        )
        result = MediaTransformer().transform(asset, opts)
        if not result.success:
            raise RuntimeError(result.error or "transform failed")
        return result.asset  # type: ignore[return-value]

    async def _run_upload(
        self, step: UploadStep, asset: MediaAsset, page
    ) -> MediaAsset:
        uploader = self._uploaders.get(step.destination)
        if uploader is None:
            self._load_default_uploader(step.destination)
            uploader = self._uploaders.get(step.destination)
        if uploader is None:
            raise RuntimeError(f"No uploader registered for destination '{step.destination}'")
        result = await uploader.upload(asset, page=page, **step.kwargs)
        if not result.success:
            raise RuntimeError(result.error or "upload failed")
        return result.asset or asset

    # ── Default adapter/uploader lookup ───────────────────────────────────────

    def _default_adapter(self, source: str):
        from browsermind_core.media.media_asset import MediaSource
        from browsermind_core.media.adapters.generic import GenericHTTPAdapter
        from browsermind_core.media.adapters.youtube import YouTubeAdapter
        from browsermind_core.media.adapters.pinterest import PinterestAdapter
        from browsermind_core.media.adapters.instagram import InstagramAdapter
        from browsermind_core.media.adapters.discord import DiscordAdapter

        _MAP = {
            MediaSource.YOUTUBE:   YouTubeAdapter,
            MediaSource.PINTEREST: PinterestAdapter,
            MediaSource.INSTAGRAM: InstagramAdapter,
            MediaSource.DISCORD:   DiscordAdapter,
        }
        return _MAP.get(source, GenericHTTPAdapter)()

    def _load_default_uploader(self, destination: str) -> None:
        from browsermind_core.media.upload.discord_uploader import DiscordUploader
        from browsermind_core.media.upload.reddit_uploader import RedditUploader
        from browsermind_core.media.upload.github_uploader import GitHubUploader

        _MAP = {
            "discord": DiscordUploader,
            "reddit":  RedditUploader,
            "github":  GitHubUploader,
        }
        cls = _MAP.get(destination)
        if cls:
            self._uploaders[destination] = cls()
