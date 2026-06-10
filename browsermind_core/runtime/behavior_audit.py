"""BehaviorAuditLog — append-only JSONL trail of prior-driven decisions.

Self-Learning v1, Loop 12 (audit trail). Records every runtime decision
that was influenced by a learned prior so failures can be explained
post-hoc. Format:

    {ts, persona, env, decision_point, prior_source, prior_version,
     picked, fallback_used}

Best-effort. Audit failures must NEVER raise into the runtime.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_DEFAULT_PATH = Path.home() / ".browsermind" / "audit" / "behavior_audit.jsonl"


class BehaviorAuditLog:
    """Append-only JSONL writer. One file per store_dir.

    Construction is lazy — the file/dir is only touched on first write.
    All writes are guarded by a lock and silently swallowed on error.
    """

    _lock = threading.Lock()

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _DEFAULT_PATH

    def record(
        self,
        *,
        persona: str = "",
        env: str = "",
        decision_point: str,
        prior_source: str,
        prior_version: str = "",
        picked: str = "",
        fallback_used: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "persona": persona or "",
            "env": env or "",
            "decision_point": decision_point,
            "prior_source": prior_source,
            "prior_version": prior_version or "",
            "picked": picked or "",
            "fallback_used": bool(fallback_used),
        }
        if extra:
            entry["extra"] = extra
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Audit must not break the runtime.

    # Convenience helpers for the two prior sources we have today.

    def memory_prior(self, *, persona: str, env: str, picked: str,
                     fallback_used: bool = False, extra: Optional[Dict] = None):
        self.record(
            persona=persona, env=env,
            decision_point="target_resolver.memory_prior",
            prior_source="procedural_memory",
            prior_version="v1",
            picked=picked, fallback_used=fallback_used, extra=extra,
        )

    def lesson_prior(self, *, persona: str, env: str, picked: str,
                     fallback_used: bool = False, extra: Optional[Dict] = None):
        self.record(
            persona=persona, env=env,
            decision_point="target_resolver.lesson_prior",
            prior_source="lessons.jsonl",
            prior_version="v1",
            picked=picked, fallback_used=fallback_used, extra=extra,
        )

    # Read helper for tests / forensics.
    def tail(self, n: int = 50):
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out[-n:]
