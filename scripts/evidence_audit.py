from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import (
    domain_from_url,
    extract_action,
    extract_action_id_and_name,
    graph_nodes,
    iter_dataset_samples,
    rel,
    state_family_key,
)
from training.verification.core import AIRTIGHT, evidence_passed


EVIDENCE_FIELDS = [
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
    "process_evidence",
    "transition_evidence",
    "outcome_evidence",
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

SYNTHETIC_HINTS = [
    "synthetic",
    "fake",
    "generated",
    "generate_",
    "automated_gold",
    "template",
    "gpt",
    "claude",
    "simulated",
]


def _target_element(sample: Dict) -> str:
    action = extract_action(sample)
    for key in ("target_element", "target", "selector"):
        value = action.get(key) or sample.get(key)
        if value:
            return str(value)
    element_idx = action.get("element_idx")
    try:
        idx = int(element_idx)
        for node in graph_nodes(sample):
            if int(node.get("idx", -999)) == idx:
                return str(node.get("name") or node.get("role") or idx)
    except Exception:
        pass
    return ""


def _field_present(sample: Dict, field: str) -> bool:
    verification = sample.get("verification") if isinstance(sample.get("verification"), dict) else {}
    if field == "domain":
        return bool(sample.get("domain") or domain_from_url(str(sample.get("url", ""))) != "unknown")
    if field == "state_family":
        return bool(sample.get("state_family") or state_family_key(sample) != "empty")
    if field == "action":
        _, action_name, _ = extract_action_id_and_name(sample)
        return bool(sample.get("action") or sample.get("expert_action") or action_name)
    if field == "target_element":
        return bool(_target_element(sample))
    if field == "goal_verified":
        return sample.get("goal_verified") is True and verification.get("goal_verified") is True
    if field == "verification":
        return bool(verification)
    if field == "causality_strength":
        return str(verification.get("causality_strength") or sample.get("causality_strength") or "").lower() == AIRTIGHT
    if field == "process_evidence":
        return evidence_passed(verification.get("process_evidence"))
    if field == "transition_evidence":
        return evidence_passed(verification.get("transition_evidence"))
    if field == "outcome_evidence":
        return evidence_passed(verification.get("outcome_evidence"))
    if field == "execution_trace":
        return bool(sample.get("execution_trace") or sample.get("trace") or sample.get("action_trace"))
    if field == "provenance":
        provenance = sample.get("provenance")
        if isinstance(provenance, dict):
            source = str(provenance.get("source") or "").strip().lower()
            return bool(source and source not in {"unknown", "none", "null"})
        source = str(provenance or "").strip().lower()
        return bool(source and source not in {"unknown", "none", "null"})
    if field == "verifier_version":
        return bool(sample.get("verifier_version") or verification.get("verifier_version"))
    value = sample.get(field)
    return value is not None and value != ""


def _synthetic_flags(fp: Path, sample: Dict) -> List[str]:
    haystack = " ".join(
        [
            rel(fp).lower(),
            str(sample.get("collector_version", "")).lower(),
            str(sample.get("source", "")).lower(),
            str(sample.get("generator", "")).lower(),
            str(sample.get("metadata", "")).lower(),
        ]
    )
    return [hint for hint in SYNTHETIC_HINTS if hint in haystack]


def evidence_audit(paths: List[str] | None = None, max_examples: int = 25) -> Dict:
    total = 0
    missing_counts = Counter()
    synthetic_counts = Counter()
    incomplete = 0
    synthetic = 0
    examples = []
    synthetic_examples = []

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        missing = [field for field in EVIDENCE_FIELDS if not _field_present(sample, field)]
        flags = _synthetic_flags(fp, sample)

        if missing:
            incomplete += 1
            for field in missing:
                missing_counts[field] += 1
            if len(examples) < max_examples:
                examples.append(
                    {
                        "file": rel(fp),
                        "location": loc,
                        "goal": str(sample.get("goal", ""))[:120],
                        "missing": missing,
                    }
                )

        if flags:
            synthetic += 1
            for flag in flags:
                synthetic_counts[flag] += 1
            if len(synthetic_examples) < max_examples:
                synthetic_examples.append(
                    {
                        "file": rel(fp),
                        "location": loc,
                        "flags": flags,
                        "goal": str(sample.get("goal", ""))[:120],
                    }
                )

    return {
        "total_samples": total,
        "complete_evidence_samples": total - incomplete,
        "incomplete_evidence_samples": incomplete,
        "incomplete_evidence_rate": round(incomplete / max(total, 1), 4),
        "missing_field_counts": dict(missing_counts.most_common()),
        "synthetic_suspect_samples": synthetic,
        "synthetic_suspect_rate": round(synthetic / max(total, 1), 4),
        "synthetic_hint_counts": dict(synthetic_counts.most_common()),
        "production_dataset_gate": {
            "passes": incomplete == 0 and synthetic == 0,
            "rule": "No production training sample may lack airtight causal evidence or come from synthetic/generated sources.",
        },
        "examples": examples,
        "synthetic_examples": synthetic_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit sample evidence completeness and synthetic flags.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = evidence_audit(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
