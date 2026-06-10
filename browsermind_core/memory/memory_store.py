"""
MemoryStore — P4: Persistent JSONL storage for all memory types.

Storage layout:
  ~/.browsermind/memory/
    <env_key>/
      episodes.jsonl      — append-only episode log
      procedural.json     — aggregated ProceduralRecord per (intent_family, cap_hint, action)
      semantic.json       — aggregated SemanticFact per (concept)
    capabilities/
      <hash16>.json       — CapabilityRecord (cross-environment, keyed by invariant_hash)

Design:
  - Episodes: append-only JSONL. Never modified. Audit log.
  - Procedural: JSON dict keyed by record ID. Updated in-place on each run.
  - Semantic: JSON dict keyed by concept. Updated in-place on confidence changes.
  - Capabilities: one JSON file per invariant_hash (cross-environment). Updated in-place.
  - All writes are atomic (write to temp file, rename).
  - Thread safety: single-process assumption for P4. Lock added post-P5 if needed.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from browsermind_core.memory.episode import EpisodeRecord
from browsermind_core.memory.procedural import ProceduralRecord
from browsermind_core.memory.semantic import SemanticFact


def _default_memory_root(persona_id: str = "default") -> Path:
    return Path.home() / ".browsermind" / "memory" / persona_id


class MemoryStore:
    """
    JSONL/JSON persistence layer for the three memory types.
    One instance per session; env dirs are created lazily.
    """

    def __init__(self, root: Optional[Path] = None, persona_id: str = "default"):
        self.persona_id = persona_id
        self.root = root or _default_memory_root(persona_id)

    def _env_dir(self, env_key: str) -> Path:
        d = self.root / env_key
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Episodes — append-only
    # ------------------------------------------------------------------

    def append_episode(self, record: EpisodeRecord) -> None:
        path = self._env_dir(record.environment_key) / "episodes.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(record.to_json_line() + "\n")

    def read_episodes(self, env_key: str) -> List[EpisodeRecord]:
        path = self._env_dir(env_key) / "episodes.jsonl"
        if not path.exists():
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(EpisodeRecord.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return records

    # ------------------------------------------------------------------
    # Procedural — aggregated dict, atomic write
    # ------------------------------------------------------------------

    def _procedural_path(self, env_key: str) -> Path:
        return self._env_dir(env_key) / "procedural.json"

    def _procedural_key(self, r: ProceduralRecord) -> str:
        return f"{r.intent_family}|{r.capability_hint}|{r.step_action}"

    def load_procedural(self, env_key: str) -> Dict[str, ProceduralRecord]:
        path = self._procedural_path(env_key)
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        result = {}
        for k, v in raw.items():
            try:
                result[k] = ProceduralRecord.from_dict(v)
            except Exception:
                pass
        return result

    def save_procedural(self, env_key: str, records: Dict[str, ProceduralRecord]) -> None:
        path = self._procedural_path(env_key)
        data = {k: json.loads(v.to_json_line()) for k, v in records.items()}
        _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))

    def update_procedural(self, record: ProceduralRecord) -> None:
        """Load, merge, save — called after each step outcome."""
        env_key = record.environment_key
        records = self.load_procedural(env_key)
        key = self._procedural_key(record)
        if key in records:
            existing = records[key]
            # Merge strategy_counts
            for strategy, counts in record.strategy_counts.items():
                if strategy not in existing.strategy_counts:
                    existing.strategy_counts[strategy] = {"success": 0, "failure": 0}
                existing.strategy_counts[strategy]["success"] += counts.get("success", 0)
                existing.strategy_counts[strategy]["failure"] += counts.get("failure", 0)
            # Merge known_boundaries using CapabilityBoundary.merge_boundaries
            if record.known_boundaries:
                try:
                    from browsermind_core.learning.capability_boundary import (
                        CapabilityBoundary,
                        merge_boundaries,
                    )
                    new_boundaries = [
                        CapabilityBoundary(
                            capability_hint=b.get("capability_hint", ""),
                            failure_mode=b.get("failure_mode", ""),
                            failure_reason=b.get("failure_reason", ""),
                            environment_pattern=b.get("environment_pattern", ""),
                            frequency=b.get("frequency", 1),
                            evidence_count=b.get("evidence_count", 1),
                            first_seen_env=b.get("first_seen_env", ""),
                        )
                        for b in record.known_boundaries
                    ]
                    existing.known_boundaries = merge_boundaries(
                        existing.known_boundaries, new_boundaries
                    )
                except Exception:
                    pass
            existing.last_seen = record.last_seen
        else:
            records[key] = record
        self.save_procedural(env_key, records)

    def get_procedural(
        self,
        env_key: str,
        intent_family: str,
        capability_hint: str,
        step_action: str,
    ) -> Optional[ProceduralRecord]:
        """Lookup by (intent_family, capability_hint, step_action) for given env."""
        records = self.load_procedural(env_key)
        key = f"{intent_family}|{capability_hint}|{step_action}"
        return records.get(key)

    # ------------------------------------------------------------------
    # Semantic — aggregated dict, atomic write
    # ------------------------------------------------------------------

    def _semantic_path(self, env_key: str) -> Path:
        return self._env_dir(env_key) / "semantic.json"

    def load_semantic(self, env_key: str) -> Dict[str, SemanticFact]:
        path = self._semantic_path(env_key)
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        result = {}
        for k, v in raw.items():
            try:
                result[k] = SemanticFact.from_dict(v)
            except Exception:
                pass
        return result

    def save_semantic(self, env_key: str, facts: Dict[str, SemanticFact]) -> None:
        path = self._semantic_path(env_key)
        data = {k: json.loads(v.to_json_line()) for k, v in facts.items()}
        _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))

    def update_semantic(self, fact: SemanticFact) -> None:
        """Load, reinforce or insert, save."""
        env_key = fact.environment_key
        facts = self.load_semantic(env_key)
        if fact.concept in facts:
            facts[fact.concept].reinforce(fact.value, fact.evidence)
        else:
            facts[fact.concept] = fact
        self.save_semantic(env_key, facts)

    def get_semantic(self, env_key: str, concept: str) -> Optional[SemanticFact]:
        facts = self.load_semantic(env_key)
        return facts.get(concept)

    def get_all_semantic(self, env_key: str) -> Dict[str, SemanticFact]:
        return self.load_semantic(env_key)

    # ------------------------------------------------------------------
    # Capabilities — cross-environment, keyed by invariant_hash
    # One JSON file per hash: capabilities/<hash16>.json
    # ------------------------------------------------------------------

    def _capabilities_dir(self) -> Path:
        d = self.root / "capabilities"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _capability_path(self, invariant_hash: str) -> Path:
        return self._capabilities_dir() / f"{invariant_hash}.json"

    def update_capability(self, record) -> None:
        """Load existing CapabilityRecord for this hash, merge, save.

        Merges:
          transfer_envs    — union
          known_boundaries — via merge_boundaries
          strategy_counts  — incremental sum
          contract_verified_ratio — overwrite with latest
          promotion_tier   — take the higher tier
          source_templates — union
        """
        from browsermind_core.learning.capability_record import CapabilityRecord

        path = self._capability_path(record.invariant_hash)
        existing: Optional[CapabilityRecord] = None
        if path.exists():
            try:
                existing = CapabilityRecord.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except Exception:
                existing = None

        if existing is None:
            _atomic_write(path, record.to_json())
            return

        # Merge transfer_envs
        for env in record.transfer_envs:
            if env and env not in existing.transfer_envs:
                existing.transfer_envs.append(env)

        # Merge strategy_counts
        for strategy, counts in record.strategy_counts.items():
            if strategy not in existing.strategy_counts:
                existing.strategy_counts[strategy] = {"success": 0, "failure": 0}
            existing.strategy_counts[strategy]["success"] += counts.get("success", 0)
            existing.strategy_counts[strategy]["failure"] += counts.get("failure", 0)

        # Merge known_boundaries
        if record.known_boundaries:
            try:
                from browsermind_core.learning.capability_boundary import (
                    CapabilityBoundary,
                    merge_boundaries,
                )
                new_boundaries = [
                    CapabilityBoundary(
                        capability_hint=b.get("capability_hint", ""),
                        failure_mode=b.get("failure_mode", ""),
                        failure_reason=b.get("failure_reason", ""),
                        environment_pattern=b.get("environment_pattern", ""),
                        frequency=b.get("frequency", 1),
                        evidence_count=b.get("evidence_count", 1),
                        first_seen_env=b.get("first_seen_env", ""),
                    )
                    for b in record.known_boundaries
                ]
                existing.known_boundaries = merge_boundaries(
                    existing.known_boundaries, new_boundaries
                )
            except Exception:
                pass

        # Merge source_templates
        for tmpl in record.source_templates:
            if tmpl and tmpl not in existing.source_templates:
                existing.source_templates.append(tmpl)

        # Update scalar fields: take latest non-None, higher tier
        if record.contract_verified_ratio is not None:
            existing.contract_verified_ratio = record.contract_verified_ratio
        if record.human_name and not existing.human_name:
            existing.human_name = record.human_name

        _TIER_ORDER = ["CANDIDATE", "STRONG", "VALIDATED", "DEPRECATED"]
        def _tier_rank(t: str) -> int:
            try:
                return _TIER_ORDER.index(t)
            except ValueError:
                return 0

        if _tier_rank(record.promotion_tier) > _tier_rank(existing.promotion_tier):
            existing.promotion_tier = record.promotion_tier

        existing.last_seen = record.last_seen
        _atomic_write(path, existing.to_json())

    def get_capability_by_hash(self, invariant_hash: str):
        """Return CapabilityRecord for this hash, or None if not found."""
        from browsermind_core.learning.capability_record import CapabilityRecord

        path = self._capability_path(invariant_hash)
        if not path.exists():
            return None
        try:
            return CapabilityRecord.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except Exception:
            return None

    def load_capabilities(self):
        """Return dict of {invariant_hash: CapabilityRecord} for all stored capabilities."""
        from browsermind_core.learning.capability_record import CapabilityRecord

        result = {}
        cap_dir = self._capabilities_dir()
        for json_path in cap_dir.glob("*.json"):
            try:
                record = CapabilityRecord.from_dict(
                    json.loads(json_path.read_text(encoding="utf-8"))
                )
                result[record.invariant_hash] = record
            except Exception:
                pass
        return result


# ------------------------------------------------------------------
# Atomic write helper
# ------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically: write to temp, then rename."""
    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
