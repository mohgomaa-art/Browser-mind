"""MediaVault — content-addressed persistent store for MediaAsset objects.

Layout
──────
  <root>/vault/<hash[:2]>/<hash><ext>   ← file bytes (sharded by 2-char prefix)
  <root>/index/<hash>.json              ← MediaAsset JSON metadata

Deduplication
─────────────
Two assets with the same content_hash are stored once. Calling store() on a
duplicate merges tags and collections (union, preserving order) but leaves all
other fields unchanged unless overwrite_meta=True.

Atomic writes
─────────────
Both file and index writes go via <target>.tmp → rename, matching the
CapabilityHypothesisStore pattern used throughout the codebase.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from browsermind_core.media.media_asset import MediaAsset, MediaSource, MediaType


_DEFAULT_ROOT = Path.home() / ".browsermind" / "media"


class MediaVault:
    """Content-addressed persistent media library.

    Usage
    ─────
      vault = MediaVault()                          # default ~/.browsermind/media
      vault = MediaVault(root=tmp_path)             # test override

      asset = vault.store_file("photo.jpg", source_url="https://...", tags=["cat"])
      same  = vault.get(asset.content_hash)         # always the same object
      data  = vault.get_bytes(asset.content_hash)

      cats  = vault.by_tag("cat")
      imgs  = vault.by_type(MediaType.IMAGE)
      hits  = vault.search(query="kitten", source="pinterest")
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root      = Path(root) if root is not None else _DEFAULT_ROOT
        self._vault_dir = self._root / "vault"
        self._index_dir = self._root / "index"
        self._vault_dir.mkdir(parents=True, exist_ok=True)
        self._index_dir.mkdir(parents=True, exist_ok=True)

    # ── Store ──────────────────────────────────────────────────────────────────

    def store(
        self,
        asset: MediaAsset,
        data: Optional[bytes] = None,
        overwrite_meta: bool = False,
    ) -> MediaAsset:
        """Persist a MediaAsset. Returns canonical (possibly pre-existing) asset.

        If data is provided and the file does not yet exist, it is written.
        Duplicate content_hash without overwrite_meta → merge tags/collections.
        """
        existing = self.get(asset.content_hash)
        if existing is not None and not overwrite_meta:
            existing.tags        = list(dict.fromkeys(existing.tags + asset.tags))
            existing.collections = list(dict.fromkeys(existing.collections + asset.collections))
            self._save_index(existing)
            return existing

        if data is not None:
            ext       = self._ext_for(asset)
            file_path = self._file_path(asset.content_hash, ext)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                tmp = file_path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(file_path)
            asset.local_path = str(file_path)

        self._save_index(asset)
        return asset

    def store_file(
        self,
        file_path,
        source_url: str = "",
        source: Optional[str] = None,
        title: str = "",
        author: str = "",
        tags: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
    ) -> MediaAsset:
        """Create a MediaAsset from a file on disk and store it."""
        p    = Path(file_path)
        data = p.read_bytes()
        asset = MediaAsset.from_bytes(
            data=data,
            source_url=source_url,
            source=source,
            title=title or p.stem,
            author=author,
        )
        asset.media_type  = MediaType.from_path(p)
        asset.tags        = list(tags or [])
        asset.collections = list(collections or [])
        return self.store(asset, data=data)

    # ── Retrieve ───────────────────────────────────────────────────────────────

    def get(self, content_hash: str) -> Optional[MediaAsset]:
        p = self._index_path(content_hash)
        if not p.exists():
            return None
        try:
            return MediaAsset.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def get_bytes(self, content_hash: str) -> Optional[bytes]:
        asset = self.get(content_hash)
        if asset and asset.local_path:
            p = Path(asset.local_path)
            if p.exists():
                return p.read_bytes()
        # Scan shard directory as fallback
        shard = self._vault_dir / content_hash[:2]
        if shard.exists():
            for f in shard.iterdir():
                if f.stem == content_hash:
                    return f.read_bytes()
        return None

    def exists(self, content_hash: str) -> bool:
        return self._index_path(content_hash).exists()

    # ── Query ──────────────────────────────────────────────────────────────────

    def all(self) -> List[MediaAsset]:
        assets = []
        for f in self._index_dir.iterdir():
            if f.suffix == ".json":
                try:
                    assets.append(MediaAsset.from_dict(json.loads(f.read_text(encoding="utf-8"))))
                except Exception:
                    pass
        return assets

    def by_collection(self, collection: str) -> List[MediaAsset]:
        return [a for a in self.all() if collection in a.collections]

    def by_tag(self, tag: str) -> List[MediaAsset]:
        return [a for a in self.all() if tag in a.tags]

    def by_source(self, source: str) -> List[MediaAsset]:
        return [a for a in self.all() if a.source == source]

    def by_type(self, media_type: str) -> List[MediaAsset]:
        return [a for a in self.all() if a.media_type == media_type]

    def search(
        self,
        query: str = "",
        source: Optional[str] = None,
        media_type: Optional[str] = None,
        collection: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[MediaAsset]:
        results = self.all()
        if source:
            results = [a for a in results if a.source == source]
        if media_type:
            results = [a for a in results if a.media_type == media_type]
        if collection:
            results = [a for a in results if collection in a.collections]
        if tag:
            results = [a for a in results if tag in a.tags]
        if query:
            q       = query.lower()
            results = [
                a for a in results
                if q in a.title.lower()
                or q in a.author.lower()
                or any(q in t.lower() for t in a.tags)
            ]
        return results

    def delete(self, content_hash: str) -> bool:
        asset = self.get(content_hash)
        if asset is None:
            return False
        if asset.local_path:
            p = Path(asset.local_path)
            if p.exists():
                p.unlink()
        self._index_path(content_hash).unlink(missing_ok=True)
        return True

    def stats(self) -> Dict[str, Any]:
        assets     = self.all()
        by_type:   Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        for a in assets:
            by_type[a.media_type] = by_type.get(a.media_type, 0) + 1
            by_source[a.source]   = by_source.get(a.source, 0) + 1
        return {"total": len(assets), "by_type": by_type, "by_source": by_source}

    # ── Internal ───────────────────────────────────────────────────────────────

    def _index_path(self, content_hash: str) -> Path:
        return self._index_dir / f"{content_hash}.json"

    def _file_path(self, content_hash: str, ext: str) -> Path:
        return self._vault_dir / content_hash[:2] / f"{content_hash}{ext}"

    def _ext_for(self, asset: MediaAsset) -> str:
        _TYPE_EXT: Dict[str, str] = {
            MediaType.IMAGE:    ".png",
            MediaType.VIDEO:    ".mp4",
            MediaType.AUDIO:    ".mp3",
            MediaType.GIF:      ".gif",
            MediaType.DOCUMENT: ".bin",
        }
        if asset.local_path:
            sfx = Path(asset.local_path).suffix
            if sfx:
                return sfx
        return _TYPE_EXT.get(asset.media_type, ".bin")

    def _save_index(self, asset: MediaAsset) -> None:
        p   = self._index_path(asset.content_hash)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(asset.to_json(), encoding="utf-8")
        tmp.replace(p)  # replace() is atomic on POSIX and handles existing target on Windows
