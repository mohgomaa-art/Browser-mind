"""Report (and optionally archive) same-name same-principal persona duplicates.

Reads every Persona JSON under ~/.browsermind/persona/.
Groups by (name, principal_id). For each group with >1 member, prints
the duplicates sorted oldest-first.

Usage:
    python scripts/cleanup_persona_dupes.py [--store <path>]
    python scripts/cleanup_persona_dupes.py --show-all

Does NOT delete anything automatically.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(pathlib.Path.home() / ".browsermind"))
    ap.add_argument("--show-all", action="store_true",
                    help="Also show groups with exactly 1 member (no duplicates).")
    args = ap.parse_args()

    persona_dir = pathlib.Path(args.store) / "persona"
    if not persona_dir.exists():
        print(f"[cleanup] No persona dir at {persona_dir}")
        return

    files = sorted(persona_dir.glob("*.json"))
    personas = []
    for fpath in files:
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            # Persona records may be wrapped: {_checksum, _data, ...}
            data = raw.get("_data", raw)
            personas.append((fpath, data))
        except Exception as e:
            print(f"  [SKIP] {fpath.name}: {e}")

    groups: dict = defaultdict(list)
    for fpath, data in personas:
        key = (data.get("name", ""), str(data.get("principal_id", "")))
        groups[key].append((fpath, data))

    dupe_count = 0
    for (name, principal_id), members in sorted(groups.items()):
        if len(members) <= 1 and not args.show_all:
            continue
        marker = "[DUPE]" if len(members) > 1 else "[OK]  "
        if len(members) > 1:
            dupe_count += 1
        print(f"\n{marker} name='{name}'  principal={principal_id}  count={len(members)}")
        for fpath, data in sorted(members, key=lambda x: x[1].get("created_at", "")):
            pid = data.get("id", "?")
            ts = data.get("created_at", "unknown")
            print(f"         {pid}  created={ts}  file={fpath.name}")

    total = len(personas)
    print(f"\n[cleanup] Scanned {total} personas. Duplicate groups: {dupe_count}.")
    if dupe_count:
        print("[cleanup] To resolve: keep the oldest record per group, delete or rename the others.")
        print("[cleanup] Use 'bm persona list' to inspect before making changes.")


if __name__ == "__main__":
    main()
