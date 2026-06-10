"""GenericHTTPAdapter — direct HTTP download fallback for any public URL.

Uses stdlib urllib only — no extra dependencies. Suitable for:
  - Direct image/video CDN links
  - Public APIs that return media
  - Any URL that responds to a HEAD/GET with media content

For authenticated or JS-rendered sources, use a Playwright-based adapter.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error

from browsermind_core.media.adapters.base import MediaAdapter, AcquisitionResult
from browsermind_core.media.media_asset import MediaAsset, MediaSource, MediaType


class GenericHTTPAdapter(MediaAdapter):
    """Download any public media URL via HTTP/HTTPS."""
    source = MediaSource.DIRECT

    _HEADERS = {"User-Agent": "BrowserMind/1.0 (media-runtime)"}

    def can_handle(self, url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

    async def acquire(
        self,
        url: str,
        page=None,
        vault=None,
    ) -> AcquisitionResult:
        try:
            req = urllib.request.Request(url, headers=self._HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data         = resp.read()

            media_type = MediaType.from_mime(content_type)
            if media_type == MediaType.UNKNOWN:
                ext        = Path(urlparse(url).path).suffix
                media_type = MediaType.from_extension(ext)

            asset = MediaAsset.from_bytes(
                data=data,
                source_url=url,
                media_type=media_type,
                source=MediaSource.from_url(url),
                title=Path(urlparse(url).path).stem,
            )
            asset.metadata["content_type"] = content_type
            asset.metadata["size_bytes"]   = len(data)

            if vault is not None:
                asset = vault.store(asset, data=data)
            return AcquisitionResult.ok(asset)

        except urllib.error.HTTPError as exc:
            return AcquisitionResult.fail(url, f"HTTP {exc.code}: {exc.reason}")
        except urllib.error.URLError as exc:
            return AcquisitionResult.fail(url, f"URL error: {exc.reason}")
        except Exception as exc:
            return AcquisitionResult.fail(url, str(exc))
