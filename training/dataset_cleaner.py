"""
BrowserMind — Dataset Cleaner + Quality Filter
================================================
بياخد sessions خام ويطلع منها داتا نضيفة بس.

المشاكل اللي بيحلها:
  1. Samples فيها success=False → ترميها
  2. Samples مفيهاش target_text ولا target_selector → ترميها
  3. Elements list فاضية → ترميها
  4. Duplicate states في نفس الـ session → تحتفظ بواحدة
  5. Sessions قصيرة جداً (< min_steps) → ترمي السيشن كلها

Output:
  - cleaned_sessions/ directory
  - quality_report.json
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DatasetCleaner:

    def __init__(
        self,
        input_dir:  str = "training/sessions",
        output_dir: str = "training/cleaned_sessions",
        min_steps:  int = 2,     # أقل عدد steps في session مقبولة
        min_success_rate: float = 0.3,  # على الأقل 30% من steps ناجحين
    ):
        self.input_dir  = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.min_steps        = min_steps
        self.min_success_rate = min_success_rate

        # Stats
        self.stats = {
            "sessions_read":      0,
            "sessions_kept":      0,
            "sessions_dropped":   0,
            "samples_read":       0,
            "samples_kept":       0,
            "samples_dropped":    0,
            "drop_reasons":       {},
        }

    # ── Public API ──────────────────────────────────────────────────────────

    def clean_all(self) -> Dict:
        """
        يقرأ كل sessions من input_dir
        ويكتب النضيفة في output_dir
        ويرجع quality report
        """
        session_files = list(self.input_dir.glob("*.json"))
        if not session_files:
            print(f"⚠️  No sessions found in {self.input_dir}")
            return self.stats

        print(f"\n{'='*50}")
        print(f"  Dataset Cleaner")
        print(f"  Input : {len(session_files)} sessions")
        print(f"{'='*50}")

        for sf in sorted(session_files):
            self._process_session(sf)

        self._save_report()
        self._print_report()
        return self.stats

    # ── Session Processing ──────────────────────────────────────────────────

    def _process_session(self, path: Path):
        self.stats["sessions_read"] += 1

        try:
            with open(path, encoding="utf-8") as f:
                session = json.load(f)
        except Exception as e:
            self._drop_session(path.name, f"parse_error: {e}")
            return

        raw_samples = session.get("samples", [])
        self.stats["samples_read"] += len(raw_samples)

        # Clean samples
        clean_samples = []
        seen_states   = set()

        for sample in raw_samples:
            ok, reason = self._is_valid_sample(sample)
            if not ok:
                self._drop_sample(reason)
                continue

            # Dedup: same state seen before in this session?
            state_hash = self._hash_state(sample["state"])
            if state_hash in seen_states:
                self._drop_sample("duplicate_state")
                continue
            seen_states.add(state_hash)

            clean_samples.append(sample)

        # Session-level checks
        if len(clean_samples) < self.min_steps:
            self._drop_session(path.name, f"too_few_steps:{len(clean_samples)}")
            return

        success_count = sum(1 for s in clean_samples if s.get("success", False))
        success_rate  = success_count / len(clean_samples)
        if success_rate < self.min_success_rate:
            self._drop_session(path.name, f"low_success_rate:{success_rate:.0%}")
            return

        # Write cleaned session
        cleaned = dict(session)
        cleaned["samples"]     = clean_samples
        cleaned["total_steps"] = len(clean_samples)
        cleaned["cleaned"]     = True

        out_path = self.output_dir / path.name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)

        self.stats["sessions_kept"]  += 1
        self.stats["samples_kept"]   += len(clean_samples)

    # ── Sample Validation ───────────────────────────────────────────────────

    def _is_valid_sample(self, sample: Dict) -> Tuple[bool, str]:
        # Must have succeeded
        if not sample.get("success", False):
            return False, "success_false"

        # Must have elements
        elements = sample.get("state", {}).get("elements", [])
        if not elements:
            return False, "no_elements"

        # Must have some action grounding
        action = sample.get("action", {})
        has_text     = bool((action.get("target_text") or "").strip())
        has_selector = bool((action.get("target_selector") or "").strip())
        if not has_text and not has_selector:
            # scroll and go_back don't need a target — allow them
            act_type = action.get("action_type", "")
            if act_type not in ("scroll", "go_back", "wait", "open_url"):
                return False, "no_grounding"

        # Must have a goal
        if not action.get("goal", "").strip():
            return False, "no_goal"

        return True, ""

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _hash_state(self, state: Dict) -> str:
        els   = state.get("elements", [])
        url   = state.get("page_url", "")
        key   = url + "|" + "|".join(
            f"{e.get('tag')}{e.get('text','')[:20]}{e.get('x')}{e.get('y')}"
            for e in els[:15]
        )
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def _drop_sample(self, reason: str):
        self.stats["samples_dropped"] += 1
        self.stats["drop_reasons"][reason] = (
            self.stats["drop_reasons"].get(reason, 0) + 1
        )

    def _drop_session(self, name: str, reason: str):
        self.stats["sessions_dropped"] += 1
        key = f"session:{reason}"
        self.stats["drop_reasons"][key] = (
            self.stats["drop_reasons"].get(key, 0) + 1
        )
        print(f"  ✗ {name:<40} {reason}")

    def _save_report(self):
        report_path = self.output_dir / "quality_report.json"
        with open(report_path, "w") as f:
            json.dump(self.stats, f, indent=2)

    def _print_report(self):
        s = self.stats
        kept_pct = s["sessions_kept"] / max(s["sessions_read"], 1) * 100
        samp_pct = s["samples_kept"]  / max(s["samples_read"],  1) * 100

        print(f"\n  Sessions : {s['sessions_kept']}/{s['sessions_read']} kept ({kept_pct:.0f}%)")
        print(f"  Samples  : {s['samples_kept']}/{s['samples_read']} kept ({samp_pct:.0f}%)")
        if s["drop_reasons"]:
            print(f"  Drop reasons:")
            for reason, count in sorted(s["drop_reasons"].items(), key=lambda x: -x[1]):
                print(f"    {count:>4}× {reason}")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    cleaner = DatasetCleaner()
    cleaner.clean_all()
