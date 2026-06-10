"""
Scrub sensitive values from BrowserMind training session JSON files.

This script is safe to run before training on authenticated social sessions.
It redacts passwords/tokens/emails/identity strings from goal/action/state/graph
without changing action IDs or graph structure.

Usage:
  python scripts/scrub_training_secrets.py --dry-run
  python scripts/scrub_training_secrets.py --apply
  python scripts/scrub_training_secrets.py --apply --paths training/massive_sessions training/sessions
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure repository root is importable when running this file directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.privacy import (
    redact_sensitive_text,
    sanitize_expert_action,
    sanitize_goal_for_storage,
    sanitize_graph_for_storage,
    sanitize_state_for_storage,
    sanitize_typed_text,
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sanitize_old_format_session(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    out["goal"] = sanitize_goal_for_storage(str(out.get("goal", "")))

    samples = out.get("samples")
    if not isinstance(samples, list):
        return out

    safe_samples: List[Dict[str, Any]] = []
    for s in samples:
        if not isinstance(s, dict):
            continue

        safe = dict(s)

        state = safe.get("state", {})
        if isinstance(state, dict):
            safe["state"] = sanitize_state_for_storage(state)

        action = safe.get("action", {})
        if isinstance(action, dict):
            act = dict(action)
            target_text = str(act.get("target_text", ""))
            typed_text = str(act.get("typed_text", ""))
            goal_text = str(act.get("goal", out.get("goal", "")))
            act["goal"] = sanitize_goal_for_storage(goal_text)
            act["target_text"] = redact_sensitive_text(target_text)
            act["target_selector"] = redact_sensitive_text(str(act.get("target_selector", "")))
            if typed_text:
                act["typed_text"] = sanitize_typed_text(typed_text, target_text=target_text, goal_text=goal_text)
            safe["action"] = act

        safe_samples.append(safe)

    out["samples"] = safe_samples
    return out


def _sanitize_spec_sample(s: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(s)
    goal = sanitize_goal_for_storage(str(safe.get("goal", "")))
    safe["goal"] = goal
    safe["url"] = redact_sensitive_text(str(safe.get("url", "")))

    graph = safe.get("graph", {})
    if isinstance(graph, dict):
        safe["graph"] = sanitize_graph_for_storage(graph)

    expert = safe.get("expert_action", {})
    if isinstance(expert, dict):
        safe["expert_action"] = sanitize_expert_action(expert, goal_text=goal)

    state = safe.get("state", {})
    if isinstance(state, dict):
        safe["state"] = sanitize_state_for_storage(state)

    return safe


def _sanitize_doc(doc: Any) -> Any:
    if isinstance(doc, dict) and isinstance(doc.get("samples"), list):
        return _sanitize_old_format_session(doc)

    if isinstance(doc, list):
        out: List[Any] = []
        for item in doc:
            if isinstance(item, dict):
                out.append(_sanitize_spec_sample(item))
            else:
                out.append(item)
        return out

    if isinstance(doc, dict):
        return _sanitize_spec_sample(doc)

    return doc


def _json_equal(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)
    except Exception:
        return False


def scrub_paths(paths: List[Path], apply: bool) -> Tuple[int, int, int]:
    files_scanned = 0
    files_changed = 0
    files_failed = 0

    for base in paths:
        if not base.exists():
            continue

        if base.is_file() and base.suffix.lower() == ".json":
            candidates = [base]
        else:
            candidates = list(base.rglob("*.json"))

        for fp in candidates:
            files_scanned += 1
            src = _load_json(fp)
            if src is None:
                files_failed += 1
                continue

            safe = _sanitize_doc(src)
            if _json_equal(src, safe):
                continue

            files_changed += 1
            if apply:
                fp.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")

    return files_scanned, files_changed, files_failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrub secrets from BrowserMind training data JSON files")
    parser.add_argument("--paths", nargs="*", default=["training/sessions", "training/massive_sessions", "training/spec_sessions"])
    parser.add_argument("--apply", action="store_true", help="Write sanitized changes to disk")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    apply = bool(args.apply and not args.dry_run)
    bases = [Path(p) for p in args.paths]
    scanned, changed, failed = scrub_paths(bases, apply=apply)

    mode = "APPLY" if apply else "DRY_RUN"
    print(f"[{mode}] scanned={scanned} changed={changed} failed={failed}")
    if not apply:
        print("[INFO] Re-run with --apply to write sanitized files.")


if __name__ == "__main__":
    main()
