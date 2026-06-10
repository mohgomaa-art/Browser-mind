#!/usr/bin/env python3
"""Open a headful browser session for a registered environment."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import DEFAULT_STORE
from browsermind_core.runtime.environment_registry import resolve, get_all
from browsermind_core.runtime.auth_session import AuthSession


async def main_async(env_key: str, url: str | None, store: str, persona: str, headless: bool):
    entry = resolve(env_key)
    if entry is None:
        known = ", ".join(e.key for e in get_all())
        print(f"\n  [ERROR] Unknown environment: '{env_key}'")
        print(f"  Known environments: {known}")
        print(f"  To add a new one: bm environment add --key mysite --url https://mysite.com")
        sys.exit(1)

    session = AuthSession(
        entry=entry,
        persona_name=persona,
        store_dir=Path(store),
        headless=headless,
    )

    initialized = session.is_profile_initialized()
    if initialized:
        print(f"\n  Auth state found -- restoring session for [{persona}] on [{entry.key}]")
    else:
        print(f"\n  No prior auth state -- fresh session for [{persona}] on [{entry.key}]")
        print(f"  Log in manually. Close the browser when done.")

    await session.open(url)
    print("\n  Press Enter to close the browser and save session...")
    await asyncio.get_event_loop().run_in_executor(None, input)
    await session.close()


def main():
    p = argparse.ArgumentParser(description="Open a headful browser for a registered environment")
    p.add_argument("--env", default="huggingface", help="Environment key (huggingface, linkedin, github...)")
    p.add_argument("--url", default=None, help="Override start URL")
    p.add_argument("--store", default=DEFAULT_STORE)
    p.add_argument("--persona", default="pilot")
    p.add_argument("--headless", action="store_true")
    args = p.parse_args()
    asyncio.run(main_async(args.env, args.url, args.store, args.persona, args.headless))


if __name__ == "__main__":
    main()
