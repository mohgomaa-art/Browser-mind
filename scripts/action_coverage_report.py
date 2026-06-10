from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import CANONICAL_ACTIONS, extract_action_id_and_name, iter_dataset_samples


DEFAULT_TARGETS = {
    "navigate": 50,
    "extract": 50,
    "go_back": 50,
}


def action_coverage(paths: List[str] | None = None, per_action_target: int = 0) -> Dict:
    counts = Counter()
    total = 0
    for _, _, sample in iter_dataset_samples(paths):
        total += 1
        action_id, action_name, _ = extract_action_id_and_name(sample)
        if not action_name and action_id in CANONICAL_ACTIONS:
            action_name = CANONICAL_ACTIONS[action_id]
        counts[action_name or "unknown"] += 1

    targets = dict(DEFAULT_TARGETS)
    if per_action_target > 0:
        for name in CANONICAL_ACTIONS.values():
            targets[name] = per_action_target

    deficits = {
        action: max(0, target - counts.get(action, 0))
        for action, target in targets.items()
    }
    distribution = {
        action: {
            "count": count,
            "pct": round(count / max(total, 1), 4),
        }
        for action, count in counts.most_common()
    }

    max_action_pct = max((v["pct"] for v in distribution.values()), default=0.0)
    return {
        "total_samples": total,
        "action_distribution": distribution,
        "collection_targets": targets,
        "deficits": deficits,
        "balanced_distribution_gate": {
            "max_action_pct": max_action_pct,
            "passes": max_action_pct <= 0.20 if total else False,
            "target": "No action should exceed 20% of production training distribution.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report action coverage and collection deficits.")
    parser.add_argument("paths", nargs="*", help="Optional files/directories to audit.")
    parser.add_argument("--per-action-target", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = action_coverage(args.paths or None, per_action_target=args.per_action_target)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
