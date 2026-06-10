from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evidence_audit import evidence_audit
from scripts.audit_utils import domain_from_url


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


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _summarize(sample: Dict[str, Any]) -> str:
    goal = str(sample.get("goal", ""))[:120]
    url = str(sample.get("url", ""))[:140]
    task_type = str(sample.get("task_type", ""))
    strength = str((sample.get("verification") or {}).get("causality_strength") or sample.get("causality_strength") or "")
    replay = sample.get("replay_passed")
    return f"goal={goal!r}\nurl={url!r}\ntask_type={task_type!r}\ncausality={strength!r}\nreplay_passed={replay!r}"


def _interactive_audit(samples: List[Dict[str, Any]], decisions_path: Path, limit: int = 0) -> Dict[str, Any]:
    audited = 0
    approved = 0
    rejected = 0
    reasons = Counter()

    for idx, sample in enumerate(samples, start=1):
        if limit and audited >= limit:
            break
        sample_hash = str(sample.get("sample_hash") or "")
        if not sample_hash:
            continue

        print("\n" + "=" * 70)
        print(f"[{idx}/{len(samples)}] sample_hash={sample_hash}")
        print(_summarize(sample))
        print("=" * 70)

        choice = input("Approve? (y/n/skip) ").strip().lower()
        if choice in {"skip", "s"}:
            continue
        audited += 1
        if choice in {"y", "yes"}:
            approved += 1
            row = {"sample_hash": sample_hash, "decision": "approved", "reason": "", "audited_at": _now_iso()}
            _append_jsonl(decisions_path, row)
            continue
        rejected += 1
        reason = input("Reason (short) ").strip()[:200]
        reasons[reason or "unspecified"] += 1
        row = {"sample_hash": sample_hash, "decision": "rejected", "reason": reason, "audited_at": _now_iso()}
        _append_jsonl(decisions_path, row)

    approval_rate = approved / max(audited, 1)
    return {
        "audited_samples": audited,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": round(approval_rate, 4),
        "common_failure_reasons": [r for r, _ in reasons.most_common(10)],
    }


def _load_decisions(decisions_path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not decisions_path.exists():
        return out
    with decisions_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            h = str(row.get("sample_hash") or "")
            if h:
                out[h] = row
    return out


def _report(samples: List[Dict[str, Any]], decisions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    audited = 0
    approved = 0
    rejected = 0
    reasons = Counter()

    for s in samples:
        h = str(s.get("sample_hash") or "")
        if not h or h not in decisions:
            continue
        audited += 1
        decision = str(decisions[h].get("decision", "")).lower()
        if decision == "approved":
            approved += 1
        elif decision == "rejected":
            rejected += 1
            reasons[str(decisions[h].get("reason") or "unspecified")] += 1

    approval_rate = approved / max(audited, 1)
    return {
        "audited_samples": audited,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": round(approval_rate, 4),
        "common_failure_reasons": [r for r, _ in reasons.most_common(25)],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Human audit gate for training/gold samples.")
    ap.add_argument("--samples", default="training/gold/samples.json")
    ap.add_argument("--out", default="reports/human_audit.json")
    ap.add_argument("--decisions", default="reports/human_audit_decisions.jsonl")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    samples_path = Path(args.samples)
    samples = _load_samples(samples_path)
    decisions_path = Path(args.decisions)

    if args.interactive:
        report = _interactive_audit(samples, decisions_path, limit=args.limit)
    else:
        report = _report(samples, _load_decisions(decisions_path))

    # Add automatic preflight evidence audit (does not replace human review)
    report["generated_at"] = _now_iso()
    report["schema"] = "browsermind.human_audit.v1"
    report["auto_evidence_audit"] = evidence_audit([str(samples_path)])
    _write_json(Path(args.out), report)
    print(f"[ok] wrote {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()

