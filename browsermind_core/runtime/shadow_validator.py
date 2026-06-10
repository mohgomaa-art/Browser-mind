"""ShadowValidator — Phase 5 of R6 v1.

Append-only shadow trial log. Runs a RecoveryCandidate's primitive in
READ-ONLY mode against the current page to see whether it WOULD resolve
uniquely, without ever clicking or mutating the page. Each trial is one
JSONL row in `<store_dir>/shadow_results.jsonl`.

Best-effort: writer and primitive errors must NEVER raise into the runtime.

Format per row:
    {ts, candidate_id, step_id, persona, env, primitive,
     matched, would_resolve, candidate_count,
     live_resolver_succeeded, error}
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from browsermind_core.runtime.primitive_library import get_primitive


_FILE_NAME = "shadow_results.jsonl"
_ERROR_TRUNC = 500


class ShadowValidator:
    """Append-only shadow trial log. One file per store_dir at
    <store_dir>/shadow_results.jsonl."""

    _lock = threading.Lock()

    def __init__(self, store_dir: Optional[str] = None):
        base = Path(store_dir) if store_dir else (Path.home() / ".browsermind")
        self.path = base / _FILE_NAME

    async def shadow_trial(
        self,
        *,
        candidate,                          # RecoveryCandidate
        page,                               # Playwright Page
        descriptor: Dict[str, Any],
        feature_vector: Dict[str, Any],
        step_id: str = "",
        persona: str = "",
        env: str = "",
        live_resolver_succeeded: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Run candidate.primitive in READ-ONLY mode. Never clicks, never
        mutates. Appends a row to shadow_results.jsonl and returns it."""
        primitive_name = getattr(candidate, "primitive", "") or ""
        candidate_id = str(getattr(candidate, "id", "") or "")

        would_resolve = False
        candidate_count = 0
        error: Optional[str] = None

        try:
            fn = get_primitive(primitive_name)
            if fn is None:
                error = f"unknown primitive: {primitive_name}"
            else:
                # READ-ONLY: only call .count() on the returned Locator.
                loc = await fn(page, descriptor or {}, resolver=None, read_only=True)
                if loc is None:
                    candidate_count = 0
                    would_resolve = False
                else:
                    try:
                        candidate_count = int(await loc.count())
                    except Exception as count_err:
                        candidate_count = 0
                        error = ("count_error: " + str(count_err))[:_ERROR_TRUNC]
                    would_resolve = candidate_count == 1
        except Exception as exc:
            error = str(exc)[:_ERROR_TRUNC]

        row: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate_id,
            "step_id": step_id or "",
            "persona": persona or "",
            "env": env or "",
            "primitive": primitive_name,
            "matched": True,            # caller guarantees predicate match
            "would_resolve": bool(would_resolve),
            "candidate_count": int(candidate_count),
            "live_resolver_succeeded": live_resolver_succeeded,
            "error": error,
        }

        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Writer must not break the runtime.

        return row

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        """Read last N lines of shadow_results.jsonl."""
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []
        return out[-n:]

    def aggregate(self, candidate_id: str) -> Dict[str, Any]:
        """Compute {n_trials, n_would_resolve, would_resolve_rate} for one
        candidate. Returns empty defaults on absent file or no matches."""
        defaults = {"n_trials": 0, "n_would_resolve": 0, "would_resolve_rate": 0.0}
        if not self.path.exists():
            return defaults
        n_trials = 0
        n_would_resolve = 0
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(row.get("candidate_id") or "") != str(candidate_id):
                        continue
                    n_trials += 1
                    if bool(row.get("would_resolve")):
                        n_would_resolve += 1
        except Exception:
            return defaults
        rate = (n_would_resolve / n_trials) if n_trials else 0.0
        return {
            "n_trials": n_trials,
            "n_would_resolve": n_would_resolve,
            "would_resolve_rate": round(rate, 4),
        }
