"""CLI for the BC training-data unification layer.

    python -m browsermind_core.training.cli extract \
        --store ~/.browsermind \
        --out training/episodes/bc_v1.jsonl

Reads OutcomeLedger step records from the persistence store, writes one JSONL
line per step attempt, and prints a small summary of the result.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from browsermind_core.training.episode_extractor import (
    extract_bc_episodes_from_repository,
    summarize,
    write_jsonl,
)


def _expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def _cmd_extract(args: argparse.Namespace) -> int:
    store = _expand(args.store)
    out = _expand(args.out)
    sites = list(args.site) if args.site else None

    if not Path(store).exists():
        # Empty/missing store is a valid input: report 0 episodes, do not crash.
        Path(store).mkdir(parents=True, exist_ok=True)

    episodes = extract_bc_episodes_from_repository(
        store, success_only=not args.include_failures, sites=sites
    )
    write_jsonl(episodes, out)
    summary = summarize(episodes)
    summary["store"] = store
    summary["out"] = str(Path(out))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m browsermind_core.training.cli",
        description="Unified BC training-data layer (OutcomeLedger -> JSONL).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="Extract BC episodes from the OutcomeLedger.")
    extract.add_argument("--store", required=True, help="Persistence store dir.")
    extract.add_argument("--out", required=True, help="Output JSONL path.")
    extract.add_argument(
        "--site",
        action="append",
        default=None,
        help="Filter by environment_instance (repeatable).",
    )
    extract.add_argument(
        "--include-failures",
        action="store_true",
        help="Keep failure attempts (default: success_only=True).",
    )
    extract.set_defaults(func=_cmd_extract)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
