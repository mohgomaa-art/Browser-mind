from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sample_replayer import replay_paths


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_samples(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _index_by_hash(samples: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {}
    for idx, s in enumerate(samples):
        h = str(s.get("sample_hash") or s.get("sample_id") or "")
        if h:
            out[h] = idx
    return out


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _run(args) -> Path:
    paths = args.paths or ["training/gold/samples.json"]
    report = await replay_paths(paths, limit=args.limit, headless=not args.headed, include_graph=not args.no_graph)

    out_path = Path(args.out or "reports/replay_report.json")
    _write_json(out_path, report)

    if args.update_samples:
        samples_path = Path("training/gold/samples.json")
        samples = _load_samples(samples_path)
        idx = _index_by_hash(samples)
        for row in report.get("results", []) if isinstance(report, dict) else []:
            if not isinstance(row, dict):
                continue
            h = str(row.get("sample_hash") or "")
            if not h or h not in idx:
                continue
            samples[idx[h]]["replay_passed"] = bool(row.get("replay_passed") is True)
            samples[idx[h]]["replay_checked_at"] = _now_iso()
            samples[idx[h]]["replay"] = {
                "replay_passed": bool(row.get("replay_passed") is True),
                "actions_ok": row.get("actions_ok"),
                "state_match": row.get("state_match"),
                "url_match": row.get("url_match"),
                "verification_match": row.get("verification_match"),
                "error": (row.get("replay_trace") or {}).get("error") if isinstance(row.get("replay_trace"), dict) else "",
            }
        _write_json(samples_path, samples)

    return out_path.resolve()


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay all gold samples and emit a replay report.")
    ap.add_argument("paths", nargs="*", help="Optional paths (files/dirs). Defaults to training/gold/samples.json")
    ap.add_argument("--out", default="reports/replay_report.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-graph", action="store_true")
    ap.add_argument("--update-samples", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    out = asyncio.run(_run(args))
    print(f"[ok] wrote {out}")


if __name__ == "__main__":
    main()

