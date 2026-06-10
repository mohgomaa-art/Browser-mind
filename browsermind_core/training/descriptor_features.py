"""DescriptorFeatureExtractor — Phase 1 of R6 v1.

Pure function over fields BrowserMind already records (semantic recorder,
target_integrity probe). No new fields invented; no new schema introduced.

Used by:
  - failure_pattern_miner: turns OutcomeRecord rows into binary feature dicts
                            for Apriori-lite mining.
  - RecoveryRegistry.predicate_matches: the same feature shape evaluates a
                                         mined predicate against a live
                                         descriptor at resolve-time.

The output is a flat dict[str, bool|int|float] suitable for set-membership
operations (presence flags) and threshold predicates (length, similarity).
"""
from __future__ import annotations

import difflib
from typing import Any, Dict, Optional


def _ratio(a: Optional[str], b: Optional[str]) -> float:
    """SequenceMatcher ratio over two strings; safe on None/empty."""
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 4)


def features(
    descriptor: Optional[Dict[str, Any]],
    integrity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a feature vector from a recorded step descriptor + optional
    target_integrity probe payload.

    Stable key set — the pattern miner depends on these names. Adding new
    keys is safe (mining ignores unknowns); removing or renaming a key is
    a breaking change for already-mined predicates.
    """
    d = descriptor or {}
    g = integrity or {}

    accessible_name = d.get("accessible_name") or ""
    text_content = d.get("text_content") or ""
    placeholder = d.get("placeholder") or ""
    dom_path = d.get("dom_path") or ""
    capability_hint = d.get("capability_hint") or ""
    container_label = d.get("container_label") or ""
    container_data_test = d.get("container_data_test") or ""

    resolved_text = g.get("resolved_text") or ""
    candidate_count = int(g.get("candidate_count") or 0)

    return {
        # Presence flags — the bread and butter of pattern mining.
        "has_accessible_name":   bool(accessible_name),
        "has_text_content":      bool(text_content),
        "has_placeholder":       bool(placeholder),
        "has_dom_path":          bool(dom_path),
        "has_capability_hint":   bool(capability_hint),
        "has_container_label":   bool(container_label),
        "has_test_id":           bool(container_data_test),
        # Coarse ambiguity bucket — drives strategies that rely on uniqueness.
        "candidate_count_eq_0":  candidate_count == 0,
        "candidate_count_eq_1":  candidate_count == 1,
        "candidate_count_gt_1":  candidate_count > 1,
        # Cheap text-similarity probe between recorded name and live text.
        "name_text_similarity":          _ratio(accessible_name, resolved_text),
        "name_text_similarity_gte_0_8":  _ratio(accessible_name, resolved_text) >= 0.8,
        # Length buckets — predicate-friendly.
        "name_len_short":   0 < len(accessible_name) <= 20,
        "name_len_long":    len(accessible_name) > 20,
    }


def features_from_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience for OutcomeRecord step rows. Reconstructs minimal
    descriptor + integrity from the metrics dict the Phase 1 step writer
    produced. Returns the same shape as features().
    """
    descriptor = {
        "accessible_name": metrics.get("name") or "",
        "text_content":    metrics.get("name") or "",
        "capability_hint": metrics.get("capability_hint") or "",
    }
    integrity = {
        "candidate_count": 0,
        "resolved_text": metrics.get("name") or "",
    }
    return features(descriptor, integrity)


# Stable feature key list — pattern miner enumerates these. Floats are
# excluded from boolean conjunctions; only the threshold-ed companions
# (e.g. name_text_similarity_gte_0_8) participate.
BOOLEAN_FEATURE_KEYS = (
    "has_accessible_name",
    "has_text_content",
    "has_placeholder",
    "has_dom_path",
    "has_capability_hint",
    "has_container_label",
    "has_test_id",
    "candidate_count_eq_0",
    "candidate_count_eq_1",
    "candidate_count_gt_1",
    "name_text_similarity_gte_0_8",
    "name_len_short",
    "name_len_long",
)
