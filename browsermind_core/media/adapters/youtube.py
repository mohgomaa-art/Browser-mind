"""YouTubeAdapter — acquire video or thumbnail from YouTube.

Two modes:
  1. Full download  — uses yt-dlp if installed (pip install yt-dlp)
  2. Thumbnail only — fallback using maxresdefault.jpg via GenericHTTPAdapter

The adapter never raises. Errors are captured in AcquisitionResult.error.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from browsermind_core.media.adapters.base import MediaAdapter, AcquisitionResult
from browsermind_core.media.media_asset import MediaAsset, MediaSource, MediaType


class YouTubeAdapter(MediaAdapter):
    source = MediaSource.YOUTUBE

    _DOMAINS = ("youtube.com", "youtu.be")

    def can_handle(self, url: str) -> bool:
        return any(d in url for d in self._DOMAINS)

    async def acquire(self, url: str, page=None, vault=None) -> AcquisitionResult:
        video_id = self._extract_id(url)
        if not video_id:
            return AcquisitionResult.fail(url, "Could not extract YouTube video ID")
        try:
            return await self._acquire_with_ytdlp(url, video_id, vault)
        except ImportError:
            return await self._acquire_thumbnail(url, video_id, vault)
        except Exception as exc:
            return AcquisitionResult.fail(url, str(exc))

    async def _acquire_with_ytdlp(
        self, url: str, video_id: str, vault
    ) -> AcquisitionResult:
        import yt_dlp
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            opts = {
                "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
                "format":  "bestaudio/best",
                "quiet":   True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info  = ydl.extract_info(url, download=True)
                files = list(Path(tmpdir).iterdir())
                if not files:
                    return AcquisitionResult.fail(url, "yt-dlp produced no output file")
                out_file = files[0]
                data     = out_file.read_bytes()
                mt       = MediaType.from_path(out_file)

            asset = MediaAsset.from_bytes(
                data=data,
                source_url=url,
                media_type=mt,
                source=self.source,
                title=info.get("title", ""),
                author=info.get("uploader", ""),
            )
            asset.metadata.update({
                "duration":    info.get("duration"),
                "view_count":  info.get("view_count"),
                "upload_date": info.get("upload_date"),
                "description": (info.get("description") or "")[:500],
                "thumbnail":   info.get("thumbnail"),
                "video_id":    video_id,
            })
            if vault is not None:
                asset = vault.store(asset, data=data)
        return AcquisitionResult.ok(asset)

    async def _acquire_thumbnail(
        self, url: str, video_id: str, vault
    ) -> AcquisitionResult:
        from browsermind_core.media.adapters.generic import GenericHTTPAdapter
        thumb_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        result    = await GenericHTTPAdapter().acquire(thumb_url, vault=vault)
        if result.success and result.asset is not None:
            result.asset.source      = self.source
            result.asset.source_url  = url
            result.asset.metadata["video_id"]    = video_id
            result.asset.metadata["acquired_as"] = "thumbnail_only"
        return result

    def _extract_id(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            return parsed.path.lstrip("/").split("?")[0] or None
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "v"):
            return parts[1]
        return None
