"""MediaAdapter — base class and AcquisitionResult for all acquisition adapters.

Every adapter implements:
  can_handle(url) → bool
  acquire(url, page=None, vault=None) → AcquisitionResult

The page parameter is an optional Playwright Page object. Adapters that
download directly via HTTP (GenericHTTPAdapter, YouTubeAdapter without yt-dlp)
ignore it. Adapters that need authenticated browser context (PinterestAdapter,
InstagramAdapter) require it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from browsermind_core.media.media_asset import MediaAsset


@dataclass
class AcquisitionResult:
    """Outcome of one MediaAdapter.acquire() call."""
    success: bool = False
    asset: Optional[MediaAsset] = None
    error: Optional[str] = None
    source_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, asset: MediaAsset) -> "AcquisitionResult":
        return cls(success=True, asset=asset, source_url=asset.source_url)

    @classmethod
    def fail(cls, url: str, reason: str) -> "AcquisitionResult":
        return cls(success=False, error=reason, source_url=url)


class MediaAdapter:
    """Base class for media acquisition adapters.

    Subclasses must set the class-level `source` attribute to a MediaSource
    constant and implement can_handle() and acquire().
    """
    source: str = "unknown"

    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    async def acquire(
        self,
        url: str,
        page=None,
        vault=None,
    ) -> AcquisitionResult:
        raise NotImplementedError

    async def acquire_to_vault(
        self,
        url: str,
        vault,
        page=None,
        tags: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
    ) -> AcquisitionResult:
        """Convenience: acquire then immediately store in vault."""
        result = await self.acquire(url, page=page)
        if not result.success or result.asset is None:
            return result
        asset = result.asset
        if tags:
            asset.tags = list(dict.fromkeys(asset.tags + list(tags)))
        if collections:
            asset.collections = list(dict.fromkeys(asset.collections + list(collections)))
        data: Optional[bytes] = None
        if asset.local_path:
            p = Path(asset.local_path)
            if p.exists():
                data = p.read_bytes()
        stored = vault.store(asset, data=data)
        return AcquisitionResult.ok(stored)
