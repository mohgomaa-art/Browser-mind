"""MediaCollection + CollectionManager — organize assets into named groups.

Collections live in <root>/collections/<safe_name>.json.
Auto-tag rules let collections self-populate: any asset whose title or tags
contain a rule string is automatically added to that collection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from browsermind_core.media.media_asset import MediaAsset


@dataclass
class MediaCollection:
    """A named, persistent group of MediaAsset content_hashes.

    auto_tag_rules  — list of strings; if any appears in asset.title or
                      asset.tags, the asset is automatically assigned here.
    """
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    auto_tag_rules: List[str] = field(default_factory=list)
    asset_hashes: List[str] = field(default_factory=list)
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":           self.name,
            "description":    self.description,
            "tags":           list(self.tags),
            "auto_tag_rules": list(self.auto_tag_rules),
            "asset_hashes":   list(self.asset_hashes),
            "created_at":     self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MediaCollection":
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            tags=list(d.get("tags", [])),
            auto_tag_rules=list(d.get("auto_tag_rules", [])),
            asset_hashes=list(d.get("asset_hashes", [])),
            created_at=d.get("created_at"),
        )


_DEFAULT_COLLECTIONS_ROOT = Path.home() / ".browsermind" / "media" / "collections"


class CollectionManager:
    """Create, query, and maintain MediaCollections on disk.

    Usage
    ─────
      mgr = CollectionManager(root=tmp_path)
      col = mgr.create("4K Wallpapers", auto_tag_rules=["wallpaper", "4k"])
      mgr.add_asset("4K Wallpapers", asset.content_hash)
      matched = mgr.apply_auto_classify(asset)
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root is not None else _DEFAULT_COLLECTIONS_ROOT
        self._root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        name: str,
        description: str = "",
        auto_tag_rules: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> MediaCollection:
        col = MediaCollection(
            name=name,
            description=description,
            auto_tag_rules=list(auto_tag_rules or []),
            tags=list(tags or []),
            created_at=datetime.utcnow().isoformat(),
        )
        self._save(col)
        return col

    def get(self, name: str) -> Optional[MediaCollection]:
        p = self._path(name)
        if not p.exists():
            return None
        try:
            return MediaCollection.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def all(self) -> List[MediaCollection]:
        cols = []
        for f in self._root.iterdir():
            if f.suffix == ".json":
                try:
                    cols.append(
                        MediaCollection.from_dict(json.loads(f.read_text(encoding="utf-8")))
                    )
                except Exception:
                    pass
        return cols

    def add_asset(self, collection_name: str, content_hash: str) -> bool:
        col = self.get(collection_name)
        if col is None:
            return False
        if content_hash not in col.asset_hashes:
            col.asset_hashes.append(content_hash)
            self._save(col)
        return True

    def remove_asset(self, collection_name: str, content_hash: str) -> bool:
        col = self.get(collection_name)
        if col is None:
            return False
        if content_hash in col.asset_hashes:
            col.asset_hashes.remove(content_hash)
            self._save(col)
            return True
        return False

    def auto_classify(self, asset: MediaAsset) -> List[str]:
        """Return collection names this asset should belong to (by auto_tag_rules)."""
        matches = []
        title_lower = asset.title.lower()
        for col in self.all():
            for rule in col.auto_tag_rules:
                rule_lower = rule.lower()
                if rule_lower in title_lower or rule_lower in [t.lower() for t in asset.tags]:
                    matches.append(col.name)
                    break
        return matches

    def apply_auto_classify(self, asset: MediaAsset) -> List[str]:
        """Auto-classify and update asset.collections in place."""
        matched = self.auto_classify(asset)
        for name in matched:
            if name not in asset.collections:
                asset.collections.append(name)
            self.add_asset(name, asset.content_hash)
        return matched

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False

    def _path(self, name: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in ("_", "-", " ")) else "_" for c in name)
        safe = safe.replace(" ", "_")
        return self._root / f"{safe}.json"

    def _save(self, col: MediaCollection) -> None:
        p   = self._path(col.name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(col.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)  # replace() handles existing target on Windows
