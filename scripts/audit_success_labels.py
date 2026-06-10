from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import (
    CANONICAL_ACTIONS,
    counter_to_sorted_dict,
    extract_action_id_and_name,
    iter_dataset_samples,
    load_json_file,
    rel,
    resolve_roots,
    source_files,
)


VERIFICATION_KEYS = {
    "goal_verified",
    "verification_passed",
    "goal_reached",
    "task_success",
    "strict_success",
    "validated",
    "validation_signal",
    "validator_signal",
    "goal_completed",
}


def _has_goal_verification(sample: Dict) -> bool:
    verification = sample.get("verification")
    if isinstance(verification, dict):
        strength = str(verification.get("causality_strength") or "").lower()
        if verification.get("goal_verified") is True and strength == "airtight":
            return True
        if verification.get("gold_eligible") is True and strength == "airtight":
            return True

    for key in VERIFICATION_KEYS:
        value = sample.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip() and value.strip().lower() not in {"false", "0", "none"}:
            return True

    state = sample.get("state") if isinstance(sample.get("state"), dict) else {}
    for key in VERIFICATION_KEYS:
        value = state.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip() and value.strip().lower() not in {"false", "0", "none"}:
            return True
    return False


def _sample_success_reason(sample: Dict, loc: str, trajectory_len: int, sample_index: int) -> str:
    action_id, action_name, _ = extract_action_id_and_name(sample)
    if not sample.get("success", False):
        return "not_success_label"
    if _has_goal_verification(sample):
        return "verified_goal_signal"
    if action_name == "done" or action_id == 7:
        return "verified_terminal_done"
    if trajectory_len > 1 and sample_index < trajectory_len - 1:
        return "suspicious_non_terminal_step_success"
    if action_name in {"wait", "scroll", "navigate", "click", "type"}:
        return "suspicious_step_executed_not_goal_reached"
    return "suspicious_no_goal_verification"


def _iter_trajectories(paths: List[str] | None):
    for root in resolve_roots(paths):
        files = [root] if root.is_file() else sorted(root.rglob("*.json"))
        for fp in files:
            data, _ = load_json_file(fp)
            if data is None:
                continue
            if isinstance(data, dict) and isinstance(data.get("samples"), list):
                samples = [s for s in data["samples"] if isinstance(s, dict)]
            elif isinstance(data, list):
                samples = [s for s in data if isinstance(s, dict)]
            elif isinstance(data, dict):
                samples = [data]
            else:
                samples = []
            if samples:
                yield fp, samples


def _scan_success_semantics(max_refs: int = 50) -> List[Dict]:
    patterns = [
        re.compile(r"success\s*=\s*True"),
        re.compile(r"[\"']success[\"']\s*:\s*True"),
        re.compile(r"[\"']success[\"']\s*:\s*true", re.IGNORECASE),
        re.compile(r"\.record\(.*success", re.IGNORECASE),
    ]
    refs: List[Dict] = []
    for fp in source_files():
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, start=1):
            if any(p.search(line) for p in patterns):
                refs.append({"file": rel(fp), "line": lineno, "text": line.strip()[:180]})
                if len(refs) >= max_refs:
                    return refs
    return refs


def audit_success_labels(paths: List[str] | None = None, max_examples: int = 25) -> Dict:
    counts = Counter()
    suspicious_examples = []
    files_affected = set()

    for fp, samples in _iter_trajectories(paths):
        trajectory_len = len(samples)
        for idx, sample in enumerate(samples):
            if not isinstance(sample, dict) or "success" not in sample:
                continue
            if sample.get("success") is not True:
                continue

            counts["success_labels"] += 1
            reason = _sample_success_reason(sample, f"[{idx}]", trajectory_len, idx)
            counts[reason] += 1
            if reason.startswith("verified"):
                counts["verified"] += 1
            elif reason.startswith("suspicious"):
                counts["suspicious"] += 1
                files_affected.add(rel(fp))
                if len(suspicious_examples) < max_examples:
                    action_id, action_name, _ = extract_action_id_and_name(sample)
                    suspicious_examples.append(
                        {
                            "file": rel(fp),
                            "location": f"[{idx}]",
                            "goal": str(sample.get("goal", ""))[:120],
                            "action_id": action_id,
                            "action_name": action_name,
                            "reason": reason,
                        }
                    )

    return {
        "success_labels": int(counts["success_labels"]),
        "verified": int(counts["verified"]),
        "suspicious": int(counts["suspicious"]),
        "files_affected": len(files_affected),
        "reason_counts": counter_to_sorted_dict(counts),
        "suspicious_examples": suspicious_examples,
        "success_semantics_code_refs": _scan_success_semantics(max_refs=max_examples),
        "interpretation": (
            "Verified requires an explicit goal/validation signal or terminal done action. "
            "Non-terminal step success labels are treated as suspicious because they usually mean "
            "the step executed, not that the task goal was reached."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether success=true means goal reached.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = audit_success_labels(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
