from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import (
    CANONICAL_ACTIONS,
    counter_to_sorted_dict,
    extract_action_id_and_name,
    find_done_id_mismatches,
    iter_dataset_samples,
    rel,
)


def audit_actions(paths: List[str] | None = None, max_examples: int = 25) -> Dict:
    total = 0
    invalid_sample_count = 0
    invalid = []
    action_counts = Counter()
    files_affected = set()
    reasons = Counter()
    mismatch_pairs = Counter()

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        action_id, action_name, _ = extract_action_id_and_name(sample)
        if action_id is not None:
            action_counts[str(action_id)] += 1

        sample_reasons = []
        if action_id is None:
            sample_reasons.append("missing_or_non_integer_action_id")
        elif action_id not in CANONICAL_ACTIONS:
            sample_reasons.append("action_id_outside_0_7")

        if action_id in CANONICAL_ACTIONS and action_name:
            expected = CANONICAL_ACTIONS[action_id]
            if expected != action_name:
                sample_reasons.append("action_name_mismatch")
                mismatch_pairs[f"{action_id}:{expected}!={action_name}"] += 1

        if action_name == "done" and action_id != 7:
            sample_reasons.append("done_id_not_7")

        if sample_reasons:
            invalid_sample_count += 1
            files_affected.add(rel(fp))
            for reason in sample_reasons:
                reasons[reason] += 1
            if len(invalid) < max_examples:
                invalid.append(
                    {
                        "file": rel(fp),
                        "location": loc,
                        "action_id": action_id,
                        "action_name": action_name,
                        "reasons": sample_reasons,
                    }
                )

    code_mismatches = find_done_id_mismatches()
    for ref in code_mismatches:
        files_affected.add(ref["file"])

    return {
        "canonical_action_space": CANONICAL_ACTIONS,
        "total_samples": total,
        "invalid_actions": invalid_sample_count,
        "invalid_reason_instances": sum(reasons.values()),
        "invalid_samples": invalid_sample_count,
        "files_affected": len(files_affected),
        "reason_counts": counter_to_sorted_dict(reasons),
        "action_id_distribution": counter_to_sorted_dict(action_counts),
        "name_mismatch_pairs": counter_to_sorted_dict(mismatch_pairs),
        "done_id_mismatch_refs": code_mismatches[:max_examples],
        "examples": invalid,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit BrowserMind dataset action IDs.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = audit_actions(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
