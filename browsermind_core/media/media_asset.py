"""MediaAsset — the universal media object for the Media Runtime.

Every piece of media BrowserMind touches is represented as a MediaAsset.
Identity is content_hash (SHA-256 of file bytes). Two assets with the same
content_hash are the same asset regardless of source URL — deduplication
in the vault is automatic.

  Pinterest image → Vault → Transform → Discord
         ↑ all the same MediaAsset flowing through the pipeline
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── MediaType ─────────────────────────────────────────────────────────────────

class MediaType:
    IMAGE    = "image"
    VIDEO    = "video"
    AUDIO    = "audio"
    GIF      = "gif"
    DOCUMENT = "document"
    UNKNOWN  = "unknown"

    _EXT_MAP: Dict[str, str] = {
        ".jpg": IMAGE, ".jpeg": IMAGE, ".png": IMAGE, ".webp": IMAGE,
        ".svg": IMAGE, ".bmp": IMAGE, ".tiff": IMAGE, ".tif": IMAGE,
        ".mp4": VIDEO, ".avi": VIDEO, ".mov": VIDEO, ".mkv": VIDEO,
        ".webm": VIDEO, ".flv": VIDEO, ".wmv": VIDEO, ".m4v": VIDEO,
        ".mp3": AUDIO, ".wav": AUDIO, ".ogg": AUDIO, ".flac": AUDIO,
        ".aac": AUDIO, ".m4a": AUDIO, ".wma": AUDIO,
        ".gif": GIF,
        ".pdf": DOCUMENT, ".docx": DOCUMENT, ".txt": DOCUMENT,
    }

    @classmethod
    def from_extension(cls, ext: str) -> str:
        return cls._EXT_MAP.get(ext.lower(), cls.UNKNOWN)

    @classmethod
    def from_path(cls, path) -> str:
        return cls.from_extension(Path(path).suffix)

    @classmethod
    def from_mime(cls, mime: str) -> str:
        mime = mime.lower().split(";")[0].strip()
        if "gif" in mime:
            return cls.GIF
        if mime.startswith("image/"):
            return cls.IMAGE
        if mime.startswith("video/"):
            return cls.VIDEO
        if mime.startswith("audio/"):
            return cls.AUDIO
        if "pdf" in mime or "document" in mime:
            return cls.DOCUMENT
        return cls.UNKNOWN


# ── MediaSource ───────────────────────────────────────────────────────────────

class MediaSource:
    YOUTUBE   = "youtube"
    TIKTOK    = "tiktok"
    INSTAGRAM = "instagram"
    PINTEREST = "pinterest"
    REDDIT    = "reddit"
    X         = "x"
    THREADS   = "threads"
    DISCORD   = "discord"
    IMGUR     = "imgur"
    FLICKR    = "flickr"
    UNSPLASH  = "unsplash"
    DIRECT    = "direct"
    UNKNOWN   = "unknown"

    ALL = [
        YOUTUBE, TIKTOK, INSTAGRAM, PINTEREST, REDDIT, X, THREADS,
        DISCORD, IMGUR, FLICKR, UNSPLASH, DIRECT, UNKNOWN,
    ]

    _DOMAIN_MAP: Dict[str, str] = {
        "youtube.com": YOUTUBE, "youtu.be": YOUTUBE,
        "tiktok.com":   TIKTOK,
        "instagram.com": INSTAGRAM,
        "pinterest.com": PINTEREST, "pin.it": PINTEREST,
        "reddit.com":   REDDIT,  "redd.it": REDDIT,
        "twitter.com":  X,       "x.com": X,
        "threads.net":  THREADS,
        "discord.com":  DISCORD, "discordapp.com": DISCORD,
        "imgur.com":    IMGUR,
        "flickr.com":   FLICKR,
        "unsplash.com": UNSPLASH,
    }

    @classmethod
    def from_url(cls, url: str) -> str:
        lower = url.lower()
        for domain, source in cls._DOMAIN_MAP.items():
            if domain in lower:
                return source
        return cls.DIRECT


# ── Hash helper ───────────────────────────────────────────────────────────────

def _compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── MediaAsset ────────────────────────────────────────────────────────────────

@dataclass
class MediaAsset:
    """Universal media object.

    Fields
    ──────
    asset_id        UUID4 — unique per instance, not per content.
    content_hash    SHA-256 of file bytes — primary identity and dedup key.
    source          MediaSource constant. Auto-detected from source_url.
    source_url      Original URL the asset came from.
    media_type      MediaType constant.
    local_path      Absolute path to file on disk (set by vault on store).
    title           Human-readable title.
    author          Creator username or display name.
    tags            Free-form tag strings for filtering.
    metadata        Raw metadata dict (EXIF, ID3, ffprobe output, etc.).
    collections     Collection names this asset belongs to.
    understanding   Analysis results (OCR text, dominant_colors, perceptual_hash).
    acquired_at     ISO datetime string — when the asset was first acquired.
    uploaded_to     List of destination_key strings where this was uploaded.
    """
    asset_id: str
    content_hash: str
    source: str
    source_url: str
    media_type: str
    local_path: Optional[str] = None
    title: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    collections: List[str] = field(default_factory=list)
    understanding: Dict[str, Any] = field(default_factory=dict)
    acquired_at: Optional[str] = None
    uploaded_to: List[str] = field(default_factory=list)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        source_url: str,
        media_type: Optional[str] = None,
        source: Optional[str] = None,
        title: str = "",
        author: str = "",
    ) -> "MediaAsset":
        return cls(
            asset_id=str(uuid.uuid4()),
            content_hash=_compute_hash(data),
            source=source or MediaSource.from_url(source_url),
            source_url=source_url,
            media_type=media_type or MediaType.UNKNOWN,
            title=title,
            author=author,
            acquired_at=datetime.utcnow().isoformat(),
        )

    @classmethod
    def from_path(
        cls,
        path,
        source_url: str = "",
        source: Optional[str] = None,
        title: str = "",
        author: str = "",
    ) -> "MediaAsset":
        p = Path(path)
        data = p.read_bytes()
        detected_source = source or (MediaSource.from_url(source_url) if source_url else MediaSource.DIRECT)
        return cls(
            asset_id=str(uuid.uuid4()),
            content_hash=_compute_hash(data),
            source=detected_source,
            source_url=source_url,
            media_type=MediaType.from_path(p),
            local_path=str(p),
            title=title or p.stem,
            author=author,
            acquired_at=datetime.utcnow().isoformat(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id":     self.asset_id,
            "content_hash": self.content_hash,
            "source":       self.source,
            "source_url":   self.source_url,
            "media_type":   self.media_type,
            "local_path":   self.local_path,
            "title":        self.title,
            "author":       self.author,
            "tags":         list(self.tags),
            "metadata":     dict(self.metadata),
            "collections":  list(self.collections),
            "understanding": dict(self.understanding),
            "acquired_at":  self.acquired_at,
            "uploaded_to":  list(self.uploaded_to),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MediaAsset":
        return cls(
            asset_id=d.get("asset_id", str(uuid.uuid4())),
            content_hash=d["content_hash"],
            source=d.get("source", MediaSource.UNKNOWN),
            source_url=d.get("source_url", ""),
            media_type=d.get("media_type", MediaType.UNKNOWN),
            local_path=d.get("local_path"),
            title=d.get("title", ""),
            author=d.get("author", ""),
            tags=list(d.get("tags", [])),
            metadata=dict(d.get("metadata", {})),
            collections=list(d.get("collections", [])),
            understanding=dict(d.get("understanding", {})),
            acquired_at=d.get("acquired_at"),
            uploaded_to=list(d.get("uploaded_to", [])),
        )
