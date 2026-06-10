#!/usr/bin/env python3
"""
P1 proof: WorkflowInstance run -> Mutation Ledger -> Outcome -> survives restart.

Browser: Option B -- isolated Chromium profile (human logs in once).
  Profile dir: ~/.browsermind/profiles/<family_key>/

Usage:
  # 1) Warm profile (manual login once)
  python scripts/run_workflow_pilot.py --login-only

  # 2) Run scripted login + ledger proof
  python scripts/run_workflow_pilot.py

  # 3) Verify persistence in a new process
  python -m browsermind_core.console ledger tail --n 25
  python -m browsermind_core.console outcome list
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import DEFAULT_STORE, KernelSession
from browsermind_core.pilot.kernel_bridge import PilotKernelBridge
from browsermind_core.runtime.environment_config import get_instance

SAUCEDEMO_USER = "standard_user"
SAUCEDEMO_PASS = "secret_sauce"
INVENTORY_PATH = "/inventory.html"


def _parse_args():
    p = argparse.ArgumentParser(description="BrowserMind P1 workflow pilot (saucedemo)")
    p.add_argument("--store", default=DEFAULT_STORE, help="Kernel store (~/.browsermind)")
    p.add_argument("--env", default="saucedemo", help="Environment instance key")
    p.add_argument("--persona", default="pilot", help="Persona name")
    p.add_argument("--login-only", action="store_true", help="Open profile for manual login only")
    p.add_argument("--headless", action="store_true", help="Headless Chromium (default: headful)")
    p.add_argument("--kernel-only", action="store_true", help="Skip browser; emit kernel ledger only (CI)")
    return p.parse_args()


async def _open_profile(env_key: str, store: str, headless: bool, login_only: bool, persona: str = "pilot"):
    from playwright.async_api import async_playwright

    env = get_instance(env_key)
    profile_dir = env.profile_dir(Path(store), persona_name=persona)
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(env.start_url, wait_until="domcontentloaded")

        if login_only:
            print(f"\n  Profile: {profile_dir}")
            print(f"  URL:     {env.start_url}")
            print("\n  Log in manually in the browser window.")
            print("  Press Enter here when done (browser will close).\n")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await context.close()
            print(f"  Saved session under {profile_dir}")
            return

        await context.close()


async def _run_saucedemo_login(store: str, env_key: str, persona: str, headless: bool):
    from playwright.async_api import async_playwright

    env = get_instance(env_key)
    profile_dir = env.profile_dir(Path(store), persona_name=persona)
    profile_dir.mkdir(parents=True, exist_ok=True)

    session = KernelSession(store)
    bridge = PilotKernelBridge(session, env)
    bridge.bootstrap_persona(persona)
    bridge.register_workflow_binding()
    bridge.create_task(
        goal="P1 saucedemo login smoke",
        task_index_name="pilot_login",
        persona_name=persona,
    )
    bridge.start_execution(persona_name=persona)
    bridge.checkpoint_pause_resume()
    bridge.pilot_step("execution_started", {"profile_dir": str(profile_dir)})

    success = False
    evidence = ""

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        bridge.pilot_step("browser_launch")
        await page.goto(env.start_url, wait_until="domcontentloaded")
        bridge.pilot_step("navigate_home", {"url": page.url})

        await page.locator("#user-name").wait_for(state="visible", timeout=15_000)
        bridge.pilot_step("login_form_visible")

        await page.fill("#user-name", SAUCEDEMO_USER)
        bridge.pilot_step("fill_username")
        await page.fill("#password", SAUCEDEMO_PASS)
        bridge.pilot_step("fill_password")
        await page.click("#login-button")
        bridge.pilot_step("click_login")

        try:
            await page.wait_for_url(f"**{INVENTORY_PATH}", timeout=15_000)
            bridge.pilot_step("url_inventory")
        except Exception as e:
            bridge.pilot_step("url_wait_failed", {"error": str(e)})

        err = page.locator("[data-test='error']")
        if await err.count() > 0 and await err.is_visible():
            msg = (await err.inner_text()).strip()
            bridge.pilot_step("error_banner", {"message": msg})
            evidence = f"Login error banner: {msg}"
            success = False
        elif INVENTORY_PATH in page.url:
            title = await page.title()
            bridge.pilot_step("inventory_loaded", {"title": title, "url": page.url})
            items = await page.locator(".inventory_item").count()
            bridge.pilot_step("inventory_count", {"items": items})
            success = items > 0
            evidence = f"Landed on {page.url} - {items} inventory items, title={title!r}"
        else:
            evidence = f"Unexpected URL after login: {page.url}"
            bridge.pilot_step("unexpected_url", {"url": page.url})

        bridge.pilot_step("screenshot_skipped", {"note": "P1 uses URL+DOM evidence"})
        await context.close()
        bridge.pilot_step("browser_closed")

    bridge.complete_execution(success=success, persona_name=persona)
    bridge.pilot_step("execution_completed", {"success": success})
    outcome = bridge.record_outcome(
        success=success,
        evidence=evidence or ("Login failed" if not success else "OK"),
        outcome_type="login_succeeded" if success else "login_failed",
    )

    n_mut = bridge.mutation_count()
    n_out = session.outcome_repo.count()
    print("\n=== P1 Pilot Complete ===")
    print(f"  Execution:  {bridge.execution_id}")
    print(f"  Success:    {success}")
    print(f"  Evidence:   {evidence}")
    print(f"  Mutations:  {n_mut} ledger entries")
    print(f"  Outcomes:   {n_out} total ({outcome.outcome_type})")
    print(f"  Profile:    {profile_dir}")
    print("\n  Verify restart:")
    print("    python -m browsermind_core.console ledger tail --n 25")
    print("    python -m browsermind_core.console outcome list")
    if n_mut < 20:
        print(f"\n  [WARN] Expected >=20 mutation entries; got {n_mut}")
    return 0 if success else 1


async def _kernel_only(store: str, env_key: str, persona: str):
    env = get_instance(env_key)
    session = KernelSession(store)
    bridge = PilotKernelBridge(session, env)
    bridge.bootstrap_persona(persona)
    bridge.register_workflow_binding()
    bridge.create_task("P1 kernel-only smoke", "pilot_login", persona_name=persona)
    bridge.start_execution(persona_name=persona)
    bridge.checkpoint_pause_resume()
    for i in range(15):
        bridge.pilot_step(f"synthetic_step_{i}", {"index": i})
    bridge.complete_execution(success=True)
    bridge.record_outcome(True, "Kernel-only path (no browser)", "login_succeeded")
    print(f"  Mutations: {bridge.mutation_count()} (kernel-only)")
    return 0


def main():
    args = _parse_args()
    if args.kernel_only:
        raise SystemExit(asyncio.run(_kernel_only(args.store, args.env, args.persona)))
    if args.login_only:
        asyncio.run(_open_profile(args.env, args.store, args.headless, login_only=True, persona=args.persona))
        return
    raise SystemExit(
        asyncio.run(_run_saucedemo_login(args.store, args.env, args.persona, args.headless))
    )


if __name__ == "__main__":
    main()
