"""RecoveryRegistry — Phase 8 of R6 v1 (the keystone).

Loads the data-driven recovery ladder from `recovery_ladder.json`. On first
load, the file is seeded with the existing R1-R5 strategies + capability_intent
so behavior matches the previously-hardcoded ladder bit-for-bit. After that,
new strategies (R6, R7, ...) added by `bm recovery candidate approve` simply
append rows; no source-code change is required.

Each ladder row is a `RecoveryStrategy` with:
    name        — short label (e.g. "container_proximity", "mined:abcd1234")
    predicate   — dict[str, Any] of feature-flag requirements; matched
                  against descriptor_features.features() at resolve-time
    primitive   — key in PRIMITIVE_LIBRARY
    depth       — depth label preserved on ResolutionResult for parity
                  with the old hardcoded recovered_by ladder
    source      — "builtin" (R1-R5) or "mined" (added via candidate approval)
    quarantined — when True the registry hides the row at ladder() time

The seed ladder reproduces target_resolver.py:535-633 exactly:
    R1 container_proximity (no predicate gate; container helper does its own)
    R2 placeholder
    R3 accessible_name (text)
    R4 nearby_text     (text)
    R5 structural_path
    R5b capability_intent
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RecoveryStrategySource = Literal["builtin", "mined"]


class RecoveryStrategy(BaseModel):
    name: str
    predicate: Dict[str, Any] = Field(default_factory=dict)
    primitive: str
    depth: int = 1
    source: RecoveryStrategySource = "builtin"
    quarantined: bool = False
    candidate_id: Optional[str] = None  # back-pointer for mined rows
    committed_at: Optional[str] = None


# Seed ladder — mirrors target_resolver.py:628-725 exactly. Order matters.
# Each builtin row carries a `primitive` whose semantics are encoded directly
# in the resolver's _dispatch_strategy method to preserve the exact original
# labels (exact_selector / loose_semantic / nearby_text / structural_path /
# affordance / capability_intent) and depth values.
_SEED_LADDER: List[Dict[str, Any]] = [
    {
        "name": "container_proximity",
        "predicate": {},
        "primitive": "container_proximity",
        "depth": 1,
        "source": "builtin",
    },
    {
        "name": "placeholder",
        "predicate": {"has_placeholder": True},
        "primitive": "by_placeholder",
        "depth": 1,
        "source": "builtin",
    },
    {
        "name": "accessible_name",
        "predicate": {"has_accessible_name": True},
        "primitive": "by_text_accessible",
        "depth": 2,
        "source": "builtin",
    },
    {
        "name": "nearby_text",
        "predicate": {"has_text_content": True},
        "primitive": "by_text_content",
        "depth": 2,
        "source": "builtin",
    },
    {
        "name": "structural_path",
        "predicate": {"has_dom_path": True},
        "primitive": "structural_with_ambiguity",
        "depth": 3,
        "source": "builtin",
    },
    {
        "name": "affordance_intent",
        "predicate": {},
        "primitive": "affordance_intent",
        "depth": 4,
        "source": "builtin",
    },
    {
        "name": "capability_intent",
        "predicate": {"has_capability_hint": True},
        "primitive": "by_capability",
        "depth": 4,
        "source": "builtin",
    },
]


class RecoveryRegistry:
    """Persistent, append-friendly recovery ladder.

    Constructor seeds `recovery_ladder.json` with R1-R5 + capability_intent
    on first run. Subsequent calls just load the file. Approved candidates
    are added via `append(strategy)`; rolled back via `pop_by_candidate(id)`.
    """

    FILE_NAME = "recovery_ladder.json"
    SCHEMA_VERSION = "browsermind.recovery_ladder.v1"

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self.path = Path(store_dir) / self.FILE_NAME
        if not self.path.exists():
            self._write({"schema_version": self.SCHEMA_VERSION,
                         "strategies": list(_SEED_LADDER)})

    # --- I/O ---------------------------------------------------------------

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": self.SCHEMA_VERSION, "strategies": list(_SEED_LADDER)}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"schema_version": self.SCHEMA_VERSION, "strategies": list(_SEED_LADDER)}

    def _write(self, data: Dict[str, Any]) -> None:
        """Atomic JSON write — temp file in the same dir, then os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ladder_", suffix=".json",
                                   dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

    # --- Public API --------------------------------------------------------

    def ladder(self, *, include_quarantined: bool = False) -> List[RecoveryStrategy]:
        data = self._read()
        out: List[RecoveryStrategy] = []
        for raw in data.get("strategies", []):
            try:
                strat = RecoveryStrategy.model_validate(raw)
            except Exception:
                continue
            if strat.quarantined and not include_quarantined:
                continue
            out.append(strat)
        return out

    def snapshot(self) -> Dict[str, Any]:
        """Full file content — used as `previous_state` for rollback."""
        return self._read()

    def append(self, strategy: RecoveryStrategy) -> None:
        data = self._read()
        strategy.committed_at = datetime.now(timezone.utc).isoformat()
        data.setdefault("strategies", []).append(
            strategy.model_dump(mode="json")
        )
        self._write(data)

    def replace(self, snapshot: Dict[str, Any]) -> None:
        """Restore ladder from a full snapshot. Used for rollback."""
        data = dict(snapshot)
        data.setdefault("schema_version", self.SCHEMA_VERSION)
        data.setdefault("strategies", list(_SEED_LADDER))
        self._write(data)

    def quarantine(self, candidate_id: str) -> bool:
        """Mark a mined row as quarantined. Returns True on hit."""
        data = self._read()
        changed = False
        for raw in data.get("strategies", []):
            if raw.get("candidate_id") == candidate_id and not raw.get("quarantined"):
                raw["quarantined"] = True
                changed = True
        if changed:
            self._write(data)
        return changed

    def find_by_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        for raw in self._read().get("strategies", []):
            if raw.get("candidate_id") == candidate_id:
                return raw
        return None


# --- Predicate matcher -----------------------------------------------------


def predicate_matches(
    predicate: Dict[str, Any],
    feature_vector: Dict[str, Any],
) -> bool:
    """Return True when every key in `predicate` is satisfied by the
    feature_vector. Booleans are compared by equality; floats compare by
    >= when the predicate value is numeric.

    An empty predicate matches everything (used by container_proximity,
    which gates inside the helper rather than via a predicate flag)."""
    if not predicate:
        return True
    for key, expected in predicate.items():
        actual = feature_vector.get(key)
        if isinstance(expected, bool):
            if bool(actual) != expected:
                return False
        elif isinstance(expected, (int, float)):
            try:
                if float(actual or 0) < float(expected):
                    return False
            except Exception:
                return False
        else:
            if actual != expected:
                return False
    return True
