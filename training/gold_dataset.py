from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import (
    ACTION_TO_ID,
    CANONICAL_ACTIONS,
    domain_from_url,
    extract_action,
    extract_action_id_and_name,
    graph_nodes,
    iter_dataset_samples,
    rel,
    stable_json_hash,
)
from training.state_family_extractor import extract_state_family
from training.verification.core import AIRTIGHT, evidence_passed


REQUIRED_GOLD_FIELDS = [
    "goal",
    "url",
    "domain",
    "state_family",
    "action",
    "target_element",
    "success",
    "goal_verified",
    "verification",
    "causality_strength",
    "evidence",
    "execution_trace",
    "before_state_hash",
    "after_state_hash",
    "before_url",
    "after_url",
    "provenance",
    "collector_version",
    "verifier_version",
    "timestamp",
    "sample_hash",
]


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "pass", "passed", "1", "ok"}
    return False


def _verification_signal(sample: Dict[str, Any]) -> str:
    for key in ("verification_signal", "validation_signal", "verification_method", "validator_signal"):
        value = sample.get(key)
        if value:
            return str(value)
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    for key in ("verification_signal", "validation_signal", "verification_method", "validator_signal"):
        value = state.get(key)
        if value:
            return str(value)
    return ""


def _goal_verified(sample: Dict[str, Any]) -> bool:
    if _truthy(sample.get("goal_verified")):
        return True
    if _truthy(sample.get("verification_passed")):
        return True
    if _truthy(sample.get("goal_reached")):
        return True
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    return _truthy(state.get("goal_verified")) or _truthy(state.get("verification_passed")) or _truthy(state.get("goal_reached"))


def _evidence(sample: Dict[str, Any]) -> Any:
    for key in ("evidence", "verification_evidence", "validation_evidence"):
        value = sample.get(key)
        if value:
            return value
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    for key in ("evidence", "verification_evidence", "validation_evidence"):
        value = state.get(key)
        if value:
            return value
    return ""


def _verification(sample: Dict[str, Any]) -> Dict[str, Any]:
    value = sample.get("verification")
    if isinstance(value, dict):
        return dict(value)

    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    value = state.get("verification")
    if isinstance(value, dict):
        return dict(value)

    goal_verified = _goal_verified(sample)
    strength = str(sample.get("causality_strength") or state.get("causality_strength") or "").strip().lower()
    if not goal_verified and not strength:
        return {}

    return {
        "goal_verified": goal_verified,
        "passed": goal_verified,
        "causality_strength": strength,
        "verification_score": sample.get("verification_score") or state.get("verification_score"),
        "verifier_name": sample.get("verifier_name") or state.get("verifier_name") or "",
        "verifier_version": sample.get("verifier_version") or state.get("verifier_version") or "",
        "process_evidence": sample.get("process_evidence") or state.get("process_evidence") or {},
        "transition_evidence": sample.get("transition_evidence") or state.get("transition_evidence") or {},
        "outcome_evidence": sample.get("outcome_evidence") or state.get("outcome_evidence") or _evidence(sample) or {},
    }


def _causality_strength(sample: Dict[str, Any], verification: Dict[str, Any]) -> str:
    value = verification.get("causality_strength") or sample.get("causality_strength")
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    value = value or state.get("causality_strength")
    return str(value or "").strip().lower()


def _verification_goal_verified(sample: Dict[str, Any], verification: Dict[str, Any]) -> bool:
    if _truthy(verification.get("goal_verified")) or _truthy(verification.get("passed")):
        return True
    return _goal_verified(sample)


def _verification_block(verification: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = verification.get(key)
    return value if isinstance(value, dict) else {}


def _execution_trace(sample: Dict[str, Any]) -> Any:
    for key in ("execution_trace", "trace", "action_trace", "events"):
        value = sample.get(key)
        if value:
            return value
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    for key in ("execution_trace", "trace", "action_trace", "events"):
        value = state.get(key)
        if value:
            return value
    return {}


def _field_from_sample(sample: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        value = sample.get(key)
        if value:
            return str(value)
    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    for key in keys:
        value = state.get(key)
        if value:
            return str(value)
    return ""


def _before_after_value(sample: Dict[str, Any], before_keys: Tuple[str, ...], after_keys: Tuple[str, ...]) -> Tuple[str, str]:
    before = _field_from_sample(sample, before_keys)
    after = _field_from_sample(sample, after_keys)
    return before, after


def _provenance(sample: Dict[str, Any]) -> Dict[str, Any]:
    value = sample.get("provenance")
    if isinstance(value, dict):
        out = dict(value)
    elif value:
        out = {"source": str(value)}
    else:
        source = sample.get("source") or sample.get("collector") or sample.get("decision_source") or "unknown"
        out = {"source": str(source)}
    out.setdefault("source", "unknown")
    out.setdefault("method", str(sample.get("collection_method") or sample.get("generator") or "unknown"))
    return out


def _timestamp(sample: Dict[str, Any]) -> str:
    for key in ("timestamp", "created_at", "collected_at"):
        value = sample.get(key)
        if value:
            return str(value)
    return ""


def _target_element(sample: Dict[str, Any]) -> str:
    action = extract_action(sample)
    for key in ("target_element", "target", "selector"):
        value = sample.get(key) or action.get(key)
        if value:
            return str(value)

    idx = action.get("element_idx")
    try:
        idx_i = int(idx)
    except Exception:
        return ""

    for node in graph_nodes(sample):
        if not isinstance(node, dict):
            continue
        try:
            if int(node.get("idx", -999)) == idx_i:
                return str(node.get("name") or node.get("role") or idx_i)
        except Exception:
            continue
    return ""


def normalize_gold_sample(sample: Dict[str, Any], source_file: Path = Path("")) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    reasons: List[str] = []
    action_id, action_name, action = extract_action_id_and_name(sample)
    if action_id is None or action_id not in CANONICAL_ACTIONS:
        reasons.append("invalid_action")
    if action_name and action_id in CANONICAL_ACTIONS and CANONICAL_ACTIONS[action_id] != action_name:
        reasons.append("action_name_mismatch")

    if sample.get("success") is not True:
        reasons.append("execution_failed")

    goal = str(sample.get("goal", "")).strip()
    url = str(sample.get("url", "")).strip()
    domain = str(sample.get("domain") or domain_from_url(url)).strip()
    state_info = extract_state_family(sample)
    target_element = _target_element(sample)
    verification = _verification(sample)
    goal_verified = _verification_goal_verified(sample, verification)
    causality_strength = _causality_strength(sample, verification)
    process_evidence = _verification_block(verification, "process_evidence")
    transition_evidence = _verification_block(verification, "transition_evidence")
    outcome_evidence = _verification_block(verification, "outcome_evidence")
    evidence = {
        "process": process_evidence,
        "transition": transition_evidence,
        "outcome": outcome_evidence,
    }
    verification_signal = _verification_signal(sample) or str(verification.get("verifier_name") or "")
    execution_trace = _execution_trace(sample)
    before_url, after_url = _before_after_value(sample, ("before_url", "url_before"), ("after_url", "url_after"))
    before_state_hash, after_state_hash = _before_after_value(
        sample,
        ("before_state_hash", "state_hash_before", "before_hash"),
        ("after_state_hash", "state_hash_after", "after_hash"),
    )
    provenance = _provenance(sample)
    timestamp = _timestamp(sample)

    if not goal:
        reasons.append("missing_goal")
    if not url:
        reasons.append("missing_url")
    if not domain or domain == "unknown":
        reasons.append("missing_domain")
    if not target_element:
        reasons.append("missing_target")
    if not goal_verified:
        reasons.append("goal_verification_missing")
    if not verification:
        reasons.append("verification_missing")
    if causality_strength != AIRTIGHT:
        reasons.append("causality_not_airtight")
    if not evidence_passed(process_evidence):
        reasons.append("process_evidence_missing")
    if not evidence_passed(transition_evidence):
        reasons.append("transition_evidence_missing")
    if not evidence_passed(outcome_evidence):
        reasons.append("outcome_evidence_missing")
    if not execution_trace:
        reasons.append("execution_trace_missing")
    if not before_url:
        reasons.append("before_url_missing")
    if not after_url:
        reasons.append("after_url_missing")
    if not before_state_hash:
        reasons.append("before_state_hash_missing")
    if not after_state_hash:
        reasons.append("after_state_hash_missing")
    if before_state_hash and after_state_hash and before_state_hash == after_state_hash:
        reasons.append("state_transition_missing")
    provenance_source = str(provenance.get("source") or "").strip().lower()
    if provenance_source in {"", "unknown", "none", "null"}:
        reasons.append("provenance_missing")
    if not verification_signal:
        reasons.append("verification_signal_missing")
    if not timestamp:
        reasons.append("timestamp_missing")

    if reasons:
        return None, reasons

    action_type = CANONICAL_ACTIONS[int(action_id)]
    element_idx = action.get("element_idx")
    verification["goal_verified"] = True
    verification["passed"] = True
    verification["gold_eligible"] = True
    verification["causality_strength"] = causality_strength
    verification.setdefault("verifier_name", verification_signal)
    verification.setdefault("verifier_version", str(sample.get("verifier_version") or "unknown"))
    sample_hash = stable_json_hash(
        {
            "goal": goal,
            "before_url": before_url,
            "after_url": after_url,
            "before_state_hash": before_state_hash,
            "after_state_hash": after_state_hash,
            "action": action_type,
            "element_idx": element_idx,
            "verification": verification,
        },
        size=24,
    )
    normalized = dict(sample)
    normalized.update(
        {
            "goal": goal,
            "url": url,
            "domain": domain,
            "state_family": state_info["state_family"],
            "state_family_hash": state_info["state_family_hash"],
            "action": action_type,
            "target_element": target_element,
            "goal_verified": True,
            "verification_signal": verification_signal,
            "verification": verification,
            "causality_strength": causality_strength,
            "evidence": evidence,
            "execution_trace": execution_trace,
            "before_url": before_url,
            "after_url": after_url,
            "before_state_hash": before_state_hash,
            "after_state_hash": after_state_hash,
            "provenance": provenance,
            "collector_version": str(sample.get("collector_version") or "unknown"),
            "verifier_version": str(verification.get("verifier_version") or "unknown"),
            "timestamp": timestamp,
            "sample_hash": sample_hash,
            "success": True,
            "source_file": rel(source_file) if source_file else str(sample.get("source_file", "")),
            "expert_action": {
                "type": action_type,
                "action_id": int(action_id),
                "element_idx": element_idx,
                "value": action.get("value", ""),
            },
        }
    )
    return normalized, []


def build_gold_dataset(
    paths: List[str] | None,
    out_dir: str = "training/gold",
    max_state_family: int = 50,
    max_domain: int = 100,
    max_examples: int = 25,
) -> Dict[str, Any]:
    out = Path(out_dir)
    quarantine_dir = out / "quarantine"
    out.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    reason_counts = Counter()
    family_counts = Counter()
    domain_counts = Counter()
    causality_counts = Counter()
    provenance_counts = Counter()
    total = 0

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        verification = _verification(sample)
        causality_counts[_causality_strength(sample, verification) or "missing"] += 1
        provenance_counts[_provenance(sample).get("source", "unknown")] += 1
        normalized, reasons = normalize_gold_sample(sample, fp)
        if normalized is not None:
            family = normalized["state_family"]
            domain = normalized["domain"]
            if family_counts[family] >= max_state_family:
                reasons.append("state_family_cap_exceeded")
            if domain_counts[domain] >= max_domain:
                reasons.append("domain_cap_exceeded")

        if normalized is None or reasons:
            for reason in reasons:
                reason_counts[reason] += 1
            rejected.append(
                {
                    "file": rel(fp),
                    "location": loc,
                    "goal": str(sample.get("goal", ""))[:160],
                    "reasons": reasons,
                }
            )
            continue

        accepted.append(normalized)
        family_counts[normalized["state_family"]] += 1
        domain_counts[normalized["domain"]] += 1

    (out / "samples.json").write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (quarantine_dir / "rejected.jsonl").open("w", encoding="utf-8") as f:
        for row in rejected:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    evidence_coverage = len(accepted) / max(total, 1)
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema": "browsermind.gold_report.v2",
        "source_paths": paths or ["default_audit_roots"],
        "total_seen": total,
        "accepted_samples": len(accepted),
        "rejected_samples": len(rejected),
        "evidence_coverage": round(evidence_coverage, 4),
        "airtight_samples": len(accepted),
        "causality_distribution": dict(causality_counts.most_common()),
        "provenance_distribution": dict(provenance_counts.most_common()),
        "success_metric": {
            "evidence_coverage_target": 0.95,
            "passes": evidence_coverage >= 0.95,
        },
        "gold_gate": {
            "passes": len(accepted) > 0 and evidence_coverage >= 0.95,
            "rule": "Gold samples require Action -> Transition -> Outcome with causality_strength=airtight.",
        },
        "reason_counts": dict(reason_counts.most_common()),
        "state_family_frequency": dict(family_counts.most_common()),
        "domain_frequency": dict(domain_counts.most_common()),
        "caps": {
            "max_samples_per_state_family": max_state_family,
            "max_samples_per_domain": max_domain,
        },
        "examples_rejected": rejected[:max_examples],
        "outputs": {
            "samples": str(out / "samples.json"),
            "quarantine": str(quarantine_dir / "rejected.jsonl"),
            "report": str(out / "gold_report.json"),
        },
    }
    (out / "gold_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build strict BrowserMind gold dataset and quarantine rejects.")
    parser.add_argument("paths", nargs="*", help="Dataset files/directories to rebuild from.")
    parser.add_argument("--out-dir", default="training/gold")
    parser.add_argument("--max-state-family", type=int, default=50)
    parser.add_argument("--max-domain", type=int, default=100)
    parser.add_argument("--max-examples", type=int, default=25)
    args = parser.parse_args()

    report = build_gold_dataset(
        args.paths or None,
        out_dir=args.out_dir,
        max_state_family=args.max_state_family,
        max_domain=args.max_domain,
        max_examples=args.max_examples,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
