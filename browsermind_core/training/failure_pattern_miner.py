"""FailurePatternMiner — Phase 2 of R6 v1.

Apriori-lite mining over OutcomeLedger step records. Consumes Phase 1's
descriptor feature vectors and emits PatternCandidate dicts that the
caller can convert into RecoveryCandidates (Phase 4) and push through
the shadow validation pipeline.

The miner is deterministic, stdlib-only, and side-effect free: it reads
records, returns ranked candidates, and never persists. Persistence is
the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from browsermind_core.ontology.recovery_candidate import RecoveryCandidate
from browsermind_core.runtime.primitive_library import known_primitives
from browsermind_core.training.descriptor_features import (
    BOOLEAN_FEATURE_KEYS,
    features_from_metrics,
)


# --- Primitive suggestion table ---------------------------------------------
#
# Ordered: the first flag in the predicate that hits this table wins. The
# ordering encodes preference — stable, deterministic, easy to audit.
_PRIMITIVE_BY_FLAG: Tuple[Tuple[str, str], ...] = (
    ("has_placeholder",       "by_placeholder"),
    ("has_test_id",           "by_test_id"),
    ("has_accessible_name",   "by_text"),
    ("has_text_content",      "by_text"),
    ("has_dom_path",          "structural"),
    ("has_capability_hint",   "by_capability"),
    ("has_container_label",   "container_proximity"),
)
_DEFAULT_PRIMITIVE = "by_role"


@dataclass
class PatternCandidate:
    predicate: Dict[str, bool]
    support: int
    baseline_support: int
    lift: float
    suggested_primitive: str
    example_record_ids: List[str] = field(default_factory=list)


# --- Cohort splitting -------------------------------------------------------


def _metrics(rec: Any) -> Optional[Dict[str, Any]]:
    m = getattr(rec, "metrics", None)
    if m is None:
        return None
    return m


def _failure_class(rec: Any) -> str:
    m = _metrics(rec) or {}
    return str(m.get("failure_class") or "")


def _recovered_by(rec: Any) -> str:
    m = _metrics(rec) or {}
    rb = m.get("recovered_by")
    return str(rb) if rb else ""


def split_cohorts(
    records: Iterable[Any],
    *,
    failure_class: str = "TARGET_CHANGED",
) -> Tuple[List[Any], List[Any]]:
    """Return (unrecovered, recovered) cohorts.

    unrecovered = scope==step, failure_class matches, NOT success, AND
                  recovered_by is None/empty.
    recovered   = scope==step, failure_class matches, success=True
                  (regardless of how it recovered).
    """
    unrecovered: List[Any] = []
    recovered: List[Any] = []
    for rec in records or []:
        if getattr(rec, "scope", None) != "step":
            continue
        if _metrics(rec) is None:
            continue
        if _failure_class(rec) != failure_class:
            continue
        success = bool(getattr(rec, "success", False))
        if success:
            recovered.append(rec)
        else:
            if not _recovered_by(rec):
                unrecovered.append(rec)
    return unrecovered, recovered


# --- Mining -----------------------------------------------------------------


def _feature_vectors(
    records: Sequence[Any],
) -> List[Tuple[str, Dict[str, Any]]]:
    """Pair each record's id with its feature vector. Records whose metrics
    is None were already filtered by split_cohorts; we re-guard here so the
    function is safe to call standalone."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for rec in records:
        m = _metrics(rec)
        if m is None:
            continue
        feats = features_from_metrics(m)
        out.append((str(getattr(rec, "id", "")), feats))
    return out


def _matches(predicate: Dict[str, bool], feats: Dict[str, Any]) -> bool:
    for k, v in predicate.items():
        if bool(feats.get(k, False)) != bool(v):
            return False
    return True


def _suggest_primitive(predicate: Dict[str, bool]) -> str:
    known = set(known_primitives())
    for flag, prim in _PRIMITIVE_BY_FLAG:
        if predicate.get(flag) and prim in known:
            return prim
    return _DEFAULT_PRIMITIVE if _DEFAULT_PRIMITIVE in known else _DEFAULT_PRIMITIVE


def mine_patterns(
    records: Iterable[Any],
    *,
    failure_class: str = "TARGET_CHANGED",
    min_support: int = 20,
    min_lift: float = 2.0,
    max_conjunction_size: int = 3,
) -> List[PatternCandidate]:
    """Apriori-lite over the unrecovered/recovered cohorts.

    Iterates only BOOLEAN_FEATURE_KEYS with value=True. Conjunction size
    is hard-capped at 3 — larger requests are rejected.
    """
    if max_conjunction_size > 3:
        raise ValueError("max_conjunction_size hard ceiling is 3")
    if max_conjunction_size < 1:
        return []

    materialized = list(records or [])
    if not materialized:
        return []

    unrecovered, recovered = split_cohorts(
        materialized, failure_class=failure_class
    )
    if not unrecovered:
        return []

    unrec_vecs = _feature_vectors(unrecovered)
    rec_vecs = _feature_vectors(recovered)
    if not unrec_vecs:
        return []

    keys = tuple(BOOLEAN_FEATURE_KEYS)

    # Size-1 support gate over the unrecovered cohort. Only flags that
    # individually clear min_support survive into higher orders (apriori).
    size1_passing: List[str] = []
    for key in keys:
        count = sum(1 for _, f in unrec_vecs if bool(f.get(key, False)))
        if count >= min_support:
            size1_passing.append(key)

    candidates: List[PatternCandidate] = []
    # Track conjunction frozensets that passed the support gate at each
    # level so the next level can apply the apriori property.
    passing_at_level: Dict[int, set] = {0: {frozenset()}}
    for k in (1,):
        passing_at_level[k] = {frozenset([key]) for key in size1_passing}

    def _emit(predicate_keys: Sequence[str]) -> Optional[PatternCandidate]:
        predicate = {k: True for k in predicate_keys}
        examples: List[str] = []
        support = 0
        for rid, feats in unrec_vecs:
            if _matches(predicate, feats):
                support += 1
                if len(examples) < 10 and rid and rid not in examples:
                    examples.append(rid)
        if support < min_support:
            return None
        baseline = sum(1 for _, f in rec_vecs if _matches(predicate, f))
        lift = support / max(baseline, 1)
        return PatternCandidate(
            predicate=predicate,
            support=support,
            baseline_support=baseline,
            lift=lift,
            suggested_primitive=_suggest_primitive(predicate),
            example_record_ids=examples,
        )

    # Size 1
    for key in size1_passing:
        pc = _emit([key])
        if pc is not None and pc.lift >= min_lift:
            candidates.append(pc)

    # Sizes 2..max_conjunction_size — apriori prune: every (size-1) subset
    # of the candidate conjunction must already have passed the support gate.
    for size in range(2, max_conjunction_size + 1):
        prev_passing = passing_at_level.get(size - 1, set())
        if not prev_passing:
            break
        current_passing: set = set()
        for combo in combinations(size1_passing, size):
            fs = frozenset(combo)
            # apriori: every (size-1) subset must be in prev_passing.
            ok = True
            for sub in combinations(combo, size - 1):
                if frozenset(sub) not in prev_passing:
                    ok = False
                    break
            if not ok:
                continue
            pc = _emit(list(combo))
            if pc is None:
                continue
            current_passing.add(fs)
            if pc.lift >= min_lift:
                candidates.append(pc)
        passing_at_level[size] = current_passing

    candidates.sort(key=lambda c: (-c.lift, -c.support))
    return candidates


# --- Conversion to RecoveryCandidate ----------------------------------------


def to_recovery_candidate(
    p: PatternCandidate,
    *,
    name_hint: str = "",
) -> RecoveryCandidate:
    """Build a RecoveryCandidate from a PatternCandidate. Caller persists."""
    if name_hint:
        name = name_hint[:64]
    else:
        flags = sorted(p.predicate.keys())
        name = f"mined:{p.suggested_primitive}+{flags}"[:64]
    return RecoveryCandidate(
        name=name,
        predicate=dict(p.predicate),
        primitive=p.suggested_primitive,
        support=int(p.support),
        lift=float(p.lift),
        mined_from=list(p.example_record_ids),
        status="pending",
    )
