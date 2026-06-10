from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import counter_to_sorted_dict, iter_dataset_samples, rel


HEURISTIC_HINTS = {"heuristic", "fallback", "rule", "script", "automated", "synthetic", "generated", "simulated"}
HUMAN_HINTS = {"human", "manual", "teacher", "operator"}
POLICY_HINTS = {"policy", "model", "learned", "agent"}
CORRECTED_HINTS = {"corrected", "correction", "edited", "reviewed"}


def _raw_provenance(sample: Dict[str, Any]) -> Dict[str, Any]:
    provenance = sample.get("provenance")
    if isinstance(provenance, dict):
        out = dict(provenance)
    elif provenance:
        out = {"source": str(provenance)}
    else:
        out = {}
    for key in ("source", "collector", "generator", "decision_source", "collection_method"):
        if key in sample and key not in out:
            out[key] = sample.get(key)
    out.setdefault("source", "unknown")
    return out


def _category(provenance: Dict[str, Any]) -> str:
    text = " ".join(str(value).lower() for value in provenance.values() if value is not None)
    tokens = set(text.replace("-", "_").replace("/", " ").split())
    if any(hint in text for hint in CORRECTED_HINTS) or tokens & CORRECTED_HINTS:
        return "corrected"
    if any(hint in text for hint in HUMAN_HINTS) or tokens & HUMAN_HINTS:
        return "human"
    if any(hint in text for hint in POLICY_HINTS) or tokens & POLICY_HINTS:
        return "policy"
    if any(hint in text for hint in HEURISTIC_HINTS) or tokens & HEURISTIC_HINTS:
        return "heuristic"
    return "unknown"


def provenance_report(paths: List[str] | None = None, max_examples: int = 25) -> Dict[str, Any]:
    total = 0
    categories = Counter()
    sources = Counter()
    examples = []

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        provenance = _raw_provenance(sample)
        category = _category(provenance)
        source = str(provenance.get("source") or "unknown")
        categories[category] += 1
        sources[source] += 1
        if len(examples) < max_examples and category in {"heuristic", "unknown"}:
            examples.append(
                {
                    "file": rel(fp),
                    "location": loc,
                    "category": category,
                    "source": source,
                    "goal": str(sample.get("goal", ""))[:120],
                }
            )

    heuristic_like = categories["heuristic"]
    heuristic_rate = heuristic_like / max(total, 1)
    unknown_rate = categories["unknown"] / max(total, 1)
    gate_failures = []
    warnings = []
    if total <= 0:
        gate_failures.append("total_samples=0")
    if heuristic_rate >= 0.95 and total:
        gate_failures.append(f"heuristic_like_rate={heuristic_rate:.2%}")
    elif heuristic_rate >= 0.80:
        warnings.append(f"heuristic_like_rate={heuristic_rate:.2%}")
    if unknown_rate > 0:
        gate_failures.append(f"unknown_provenance_rate={unknown_rate:.2%}")

    return {
        "total_samples": total,
        "category_distribution": counter_to_sorted_dict(categories),
        "source_distribution": counter_to_sorted_dict(sources),
        "heuristic_like_rate": round(heuristic_rate, 4),
        "unknown_rate": round(unknown_rate, 4),
        "gate": {
            "passes": not gate_failures,
            "failures": gate_failures,
            "warnings": warnings,
            "rule": "Report provenance every run; fail when the dataset is effectively heuristic distillation.",
        },
        "examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report BrowserMind sample provenance distribution.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    report = provenance_report(args.paths or None, max_examples=args.max_examples)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
