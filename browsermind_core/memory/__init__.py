"""
BrowserMind Memory Runtime — P4

Three narrow, observable layers:
  episode.py      — What happened in a specific step (write-only audit log)
  procedural.py   — Strategy priors per (intent_family, capability_hint) — NOT overrides
  semantic.py     — Structured environment facts (concept/value, NOT free text)
  memory_store.py — JSONL persistence, environment-global (no Persona scoping yet)
  memory_writer.py — Writes after each step/replay (called from replay_engine, harness)
  memory_reader.py — Reads strategy priors for Resolver ranking (NOT override)

Design invariants (P4):
  - Observable: every write is a JSONL line, human-readable
  - Deterministic: same inputs produce same priors
  - Queryable: lookup by (env_key, intent_family, capability_hint)
  - Auditable: nothing is deleted or overwritten, only appended
  - NOT a Cache: Procedural memory boosts Resolver ranking, does not skip steps
  - NOT Persona-scoped: environment-global until P5

TODO (P5): Add Persona scoping for Preferences, Assets, Trust Policies.
"""
from browsermind_core.memory.episode import EpisodeRecord
from browsermind_core.memory.procedural import ProceduralRecord
from browsermind_core.memory.semantic import SemanticFact
from browsermind_core.memory.memory_store import MemoryStore
from browsermind_core.memory.memory_writer import MemoryWriter
from browsermind_core.memory.memory_reader import MemoryReader

__all__ = [
    "EpisodeRecord",
    "ProceduralRecord",
    "SemanticFact",
    "MemoryStore",
    "MemoryWriter",
    "MemoryReader",
]
