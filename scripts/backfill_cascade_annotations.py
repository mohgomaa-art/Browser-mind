"""Backfill cascade annotations for historical OutcomeRecord files.

Reads every OutcomeRecord JSON under ~/.browsermind/outcome_ledger/.
For each record missing cascade_layer, computes annotation using
cascade.annotate() and rewrites atomically (tmp + replace).

Usage:
    python scripts/backfill_cascade_annotations.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import tempfile


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(pathlib.Path.home() / ".browsermind"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Re-annotate even if already annotated")
    args = ap.parse_args()

    from browsermind_core.ledger.cascade import workflow_class_for, cascade_layer_for

    ledger_dir = pathlib.Path(args.store) / "outcome_ledger"
    if not ledger_dir.exists():
        print(f"[backfill] No outcome_ledger at {ledger_dir}")
        return

    files = sorted(ledger_dir.glob("*.json"))
    total = len(files)
    already = 0
    patched = 0
    skipped = 0

    for fpath in files:
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [SKIP] {fpath.name}: read error: {e}")
            skipped += 1
            continue

        metrics = data.get("metrics") or {}
        if "cascade_layer" in metrics and not args.force:
            already += 1
            continue

        # Records are wrapped: outer = {_checksum, _data, metrics}
        # Cascade annotations live on the outer 'metrics' but the
        # scope/template/env fields live inside '_data'.
        inner = data.get("_data") or {}
        scope = inner.get("scope", "")
        inner_metrics = inner.get("metrics") or {}
        template_name = inner_metrics.get("template_name", "")
        env_instance = (
            inner.get("environment_instance", "")
            or inner_metrics.get("environment_instance", "")
        )

        layer = cascade_layer_for(scope)
        cls = workflow_class_for(template_name, env_instance)

        metrics["cascade_layer"] = layer
        metrics["cascade_workflow_class"] = cls
        metrics["cascade_proxy_for"] = None
        data["metrics"] = metrics

        if args.dry_run:
            patched += 1
            continue

        dir_ = fpath.parent
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8",
                dir=dir_, suffix=".tmp", delete=False
            ) as tf:
                json.dump(data, tf, indent=2)
                tmp_path = tf.name
            os.replace(tmp_path, str(fpath))
            patched += 1
        except Exception as e:
            print(f"  [SKIP] {fpath.name}: write error: {e}")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            skipped += 1

    print(f"[backfill] total={total} already={already} patched={patched} skipped={skipped}"
          + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
