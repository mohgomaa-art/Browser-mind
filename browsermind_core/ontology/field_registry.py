"""FieldRegistry — single source of truth for semantic Field identity.

Lookup discipline (DOCS/FIELD_ONTOLOGY_SPEC.md §3):
    1. Normalize: strip, lowercase, drop trailing "*" / ":" / "(optional)".
    2. Exact match against the alias index (canonical + every alias).
    3. Fuzzy match (Levenshtein <= 2) only on labels >= 6 chars; abstain on tie.

Storage:
    Seed corpus ships at ``browsermind_core/data/field_registry.json`` and
    is loaded when the user has no registry yet. Once any write happens
    (``register`` or ``add_alias``), the registry is mirrored to
    ``~/.browsermind/field_registry.json`` and that becomes the read path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from browsermind_core.ontology.field_ontology import Field


_SEED_PATH = Path(__file__).parent.parent / "data" / "field_registry.json"
_USER_PATH = Path.home() / ".browsermind" / "field_registry.json"

_TRAILING_DECORATION = re.compile(r"[\*:]+$")
_OPTIONAL_SUFFIX = re.compile(r"\s*\(optional\)\s*$", re.IGNORECASE)


def _normalize(label: str) -> str:
    s = (label or "").strip()
    s = _OPTIONAL_SUFFIX.sub("", s).strip()
    s = _TRAILING_DECORATION.sub("", s).strip()
    return s.lower()


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


class FieldRegistry:
    def __init__(self, registry_path: Optional[Path] = None):
        self._path: Path = Path(registry_path) if registry_path else _USER_PATH
        self._fields: Dict[str, Field] = {}
        self._alias_index: Dict[str, str] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve(self, label: Optional[str]) -> Optional[Field]:
        """Return the Field matching ``label``, or None if unknown / ambiguous."""
        if not label or not label.strip():
            return None
        key = _normalize(label)

        hit = self._alias_index.get(key)
        if hit:
            return self._fields.get(hit)

        if len(key) >= 6:
            best_dist = 3
            best_id: Optional[str] = None
            ambiguous = False
            for alias_key, field_id in self._alias_index.items():
                d = _levenshtein(key, alias_key)
                if d < best_dist:
                    best_dist = d
                    best_id = field_id
                    ambiguous = False
                elif d == best_dist and field_id != best_id:
                    ambiguous = True
            if best_id and not ambiguous and best_dist <= 2:
                return self._fields.get(best_id)

        return None

    def get(self, field_id: str) -> Optional[Field]:
        return self._fields.get(field_id)

    def list_fields(self) -> List[Field]:
        return sorted(self._fields.values(), key=lambda f: f.id)

    def register(self, field: Field) -> None:
        """Add or replace a Field. Validates alias uniqueness across all fields."""
        for label in field.all_labels():
            key = _normalize(label)
            owner = self._alias_index.get(key)
            if owner and owner != field.id:
                raise ValueError(
                    f"Alias '{label}' already belongs to field '{owner}'. "
                    f"Aliases must be globally unique; cannot also assign to '{field.id}'."
                )
        if field.id in self._fields:
            for label in self._fields[field.id].all_labels():
                self._alias_index.pop(_normalize(label), None)
        self._fields[field.id] = field
        for label in field.all_labels():
            self._alias_index[_normalize(label)] = field.id
        self._save()

    def add_alias(self, field_id: str, alias: str) -> Field:
        if not alias or not alias.strip():
            raise ValueError("alias must be non-empty")
        field = self._fields.get(field_id)
        if field is None:
            raise KeyError(f"Field '{field_id}' not found in registry.")
        key = _normalize(alias)
        owner = self._alias_index.get(key)
        if owner and owner != field_id:
            raise ValueError(f"Alias '{alias}' already belongs to '{owner}'.")
        if key in {_normalize(a) for a in field.all_labels()}:
            return field
        updated = field.model_copy(update={"aliases": list(field.aliases) + [alias]})
        self.register(updated)
        return updated

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        path = self._path if self._path.exists() else _SEED_PATH
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [FieldRegistry] failed to load {path}: {exc}")
            return
        for raw in data.get("fields", []):
            try:
                f = Field.model_validate(raw)
            except Exception as exc:
                print(f"  [FieldRegistry] skipping invalid field {raw.get('id')!r}: {exc}")
                continue
            self._fields[f.id] = f
            for label in f.all_labels():
                self._alias_index[_normalize(label)] = f.id

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1",
            "fields": [f.model_dump(mode="json") for f in self.list_fields()],
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)


_singleton: Optional[FieldRegistry] = None


def get_registry() -> FieldRegistry:
    global _singleton
    if _singleton is None:
        _singleton = FieldRegistry()
    return _singleton


def _reset_registry_for_tests() -> None:
    """Drop the module-level singleton so tests can use isolated registry paths."""
    global _singleton
    _singleton = None
