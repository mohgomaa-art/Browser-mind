"""BC episode extractor — flattens OutcomeLedger step records into BC training rows.

Reads `OutcomeRecord(scope='step', outcome_type='step_attempt')` produced by
`ReplayEngine._record_step_outcomes` and emits one dict per attempt. This is the
modern data substrate; legacy `training/spec_sessions/` is frozen (see
`freeze_legacy.py`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Stage 1 resolver fixes were deployed at this timestamp.
# Records produced before this cutoff may reflect a deprecated code path.
_STAGE1_CUTOFF_ISO = "2026-06-07T20:00:00+00:00"


def extract_bc_episodes(
    outcome_ledger,
    *,
    success_only: bool = True,
    sites: Optional[Iterable[str]] = None,
    min_steps: int = 0,
    exclude_pre_stage1: bool = False,
) -> List[Dict[str, Any]]:
    """Flatten step-scope OutcomeRecords into BC episode dicts.

    Only records with `scope == "step"` and `outcome_type == "step_attempt"`
    are considered. `success_only` drops failure attempts. `sites`, when given,
    keeps only records whose `environment_instance` is in the set.
    `min_steps` drops episodes whose execution_id has fewer than that many
    step rows in the ledger (filters out smoke runs).
    `exclude_pre_stage1` drops records created before the Stage 1 resolver
    fix deployment (2026-06-07T20:00:00Z). Greenhouse records pre-dating
    Stage 1 reflect a deprecated resolver code path.
    """
    site_set = set(sites) if sites is not None else None
    cutoff_dt: Optional[datetime] = None
    if exclude_pre_stage1:
        cutoff_dt = datetime.fromisoformat(_STAGE1_CUTOFF_ISO)

    raw: List = []
    for rec in outcome_ledger.records:
        if rec.scope != "step" or rec.outcome_type != "step_attempt":
            continue
        if site_set is not None and rec.environment_instance not in site_set:
            continue
        if cutoff_dt is not None:
            rec_ts = getattr(rec, "created_at", None) or getattr(rec, "timestamp", None)
            if rec_ts is not None:
                try:
                    if isinstance(rec_ts, str):
                        rec_ts = datetime.fromisoformat(rec_ts)
                    if rec_ts.tzinfo is None:
                        rec_ts = rec_ts.replace(tzinfo=timezone.utc)
                    if rec_ts < cutoff_dt:
                        continue
                except Exception:
                    pass
        raw.append(rec)

    if min_steps > 0:
        from collections import Counter
        per_exec = Counter(str(r.execution_id) for r in raw if r.execution_id)
        keep_execs = {k for k, n in per_exec.items() if n >= min_steps}
        raw = [r for r in raw if str(r.execution_id) in keep_execs]

    episodes: List[Dict[str, Any]] = []
    for rec in raw:
        if success_only and not rec.success:
            continue
        m = rec.metrics or {}
        # P0.9: optionality is written as 'optionality' by the compiler into
        # template steps, then forwarded to metrics as 'field_optionality' by
        # _record_step_outcomes. Accept both field names for older records.
        field_optionality = m.get("field_optionality") or m.get("optionality")
        episodes.append(
            {
                "site": rec.environment_instance,
                "template_id": str(m.get("template_id", "")),
                "step_seq": int(m.get("step_seq", 0)),
                "action_type": m.get("action", ""),
                "role": m.get("role"),
                "name": m.get("name"),
                "field_optionality": field_optionality,
                "resolution_strategy": m.get("resolved_by"),
                "resolution_depth": m.get("resolution_depth"),
                "effect_verified": m.get("effect_verified"),
                "failure_class": m.get("failure_class"),
                "label": 1 if rec.success else 0,
                "step_id": m.get("step_id", ""),
                "persona_id": str(rec.persona_id),
                "execution_id": str(rec.execution_id) if rec.execution_id else None,
            }
        )
    return episodes


def extract_bc_episodes_from_repository(
    store_dir: str,
    *,
    success_only: bool = True,
    sites: Optional[Iterable[str]] = None,
    exclude_pre_stage1: bool = False,
) -> List[Dict[str, Any]]:
    """Open a `LocalJSONPersistenceProvider` at `store_dir` and extract episodes."""
    from browsermind_core.ledger.outcome_ledger import OutcomeLedger
    from browsermind_core.ledger.outcome_repository import OutcomeRepository
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider

    provider = LocalJSONPersistenceProvider(storage_dir=store_dir)
    repo = OutcomeRepository(provider)
    ledger = OutcomeLedger(repository=repo)
    return extract_bc_episodes(ledger, success_only=success_only, sites=sites, exclude_pre_stage1=exclude_pre_stage1)


def write_jsonl(episodes: List[Dict[str, Any]], out_path) -> Path:
    """Write episodes as one JSON object per line. Creates parent dirs."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ep in episodes:
            f.write(json.dumps(ep, ensure_ascii=False))
            f.write("\n")
    return path


def annotate_with_scores(
    episodes: List[Dict[str, Any]],
    *,
    weights: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Annotate each episode dict with its execution's TaskValueScore aggregate.

    Adds `task_value_score: float` and `task_value_components: dict` to every
    episode in-place.  Episodes without an execution_id share a single score
    keyed by the sentinel ``"__none__"``.

    Build CorpusStats from the full episode list before scoring so that
    corpus-level signals (transferability, rarity) are computed correctly.
    """
    from browsermind_core.training.objective_fn import CorpusStats, score_all_executions

    stats = CorpusStats.from_episodes(episodes)
    scores = score_all_executions(episodes, stats, weights=weights)

    for ep in episodes:
        eid = ep.get("execution_id") or "__none__"
        sc = scores.get(eid)
        if sc is not None:
            ep["task_value_score"] = round(sc.aggregate, 4)
            ep["task_value_components"] = sc.as_dict()
        else:
            ep["task_value_score"] = 0.0
            ep["task_value_components"] = {}

    return episodes


def summarize(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a small histogram of the extracted episodes."""
    by_site: Dict[str, int] = {}
    by_action: Dict[str, int] = {}
    by_failure_class: Dict[str, int] = {}
    templates: set = set()
    successes = 0
    for ep in episodes:
        by_site[ep.get("site", "")] = by_site.get(ep.get("site", ""), 0) + 1
        by_action[ep.get("action_type", "")] = by_action.get(ep.get("action_type", ""), 0) + 1
        fc = ep.get("failure_class")
        key = fc if fc is not None else "_none_"
        by_failure_class[key] = by_failure_class.get(key, 0) + 1
        if ep.get("template_id"):
            templates.add(ep["template_id"])
        if ep.get("label") == 1:
            successes += 1
    total = len(episodes)
    return {
        "total": total,
        "by_site": by_site,
        "by_action": by_action,
        "by_failure_class": by_failure_class,
        "success_rate": (successes / total) if total else 0.0,
        "sites_count": len(by_site),
        "templates_count": len(templates),
    }
