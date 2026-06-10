"""MediaUploader — base class and UploadResult for all upload adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from browsermind_core.media.media_asset import MediaAsset


@dataclass
class UploadResult:
    success: bool = False
    asset: Optional[MediaAsset] = None
    destination_url: Optional[str] = None
    destination_key: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, asset: MediaAsset, url: str = "", key: str = "") -> "UploadResult":
        return cls(success=True, asset=asset, destination_url=url, destination_key=key)

    @classmethod
    def fail(cls, reason: str) -> "UploadResult":
        return cls(success=False, error=reason)


class MediaUploader:
    """Base class for media upload adapters."""
    destination_key: str = "unknown"

    def can_upload(self, asset: MediaAsset) -> bool:
        raise NotImplementedError

    async def upload(self, asset: MediaAsset, page=None, **kwargs) -> UploadResult:
        raise NotImplementedError
