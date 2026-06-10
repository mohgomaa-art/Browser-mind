#!/usr/bin/env python3
"""Headful record session (P2A) from command line / GUI prompt."""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import DEFAULT_STORE
from browsermind_core.recorder.record_runner import run_recording_session


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env", default="facebook")
    p.add_argument("--persona", default="pilot")
    p.add_argument("--store", default=DEFAULT_STORE)
    args = p.parse_args()
    session = asyncio.run(
        run_recording_session(
            args.store, args.env, args.persona, headless=False
        )
    )
    print(f"Saved demonstration {session.id} with {len(session.actions)} actions.")


if __name__ == "__main__":
    main()
