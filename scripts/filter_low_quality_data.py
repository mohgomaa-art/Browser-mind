"""
Filter low-quality legacy samples and build a curated dataset for polishing.

This script reads spec-style JSON samples from one or more input roots,
filters weak records, deduplicates them, optionally drops the oldest slice,
and writes flat JSON files that are directly consumable by GraphDataset.

Usage:
  python scripts/filter_low_quality_data.py \
    --inputs training/spec_sessions training/super_complex_sessions \
    --output training/filtered_polish_sessions \
    --drop-oldest-fraction 0.35 \
    --min-score 4.2
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

# Ensure repository root is importable when script is run as a file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.graph_dataset import _apply_quality_rules, _dedup_key


INTERACTIVE_ROLES = {
    "button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem",
    "searchbox", "spinbutton", "slider", "switch", "tab", "option", "listbox",
    "grid", "row", "cell", "treeitem", "tabpanel",
}
TYPE_FRIENDLY_ROLES = {"textbox", "combobox", "searchbox", "generic"}


@dataclass
class Candidate:
    src_file: Path
    raw: Dict
    key: str
    score: float
    ts: Optional[int]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Curate high-quality training samples")
    p.add_argument(
        "--inputs",
        nargs="+",
        default=["training/spec_sessions", "training/super_complex_sessions"],
        help="Input directories to scan recursively for JSON files",
    )
    p.add_argument("--output", default="training/filtered_polish_sessions")
    p.add_argument("--min-nodes", type=int, default=4)
    p.add_argument("--min-interactive", type=int, default=1)
    p.add_argument("--min-named-ratio", type=float, default=0.08)
    p.add_argument("--min-score", type=float, default=4.2)
    p.add_argument("--drop-oldest-fraction", type=float, default=0.35)
    p.add_argument("--max-samples", type=int, default=20000)
    p.add_argument("--keep-output", action="store_true", help="Do not wipe output before writing")
    return p.parse_args()


def iter_json_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*.json") if p.name != "skipped_tasks.json")


def load_records(fp: Path) -> List[Dict]:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(data, dict) and isinstance(data.get("samples"), list):
        return [x for x in data["samples"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def extract_ts(fp: Path, rec: Dict) -> Optional[int]:
    m = re.search(r"_(\d{10})(?:_|$)", fp.stem)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass

    for key in ("timestamp", "ts", "created_at"):
        v = rec.get(key)
        if isinstance(v, (int, float)):
            return int(v)
    return None


def evaluate_record(
    rec: Dict,
    min_nodes: int,
    min_interactive: int,
    min_named_ratio: float,
    min_score: float,
) -> Tuple[bool, str, float]:
    base = _apply_quality_rules(rec)
    if base is None:
        return False, "invalid_by_core_rules", 0.0

    nodes = base.nodes
    if len(nodes) < min_nodes:
        return False, "too_few_nodes", 0.0

    interactive = sum(1 for n in nodes if str(n.get("role", "")) in INTERACTIVE_ROLES)
    if interactive < min_interactive:
        return False, "too_few_interactive", 0.0

    named = sum(1 for n in nodes if str(n.get("name", "")).strip())
    named_ratio = named / max(len(nodes), 1)
    if named_ratio < min_named_ratio:
        return False, "low_named_ratio", 0.0

    aid = base.action_id
    elem_idx = base.element_idx

    # Click/type samples should remain grounded in a target element.
    if aid in (1, 2) and elem_idx is None:
        return False, "ungrounded_click_or_type", 0.0

    if aid == 2 and elem_idx is not None:
        role = str(nodes[elem_idx].get("role", "generic")) if 0 <= elem_idx < len(nodes) else "generic"
        if role not in TYPE_FRIENDLY_ROLES:
            return False, "type_target_not_input_like", 0.0

    # Simple quality score for ranking before truncation.
    score = 0.0
    score += min(interactive, 5) * 0.8
    score += min(named_ratio, 1.0) * 2.5
    score += 1.5 if elem_idx is not None else 0.0
    score += 1.0 if base.success else 0.0

    goal_l = str(base.goal or "").lower()
    if any(k in goal_l for k in ("signup", "register", "form", "login", "search")):
        score += 0.5

    if score < min_score:
        return False, "below_min_score", score

    return True, "kept", score


def main() -> None:
    args = parse_args()

    output_dir = Path(args.output)
    if output_dir.exists() and not args.keep_output:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    roots = [Path(x) for x in args.inputs]

    stats: Dict[str, int] = {
        "files_scanned": 0,
        "records_seen": 0,
        "records_kept_before_dedupe": 0,
        "records_kept_after_dedupe": 0,
        "records_final": 0,
        "duplicates": 0,
        "dropped_oldest": 0,
        "dropped_by_cap": 0,
    }
    drops: Dict[str, int] = {}

    candidates: List[Candidate] = []

    for root in roots:
        for fp in iter_json_files(root):
            stats["files_scanned"] += 1
            records = load_records(fp)
            for rec in records:
                stats["records_seen"] += 1
                ok, reason, score = evaluate_record(
                    rec,
                    min_nodes=args.min_nodes,
                    min_interactive=args.min_interactive,
                    min_named_ratio=args.min_named_ratio,
                    min_score=args.min_score,
                )
                if not ok:
                    drops[reason] = drops.get(reason, 0) + 1
                    continue

                key = _dedup_key(rec)
                candidates.append(
                    Candidate(
                        src_file=fp,
                        raw=rec,
                        key=key,
                        score=score,
                        ts=extract_ts(fp, rec),
                    )
                )
                stats["records_kept_before_dedupe"] += 1

    # Dedupe globally.
    deduped: List[Candidate] = []
    seen = set()
    for c in candidates:
        if c.key in seen:
            stats["duplicates"] += 1
            continue
        seen.add(c.key)
        deduped.append(c)
    stats["records_kept_after_dedupe"] = len(deduped)

    # Drop oldest fraction among records that have timestamp.
    if args.drop_oldest_fraction > 0.0:
        with_ts = [c for c in deduped if c.ts is not None]
        without_ts = [c for c in deduped if c.ts is None]

        if with_ts:
            with_ts.sort(key=lambda x: x.ts or 0)
            n_drop = int(len(with_ts) * max(0.0, min(args.drop_oldest_fraction, 0.95)))
            if n_drop > 0:
                stats["dropped_oldest"] = n_drop
                with_ts = with_ts[n_drop:]

        deduped = with_ts + without_ts

    # Keep highest-scoring samples when capped.
    deduped.sort(key=lambda x: x.score, reverse=True)
    if args.max_samples > 0 and len(deduped) > args.max_samples:
        stats["dropped_by_cap"] = len(deduped) - args.max_samples
        deduped = deduped[: args.max_samples]

    # Write flat files compatible with GraphDataset(data_dir=...)
    for i, c in enumerate(deduped, start=1):
        out_name = f"Q_{i:06d}_{c.src_file.stem}.json"
        out_path = output_dir / out_name
        out_path.write_text(json.dumps([c.raw], ensure_ascii=False, indent=2), encoding="utf-8")

    stats["records_final"] = len(deduped)

    scores = [c.score for c in deduped]
    report = {
        "inputs": [str(r) for r in roots],
        "output": str(output_dir),
        "params": {
            "min_nodes": args.min_nodes,
            "min_interactive": args.min_interactive,
            "min_named_ratio": args.min_named_ratio,
            "min_score": args.min_score,
            "drop_oldest_fraction": args.drop_oldest_fraction,
            "max_samples": args.max_samples,
        },
        "stats": stats,
        "drops": drops,
        "score_summary": {
            "count": len(scores),
            "median": float(median(scores)) if scores else 0.0,
            "max": float(max(scores)) if scores else 0.0,
            "min": float(min(scores)) if scores else 0.0,
        },
    }

    report_path = output_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 72)
    print("Low-quality data filtering complete")
    print(f"Output dir         : {output_dir}")
    print(f"Files scanned      : {stats['files_scanned']}")
    print(f"Records seen       : {stats['records_seen']}")
    print(f"Kept pre-dedupe    : {stats['records_kept_before_dedupe']}")
    print(f"Kept post-dedupe   : {stats['records_kept_after_dedupe']}")
    print(f"Dropped oldest     : {stats['dropped_oldest']}")
    print(f"Dropped by cap     : {stats['dropped_by_cap']}")
    print(f"Final kept         : {stats['records_final']}")
    print(f"Report             : {report_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
