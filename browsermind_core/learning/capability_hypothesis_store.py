"""CapabilityHypothesisStore — persistent landing zone for unknown capability patterns.

Every unknown InvariantGraph pattern that is not yet a CapabilityRecord lands here
as a CapabilityHypothesis. The store accumulates evidence across explorations,
advances hypotheses through their lifecycle, and exports ready-to-promote
candidates back to ExplorationHarness and _compile_and_promote().

Storage layout
──────────────
  ~/.browsermind/memory/<persona_id>/hypotheses/<hash16>.json

One JSON file per invariant_hash. Cross-environment (like capabilities/).
Writes are atomic.

Self-directed exploration loop
───────────────────────────────
  query(status=[RECURRING, EMERGING])
      → returns hypotheses worth revisiting
      → ExplorationHarness feeds them back as capability_targets
      → observe() accumulates more evidence
      → _try_graduate() auto-advances status
      → promote() / refute() closes the loop

API
───
  observe(invariants, env_key, ...)         Record one new observation. Creates or merges.
  merge(hypothesis)                         Merge an externally-built hypothesis.
  promote(invariant_hash, capability_id)    Mark as PROMOTED; optionally write CapabilityRecord.
  refute(invariant_hash, reason)            Mark as REFUTED.
  query(status, source, site_category, ...)  Filter hypotheses.
  get(invariant_hash)                        Load one hypothesis by hash.
  all()                                      Load all hypotheses.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from browsermind_core.learning.capability_hypothesis import (
    CapabilityHypothesis,
    HypothesisStatus,
    make_hypothesis,
)


def _default_root(persona_id: str = "default") -> Path:
    return Path.home() / ".browsermind" / "memory" / persona_id


class CapabilityHypothesisStore:
    """Persistent store for CapabilityHypothesis objects.

    One instance per session. Lazy directory creation. Atomic file writes.
    Not thread-safe (single-process assumption, same as MemoryStore).
    """

    def __init__(self, root: Optional[Path] = None, persona_id: str = "default"):
        self.persona_id = persona_id
        self.root = root or _default_root(persona_id)

    # ── Storage helpers ───────────────────────────────────────────────────────

    def _hypotheses_dir(self) -> Path:
        d = self.root / "hypotheses"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _hypothesis_path(self, invariant_hash: str) -> Path:
        return self._hypotheses_dir() / f"{invariant_hash}.json"

    # ── Core API ──────────────────────────────────────────────────────────────

    def observe(
        self,
        invariants: List[str],
        env_key: str = "",
        source: str = "exploration",
        context_hint: str = "",
        outcome: str = "",
        site_category: Optional[str] = None,
    ) -> CapabilityHypothesis:
        """Record one observation of an unknown pattern.

        If a hypothesis for this invariant_hash already exists, merge the
        observation into it (frequency++, evidence appended, lifecycle advanced).
        If it's new, create one and persist it.

        Returns the updated or newly created CapabilityHypothesis.
        """
        from browsermind_core.learning.capability_hypothesis import make_hypothesis
        # Compute hash without creating the full object first
        import hashlib
        canonical = "|".join(sorted(invariants))
        inv_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

        existing = self.get(inv_hash)
        if existing is None:
            hyp = make_hypothesis(
                invariants=invariants,
                env_key=env_key,
                source=source,
                context_hint=context_hint,
                outcome=outcome,
                site_category=site_category,
            )
        else:
            hyp = existing
            # Avoid double-counting the initial observation already in make_hypothesis
            hyp.observe(
                env_key=env_key,
                source=source,
                context_hint=context_hint,
                outcome=outcome,
            )
            if site_category and not hyp.site_category:
                hyp.site_category = site_category

        hyp.compute_importance()
        self._save(hyp)
        return hyp

    def merge(self, hypothesis: CapabilityHypothesis) -> CapabilityHypothesis:
        """Merge an externally-built CapabilityHypothesis into the store.

        If no hypothesis exists for this hash, persist as-is.
        If one exists, merge evidence, environments, frequency, and advance status.
        Returns the merged result.
        """
        existing = self.get(hypothesis.invariant_hash)
        if existing is None:
            self._save(hypothesis)
            return hypothesis

        # Merge frequency (subtract 1 to avoid double-counting the initial observation)
        existing.frequency += max(0, hypothesis.frequency - 1)

        # Merge environments
        for env in hypothesis.environments:
            if env and env not in existing.environments:
                existing.environments.append(env)

        # Merge evidence (cap at 50)
        existing.evidence.extend(hypothesis.evidence)
        if len(existing.evidence) > 50:
            existing.evidence = existing.evidence[-50:]

        # Merge transfer stats
        existing.transfer_attempts  += hypothesis.transfer_attempts
        existing.transfer_successes += hypothesis.transfer_successes

        # Populate optional fields if missing
        if hypothesis.human_hint and not existing.human_hint:
            existing.human_hint = hypothesis.human_hint
        if hypothesis.site_category and not existing.site_category:
            existing.site_category = hypothesis.site_category

        # Advance lifecycle based on merged state
        existing._try_graduate()

        from browsermind_core.learning.capability_hypothesis import _utc_now
        existing.last_seen = _utc_now()

        self._save(existing)
        return existing

    def promote(
        self,
        invariant_hash: str,
        capability_id: Optional[str] = None,
        write_capability_record: bool = False,
        mem_store=None,
    ) -> Optional[CapabilityHypothesis]:
        """Mark hypothesis as PROMOTED and optionally write a CapabilityRecord.

        Args:
            invariant_hash:         Hash of the hypothesis to promote.
            capability_id:          If provided, sets promoted_capability_id.
            write_capability_record: If True, create a CapabilityRecord in mem_store.
            mem_store:              MemoryStore instance (required if
                                    write_capability_record=True).
        Returns the promoted hypothesis, or None if not found.
        """
        hyp = self.get(invariant_hash)
        if hyp is None:
            return None
        hyp.promote(capability_id=capability_id or invariant_hash)
        self._save(hyp)

        if write_capability_record and mem_store is not None:
            try:
                from browsermind_core.learning.capability_record import CapabilityRecord
                cap = CapabilityRecord(
                    invariant_hash=hyp.invariant_hash,
                    invariants=list(hyp.invariants),
                    promotion_tier="CANDIDATE",
                    transfer_envs=list(hyp.environments),
                    source="hypothesis_promotion",
                    is_novel=True,  # by definition: came from unknown pattern
                )
                mem_store.update_capability(cap)
            except Exception as exc:
                print(f"  [HypothesisStore/promote] CapabilityRecord write failed: {exc}")

        return hyp

    def refute(
        self,
        invariant_hash: str,
        reason: str = "",
    ) -> Optional[CapabilityHypothesis]:
        """Mark a hypothesis as REFUTED.

        Returns the refuted hypothesis, or None if not found.
        """
        hyp = self.get(invariant_hash)
        if hyp is None:
            return None
        hyp.refute(reason=reason)
        self._save(hyp)
        return hyp

    def query(
        self,
        status: Optional[List[str]] = None,
        source: Optional[str] = None,
        site_category: Optional[str] = None,
        min_frequency: int = 0,
        min_environments: int = 0,
        exclude_terminal: bool = False,
        predicate: Optional[Callable[[CapabilityHypothesis], bool]] = None,
    ) -> List[CapabilityHypothesis]:
        """Filter hypotheses by any combination of criteria.

        Args:
            status:            Allowlist of HypothesisStatus strings. None = all.
            source:            Filter by source string (exact match). None = all.
            site_category:     Filter by site_category. None = all.
            min_frequency:     Only return hypotheses with frequency >= this value.
            min_environments:  Only return hypotheses with len(environments) >= this.
            exclude_terminal:  If True, exclude PROMOTED and REFUTED.
            predicate:         Optional additional callable filter.

        Returns list sorted by frequency descending (most-seen first).
        """
        results = []
        for hyp in self.all().values():
            if status is not None and hyp.status not in status:
                continue
            if exclude_terminal and hyp.status in (
                HypothesisStatus.PROMOTED, HypothesisStatus.REFUTED
            ):
                continue
            if source is not None and hyp.source != source:
                continue
            if site_category is not None and hyp.site_category != site_category:
                continue
            if hyp.frequency < min_frequency:
                continue
            if len(hyp.environments) < min_environments:
                continue
            if predicate is not None and not predicate(hyp):
                continue
            results.append(hyp)

        results.sort(key=lambda h: h.frequency * h.importance_score, reverse=True)
        return results

    def exploration_targets(self, limit: int = 20) -> List[CapabilityHypothesis]:
        """Return hypotheses worth revisiting in the next exploration pass.

        Criteria: RECURRING or EMERGING status, not yet CANDIDATE/PROMOTED.
        Sorted by frequency descending — most-observed patterns first.
        This is the mechanism for self-directed exploration:
          Store → targets → ExplorationSpec.capability_targets → Harness → Store
        """
        return self.query(
            status=[HypothesisStatus.RECURRING, HypothesisStatus.EMERGING],
        )[:limit]

    def candidates_ready(self) -> List[CapabilityHypothesis]:
        """Return all CANDIDATE-status hypotheses ready for CapabilityRecord promotion."""
        return self.query(status=[HypothesisStatus.CANDIDATE])

    # ── Single-record I/O ─────────────────────────────────────────────────────

    def get(self, invariant_hash: str) -> Optional[CapabilityHypothesis]:
        """Load one hypothesis by hash. Returns None if not found."""
        path = self._hypothesis_path(invariant_hash)
        if not path.exists():
            return None
        try:
            return CapabilityHypothesis.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except Exception:
            return None

    def all(self) -> Dict[str, CapabilityHypothesis]:
        """Load all hypotheses. Returns dict keyed by invariant_hash."""
        result: Dict[str, CapabilityHypothesis] = {}
        for json_path in self._hypotheses_dir().glob("*.json"):
            try:
                hyp = CapabilityHypothesis.from_dict(
                    json.loads(json_path.read_text(encoding="utf-8"))
                )
                result[hyp.invariant_hash] = hyp
            except Exception:
                pass
        return result

    def delete(self, invariant_hash: str) -> bool:
        """Remove a hypothesis file. Returns True if deleted, False if not found."""
        path = self._hypothesis_path(invariant_hash)
        if path.exists():
            path.unlink()
            return True
        return False

    # ── Cross-site synthesis (#37) ────────────────────────────────────────────

    def synthesize_cross_site_patterns(
        self,
        min_sites: int = 3,
        min_frequency: int = 2,
    ) -> List[CapabilityHypothesis]:
        """
        Find hypotheses that have been independently observed on multiple sites
        and return them ranked by cross-site breadth.

        This surfaces universal UI patterns (e.g. "search box with autocomplete
        across e-commerce sites") that are more reliable for training data.

        Args:
            min_sites:      Minimum number of distinct sites (env_keys)
            min_frequency:  Minimum total observations

        Returns:
            List of hypotheses sorted by (len(environments), frequency) descending
        """
        results = self.query(
            min_frequency=min_frequency,
            min_environments=min_sites,
            exclude_terminal=False,
        )
        results.sort(
            key=lambda h: (len(h.environments), h.frequency, h.importance_score),
            reverse=True,
        )
        return results

    def cross_site_summary(self, min_sites: int = 3) -> Dict[str, Any]:
        """
        Return a summary dict of cross-site patterns for corpus reporting (#37).

        Keys:
            total_cross_site:   count of hypotheses seen on >= min_sites sites
            top_patterns:       top 10 by breadth
            by_family:          count grouped by first invariant (affordance family)
        """
        patterns = self.synthesize_cross_site_patterns(min_sites=min_sites)
        by_family: Dict[str, int] = {}
        top: List[dict] = []
        for h in patterns[:50]:
            fam = h.invariants[0] if h.invariants else "unknown"
            by_family[fam] = by_family.get(fam, 0) + 1
            if len(top) < 10:
                top.append({
                    "hash":         h.invariant_hash,
                    "invariants":   list(h.invariants),
                    "sites":        len(h.environments),
                    "frequency":    h.frequency,
                    "status":       h.status,
                    "importance":   round(h.importance_score, 3),
                })
        return {
            "total_cross_site": len(patterns),
            "min_sites_threshold": min_sites,
            "by_family": by_family,
            "top_patterns": top,
        }

    # ── Statistics ────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return counts by status."""
        counts: Dict[str, int] = {}
        for hyp in self.all().values():
            counts[hyp.status] = counts.get(hyp.status, 0) + 1
        return {
            "total": sum(counts.values()),
            "by_status": counts,
        }

    # ── Taxonomy seeding ──────────────────────────────────────────────────────

    def seed_from_taxonomy(self, category: str, env_key: str = "") -> int:
        """Pre-seed hypotheses from the capability taxonomy for a site category.

        Called by MissionWorker before starting exploration of a site so that
        the explorer policy has prior hypotheses to target. Skips keys that
        already have a hypothesis. Returns the number of new hypotheses created.
        """
        from browsermind_core.learning.capability_taxonomy import capabilities_for_category
        caps = capabilities_for_category(category)
        created = 0
        for cap_key in caps:
            h = self.observe(
                invariants=[cap_key],
                env_key=env_key,
                source="taxonomy_seed",
                outcome="UNKNOWN",
            )
            if h is not None:
                created += 1
        return created

    # ── Internal ──────────────────────────────────────────────────────────────

    def _save(self, hyp: CapabilityHypothesis) -> None:
        path = self._hypothesis_path(hyp.invariant_hash)
        _atomic_write(path, hyp.to_json())


# ── Atomic write (copied from memory_store pattern) ───────────────────────────

def _atomic_write(path: Path, content: str) -> None:
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
