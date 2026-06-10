"""FallbackLedger — persistent log of unrecognised UI interactions.

Records every PrimitiveNormalizer fallback so VocabInductor can cluster
them into candidate vocabulary expansions.

Usage:
    ledger = FallbackLedger()
    norm = PrimitiveNormalizer(logger=ledger.as_logger(site_key="github"))
    # ... run exploration ...
    entries = ledger.all()   # Dict[fragment, FallbackEntry]
    stats  = ledger.stats()

Storage: single atomic JSON file, default ~/.browsermind/fallback_ledger.json
Key: normalized name_fragment. Append-friendly: each record() call re-saves.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ── Utilities ─────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_name_fragment(raw_token: str) -> str:
    """Extract the human-readable name fragment from a fallback token.

    Fallback tokens have the format  ACTION_ROLE_name_words  where ACTION and
    ROLE are ALL-CAPS and the name part is lowercase.  We strip the first two
    uppercase-only segments and return the remainder as a space-separated string.

    Examples:
        CLICK_BUTTON_add_to_wishlist  →  add to wishlist
        FILL_TEXTBOX_newsletter_email →  newsletter email
        HOVER_DIV_tooltip_content     →  tooltip content
    """
    parts = raw_token.split("_")
    start = 0
    for i, p in enumerate(parts):
        if p == p.upper() and p.isalpha():
            start = i + 1
        else:
            break
    fragment = " ".join(parts[start:]).lower().strip()
    # Drop trailing ellipsis from truncated names
    fragment = fragment.rstrip(" .")
    fragment = re.sub(r"\s+", " ", fragment)
    return fragment or raw_token.lower()


# ── FallbackEntry ─────────────────────────────────────────────────────────────

class FallbackEntry:
    """One unique name_fragment and all evidence about it across sites."""

    __slots__ = (
        "name_fragment", "raw_tokens", "sites",
        "examples", "frequency", "first_seen", "last_seen",
    )

    def __init__(self, name_fragment: str) -> None:
        self.name_fragment: str = name_fragment
        self.raw_tokens:    List[str] = []
        self.sites:         List[str] = []
        self.examples:      List[Dict[str, Any]] = []
        self.frequency:     int = 0
        self.first_seen:    str = _utc_now()
        self.last_seen:     str = _utc_now()

    def record(
        self,
        raw_token: str,
        site_key: str,
        action_type: str,
        role: str,
        name: str,
    ) -> None:
        self.frequency += 1
        self.last_seen = _utc_now()
        if raw_token not in self.raw_tokens:
            self.raw_tokens.append(raw_token)
        if site_key and site_key not in self.sites:
            self.sites.append(site_key)
        self.examples.append({
            "site": site_key,
            "action_type": action_type,
            "role": role,
            "name": name,
        })
        if len(self.examples) > 12:
            self.examples = self.examples[-12:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name_fragment": self.name_fragment,
            "raw_tokens":    self.raw_tokens,
            "sites":         self.sites,
            "examples":      self.examples,
            "frequency":     self.frequency,
            "first_seen":    self.first_seen,
            "last_seen":     self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FallbackEntry":
        e = cls(d["name_fragment"])
        e.raw_tokens = list(d.get("raw_tokens", []))
        e.sites      = list(d.get("sites", []))
        e.examples   = list(d.get("examples", []))
        e.frequency  = int(d.get("frequency", 0))
        e.first_seen = d.get("first_seen", "")
        e.last_seen  = d.get("last_seen", "")
        return e


# ── FallbackLedger ────────────────────────────────────────────────────────────

class FallbackLedger:
    """Persistent ledger of unrecognised UI interactions.

    Thread-safety: single-process assumption (same as MemoryStore / HypothesisStore).
    """

    DEFAULT_PATH = Path.home() / ".browsermind" / "fallback_ledger.json"

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else self.DEFAULT_PATH
        self._cache: Optional[Dict[str, FallbackEntry]] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def record(
        self,
        action_type: str,
        role: str,
        name: str,
        site_key: str = "",
        raw_token: str = "",
    ) -> FallbackEntry:
        """Record one fallback observation. Returns the updated entry."""
        entries = self._load()
        token = raw_token or f"{action_type.upper()}_{role.upper()}_{name}"
        fragment = extract_name_fragment(token)

        if fragment not in entries:
            entries[fragment] = FallbackEntry(fragment)

        entries[fragment].record(
            raw_token=token,
            site_key=site_key,
            action_type=action_type,
            role=role,
            name=name,
        )
        self._cache = entries
        self._save(entries)
        return entries[fragment]

    def as_logger(self, site_key: str = "") -> Callable[[Dict[str, Any]], None]:
        """Return a PrimitiveNormalizer-compatible logger that records fallbacks.

        Wire it like:
            norm = PrimitiveNormalizer(logger=ledger.as_logger(site_key="github"))
        Only fallback records (is_fallback=True) are written; known-vocab records
        are ignored so the ledger stays focused on coverage gaps.
        """
        def _log(rec: Dict[str, Any]) -> None:
            if rec.get("is_fallback"):
                self.record(
                    action_type=rec.get("action_type", ""),
                    role=rec.get("target_role", ""),
                    name=rec.get("target_name", ""),
                    site_key=site_key,
                    raw_token=rec.get("result", ""),
                )
        return _log

    def all(self) -> Dict[str, FallbackEntry]:
        """Return all entries, keyed by name_fragment."""
        return self._load()

    def stats(self) -> Dict[str, Any]:
        entries = self._load()
        total_obs   = sum(e.frequency for e in entries.values())
        multi_site  = sum(1 for e in entries.values() if len(e.sites) >= 2)
        top = sorted(entries.values(), key=lambda e: -e.frequency)[:5]
        return {
            "unique_fragments":    len(entries),
            "total_observations":  total_obs,
            "multi_site_fragments": multi_site,
            "top_fragments": [
                {"fragment": e.name_fragment, "freq": e.frequency, "sites": len(e.sites)}
                for e in top
            ],
        }

    def clear(self) -> None:
        """Wipe the ledger. Use in tests only."""
        self._cache = {}
        self._save({})

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, FallbackEntry]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = {k: FallbackEntry.from_dict(v) for k, v in raw.items()}
        except Exception:
            self._cache = {}
        return self._cache

    def _save(self, entries: Dict[str, FallbackEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw = {k: v.to_dict() for k, v in entries.items()}
        content = json.dumps(raw, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
