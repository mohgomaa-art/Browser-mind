"""
Corpus Statistics — query and report on the collected exploration corpus (#94).

Answers:
  - How many unique (site, affordance_family, effect_type) triples?
  - What is the evidence quality distribution?
  - Which sites are over/under-represented?
  - What affordance families have the most coverage?
  - What is the temporal freshness of the corpus?

Usage:
    from browsermind_core.mission.corpus_stats import CorpusStats
    stats = CorpusStats(store_dir=Path("~/.browsermind"))
    print(stats.summary())
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class CorpusStats:

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = Path(store_dir)

    def _load_queue(self) -> List[dict]:
        path = self._store_dir / "missions" / "queue.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
        except Exception:
            return []

    def _load_ledger(self) -> List[dict]:
        """Load outcome ledger entries from store."""
        path = self._store_dir / "ledger.json"
        if not path.exists():
            # Try alternate locations
            for alt in ["outcomes.json", "ledger", "outcome_ledger.json"]:
                path = self._store_dir / alt
                if path.exists():
                    break
            else:
                return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return data.get("entries", data.get("records", []))
        except Exception:
            return []

    def _load_hypotheses(self) -> List[dict]:
        path = self._store_dir / "hypothesis_store.json"
        if not path.exists():
            for alt in ["hypotheses.json", "hypotheses"]:
                candidate = self._store_dir / alt
                if candidate.exists():
                    path = candidate
                    break
            else:
                return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return data.get("hypotheses", data.get("entries", []))
        except Exception:
            return []

    def queue_summary(self) -> Dict[str, Any]:
        entries = self._load_queue()
        counts: Dict[str, int] = {}
        categories: Dict[str, int] = {}
        total_steps = 0
        total_hyps = 0
        quality_scores: List[float] = []

        for e in entries:
            status = e.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1

            tags = e.get("tags", [])
            for tag in tags:
                categories[tag] = categories.get(tag, 0) + 1

            total_steps += e.get("last_steps") or 0
            total_hyps += e.get("last_hypotheses") or 0

            qs = e.get("avg_quality_score", 0.0)
            if qs > 0:
                quality_scores.append(qs)

            for run in (e.get("run_history") or []):
                qs2 = run.get("quality_score", 0.0)
                if qs2 > 0:
                    quality_scores.append(qs2)

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return {
            "total_entries":      len(entries),
            "by_status":          counts,
            "total_steps":        total_steps,
            "total_hypotheses":   total_hyps,
            "avg_quality_score":  round(avg_quality, 3),
            "tag_distribution":   categories,
        }

    def hypothesis_summary(self) -> Dict[str, Any]:
        hyps = self._load_hypotheses()
        by_family: Dict[str, int] = {}
        by_confidence: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}

        for h in hyps:
            fam = h.get("family", h.get("affordance_family", "unknown"))
            by_family[fam] = by_family.get(fam, 0) + 1
            conf = float(h.get("confidence", h.get("score", 0.0)))
            if conf >= 0.8:
                by_confidence["high"] += 1
            elif conf >= 0.5:
                by_confidence["medium"] += 1
            else:
                by_confidence["low"] += 1

        return {
            "total_hypotheses": len(hyps),
            "by_family":        by_family,
            "by_confidence":    by_confidence,
        }

    def freshness_summary(self) -> Dict[str, Any]:
        """Report temporal freshness of the corpus (#77)."""
        entries = self._load_queue()
        now = time.time()
        age_buckets = {"<1d": 0, "1-7d": 0, "7-30d": 0, ">30d": 0, "never": 0}

        for e in entries:
            ts = e.get("last_run_ts")
            if ts is None:
                age_buckets["never"] += 1
                continue
            age_days = (now - ts) / 86400
            if age_days < 1:
                age_buckets["<1d"] += 1
            elif age_days < 7:
                age_buckets["1-7d"] += 1
            elif age_days < 30:
                age_buckets["7-30d"] += 1
            else:
                age_buckets[">30d"] += 1

        return {"by_age": age_buckets}

    def site_coverage_summary(self) -> Dict[str, Any]:
        """Which sites have the best corpus coverage?"""
        entries = self._load_queue()
        coverage = []
        for e in entries:
            if e.get("status") not in ("done", "failed"):
                continue
            coverage.append({
                "site":          e.get("site_key"),
                "steps":         e.get("last_steps") or 0,
                "hypotheses":    e.get("last_hypotheses") or 0,
                "quality":       e.get("avg_quality_score", 0.0),
                "attempts":      e.get("attempts", 0),
                "run_count":     len(e.get("run_history") or []),
            })
        coverage.sort(key=lambda x: x["steps"], reverse=True)
        return {
            "top_sites_by_steps": coverage[:20],
            "total_explored_sites": len(coverage),
        }

    def cross_site_summary(self, min_sites: int = 3) -> Dict[str, Any]:
        """Cross-site hypothesis synthesis via CapabilityHypothesisStore (#37)."""
        try:
            from browsermind_core.learning.capability_hypothesis_store import CapabilityHypothesisStore
            store = CapabilityHypothesisStore(root=self._store_dir)
            return store.cross_site_summary(min_sites=min_sites)
        except Exception as exc:
            return {"error": str(exc), "total_cross_site": 0, "top_patterns": []}

    def summary(self) -> str:
        """Human-readable corpus summary for `bm corpus stats`."""
        q  = self.queue_summary()
        h  = self.hypothesis_summary()
        f  = self.freshness_summary()
        cv = self.site_coverage_summary()
        cs = self.cross_site_summary()

        lines = [
            "",
            "  ═══════════════════════════════════════════",
            "  BrowserMind Corpus Statistics",
            "  ═══════════════════════════════════════════",
            "",
            f"  Queue Entries    : {q['total_entries']}",
        ]
        for status, count in q["by_status"].items():
            lines.append(f"    {status:<12} : {count}")

        lines += [
            "",
            f"  Total Steps      : {q['total_steps']}",
            f"  Total Hypotheses : {q['total_hypotheses']}",
            f"  Avg Quality Score: {q['avg_quality_score']:.3f}",
            "",
            f"  Hypotheses       : {h['total_hypotheses']}",
        ]
        for fam, cnt in sorted(h["by_family"].items(), key=lambda x: -x[1])[:8]:
            lines.append(f"    {fam:<20} : {cnt}")

        lines += [
            "",
            "  Freshness (last run):",
        ]
        for bucket, cnt in f["by_age"].items():
            lines.append(f"    {bucket:<8} : {cnt}")

        lines += [
            "",
            f"  Sites Explored   : {cv['total_explored_sites']}",
            "  Top Sites by Steps:",
        ]
        for s in cv["top_sites_by_steps"][:10]:
            lines.append(
                f"    {s['site']:<24} steps={s['steps']:<5}"
                f" hyps={s['hypotheses']:<4}"
                f" quality={s['quality']:.2f}"
            )
        lines += [
            "",
            f"  Cross-Site Patterns (≥3 sites): {cs.get('total_cross_site', 0)}",
        ]
        for pat in cs.get("top_patterns", [])[:5]:
            inv = ", ".join(pat.get("invariants", [])[:3])
            lines.append(
                f"    [{pat.get('sites', 0)}s/{pat.get('frequency', 0)}f] {inv}"
            )
        lines.append("  ═══════════════════════════════════════════")
        lines.append("")
        return "\n".join(lines)
