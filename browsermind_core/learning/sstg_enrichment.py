"""
sstg_enrichment.py — Backfills historical OutcomeRecord data into the SSTG.

Reads the OutcomeLedger and attempts to reconstruct semantic state transitions
from historical replay data, enriching the SSTG with edges that were observed
before the SemanticStateClassifier was deployed.

This is a one-time backfill tool that can be run periodically via:
    python -m browsermind_core.learning.sstg_enrichment
or called directly from the CLI.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from browsermind_core.learning.state_transition_graph import SemanticStateTransitionGraph
from browsermind_core.ontology.semantic_state import SemanticState


@dataclass
class EnrichmentResult:
    """Summary of a backfill run."""
    records_scanned: int = 0
    edges_added: int = 0
    edges_updated: int = 0
    records_skipped: int = 0
    envs_covered: Set[str] = field(default_factory=set)

    def summary(self) -> str:
        return (
            f"SSTG Enrichment: scanned={self.records_scanned} "
            f"added={self.edges_added} updated={self.edges_updated} "
            f"skipped={self.records_skipped} envs={len(self.envs_covered)}"
        )


# Capability type → rough state transition mapping (used when no explicit
# semantic_state_before / semantic_state_after is recorded on the OutcomeRecord).
_CAPABILITY_TRANSITION_MAP: Dict[str, tuple] = {
    # capability_hint substring → (from_context_hint, to_context_hint, auth_delta)
    "login":            ("unauthenticated", "authenticated", True),
    "signin":           ("unauthenticated", "authenticated", True),
    "sign_in":          ("unauthenticated", "authenticated", True),
    "logout":           ("authenticated", "unauthenticated", False),
    "sign_out":         ("authenticated", "unauthenticated", False),
    "register":         ("unauthenticated", "authenticated", True),
    "search":           (None, "search_results", None),
    "checkout":         (None, "checkout", None),
    "add_to_cart":      (None, "checkout", None),
    "place_order":      ("checkout", "confirmation_page", None),
    "submit_form":      (None, "confirmation_page", None),
    "upload":           (None, "upload_zone", None),
    "navigate_to":      (None, None, None),
}


class SSTGEnrichment:
    """
    Backfills SSTG edges from OutcomeRecord history.

    Two enrichment modes:
      1. Rich mode — OutcomeRecord has semantic_state_before / semantic_state_after
         fields (written by ReplayEngine after the SemanticStateClassifier was
         deployed). These are used directly.

      2. Heuristic mode — older records only have outcome_type and evidence.
         We apply _CAPABILITY_TRANSITION_MAP to infer approximate transitions.
    """

    def __init__(
        self,
        sstg: SemanticStateTransitionGraph,
        outcome_ledger_path: str,
    ) -> None:
        self._sstg = sstg
        self._path = outcome_ledger_path

    def run(self, dry_run: bool = False) -> EnrichmentResult:
        result = EnrichmentResult()
        records = self._load_records()
        result.records_scanned = len(records)

        edges_before = self._sstg.edge_count()

        for record in records:
            env_key = record.get("environment_instance") or record.get("environment_family", "unknown")
            outcome_type = record.get("outcome_type", "")
            success = record.get("success", False)

            if not success:
                result.records_skipped += 1
                continue

            # Mode 1: rich semantic state data
            sem_before = record.get("semantic_state_before")
            sem_after  = record.get("semantic_state_after")
            if sem_before and sem_after:
                cap_hash = record.get("capability_hash") or outcome_type or "unknown"
                before_state = SemanticState.from_dict(sem_before)
                after_state  = SemanticState.from_dict(sem_after)
                if not dry_run:
                    self._sstg.add_observation(before_state, after_state, cap_hash, env_key)
                result.envs_covered.add(env_key)
                continue

            # Mode 2: heuristic inference from capability_hint / outcome_type
            capability = (
                record.get("capability_hint")
                or record.get("capability_key")
                or outcome_type
                or ""
            ).lower()

            transition = self._infer_transition(capability, record)
            if transition is None:
                result.records_skipped += 1
                continue

            before_state, after_state = transition
            if before_state.fingerprint == after_state.fingerprint:
                result.records_skipped += 1
                continue

            if not dry_run:
                self._sstg.add_observation(before_state, after_state, capability, env_key)
            result.envs_covered.add(env_key)

        edges_after = self._sstg.edge_count()
        result.edges_added = max(0, edges_after - edges_before)
        result.edges_updated = result.records_scanned - result.records_skipped - result.edges_added

        return result

    def _infer_transition(
        self,
        capability: str,
        record: dict,
    ) -> Optional[tuple]:
        """Apply heuristic map to build approximate before/after states."""
        matched_key = None
        for key in _CAPABILITY_TRANSITION_MAP:
            if key in capability:
                matched_key = key
                break

        if matched_key is None:
            return None

        from_ctx_hint, to_ctx_hint, makes_auth = _CAPABILITY_TRANSITION_MAP[matched_key]

        env = record.get("environment_instance", "unknown")
        auth_before = "authenticated" if record.get("auth_level_before") else "unknown"

        if makes_auth is True:
            auth_before = "unauthenticated"
            auth_after  = "authenticated"
        elif makes_auth is False:
            auth_before = "authenticated"
            auth_after  = "unauthenticated"
        else:
            auth_after = auth_before

        ctx_before = from_ctx_hint or "unknown"
        ctx_after  = to_ctx_hint  or "unknown"

        before = SemanticState(
            auth_level=auth_before,
            page_context=ctx_before,
            confidence=0.5,
        )
        after = SemanticState(
            auth_level=auth_after,
            page_context=ctx_after,
            confidence=0.5,
        )
        return (before, after)

    def _load_records(self) -> List[dict]:
        records: List[dict] = []
        if not os.path.exists(self._path):
            return records
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return records


def run_enrichment(
    store_dir: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> EnrichmentResult:
    """
    Convenience entry point for CLI and scheduled enrichment runs.

    store_dir defaults to ~/.browsermind/
    """
    from pathlib import Path as _Path
    base = _Path(store_dir) if store_dir else _Path.home() / ".browsermind"
    sstg_path = str(base / "sstg.json")
    ledger_path = str(base / "outcome_ledger.jsonl")

    sstg = SemanticStateTransitionGraph.load(sstg_path)
    enricher = SSTGEnrichment(sstg, ledger_path)
    result = enricher.run(dry_run=dry_run)

    if not dry_run:
        sstg.save(sstg_path)

    if verbose:
        print(result.summary())

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill SSTG from OutcomeLedger history")
    parser.add_argument("--store-dir", default=None, help="BrowserMind store directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
    args = parser.parse_args()
    run_enrichment(store_dir=args.store_dir, dry_run=args.dry_run)
