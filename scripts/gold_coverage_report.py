from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import domain_from_url, state_family_key


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


def _provenance_key(sample: Dict[str, Any]) -> str:
    prov = sample.get("provenance")
    if isinstance(prov, dict):
        return str(prov.get("source") or "unknown")
    if prov:
        return str(prov)
    return "unknown"


def _verifier_key(sample: Dict[str, Any]) -> str:
    ver = sample.get("verification")
    if isinstance(ver, dict):
        return f"{ver.get('verifier_name','')}/{ver.get('verifier_version','')}".strip("/") or "unknown"
    return "unknown"


def _share(counter: Counter, total: int) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in counter.items():
        out[str(k)] = round(v / max(total, 1), 4)
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def coverage_report(samples_path: Path) -> Dict[str, Any]:
    samples = _load_samples(samples_path)
    total = len(samples)

    domains = Counter()
    task_types = Counter()
    state_families = Counter()
    provenance = Counter()
    verifier_distribution = Counter()

    for s in samples:
        url = str(s.get("url", ""))
        domains[domain_from_url(url)] += 1
        task_types[str(s.get("task_type") or "unknown")] += 1
        # state_family_key expects a dict with graph nodes; we store graph at top-level already
        state_families[str(s.get("state_family") or state_family_key(s))] += 1
        provenance[_provenance_key(s)] += 1
        verifier_distribution[_verifier_key(s)] += 1

    def _dominance_violations(counter: Counter, limit: float) -> List[Dict[str, Any]]:
        out = []
        for k, v in counter.most_common():
            share = v / max(total, 1)
            if share > limit:
                out.append({"key": str(k), "share": round(share, 4), "count": int(v), "limit": limit})
        return out

    return {
        "generated_at": _now_iso(),
        "schema": "browsermind.gold_coverage.v1",
        "total_samples": total,
        "state_families": dict(state_families),
        "domains": dict(domains),
        "task_types": dict(task_types),
        "provenance": dict(provenance),
        "verifier_distribution": dict(verifier_distribution),
        "shares": {
            "state_families": _share(state_families, total),
            "domains": _share(domains, total),
            "task_types": _share(task_types, total),
        },
        "dominance_checks": {
            "no_family_over_20pct": {
                "passes": not _dominance_violations(state_families, 0.20),
                "violations": _dominance_violations(state_families, 0.20),
            },
            "no_domain_over_10pct": {
                "passes": not _dominance_violations(domains, 0.10),
                "violations": _dominance_violations(domains, 0.10),
            },
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Gold coverage report (domains/state families/task types/provenance/verifiers).")
    ap.add_argument("--samples", default="training/gold/samples.json")
    ap.add_argument("--out", default="reports/gold_coverage.json")
    args = ap.parse_args()

    report = coverage_report(Path(args.samples))
    _write_json(Path(args.out), report)
    print(f"[ok] wrote {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()

