"""Lock replay reliability Phase 1 baseline numbers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from browsermind_core.experiments.baseline_lock import lock_phase1_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="Lock Phase 1 replay reliability baseline.")
    parser.add_argument(
        "--identity-sprint",
        default="reports/identity_sprint/sprint_results.json",
        help="Path to identity sprint baseline JSON.",
    )
    parser.add_argument(
        "--target-changed-dossier",
        default="reports/forensic/target_changed_dossier.json",
        help="Path to target changed dossier JSON.",
    )
    parser.add_argument(
        "--out",
        default="reports/replay_reliability/phase1_baseline_locked.json",
        help="Output path for locked baseline JSON.",
    )
    args = parser.parse_args()

    locked = lock_phase1_baseline(
        identity_sprint_path=Path(args.identity_sprint),
        target_changed_dossier_path=Path(args.target_changed_dossier),
        output_path=Path(args.out),
    )
    print(json.dumps(locked, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
