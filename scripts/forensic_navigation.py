"""
forensic_navigation.py

For each site that failed with TARGET_CHANGED at step 2, inspect:
  1. What page does the recorder actually start on?
  2. What page does the replay engine start on?
  3. Is the failing element present on the replay start page?

This determines whether the failure is a missing navigation step
(recorder bug) or a genuine target-changed failure.
"""
import asyncio
from playwright.async_api import async_playwright

CHECKS = [
    {
        "site": "aria_internet",
        "replay_start_url": "https://the-internet.herokuapp.com/",
        "role": "textbox",
        "name": "Username",
        "notes": "Recorder navigated to /login; replay starts at homepage",
    },
    {
        "site": "github",
        "replay_start_url": "https://github.com/",
        "role": "span",
        "name": "Issues",
        "notes": "Recorder navigated to microsoft/playwright repo; replay starts at homepage",
    },
    {
        "site": "huggingface",
        "replay_start_url": "https://huggingface.co/",
        "role": "input",
        "name": "Filter by name",
        "notes": "Recorder navigated to /models; replay starts at homepage",
    },
]

async def check_element(page, role, name):
    """Return count via get_by_role (exact and partial)."""
    try:
        exact = await page.get_by_role(role, name=name, exact=True).count()
    except Exception:
        exact = -1
    try:
        partial = await page.get_by_role(role, name=name, exact=False).count()
    except Exception:
        partial = -1
    return exact, partial

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for check in CHECKS:
            page = await browser.new_page()
            print(f"\n{'='*60}")
            print(f"  SITE: {check['site']}")
            print(f"  Notes: {check['notes']}")
            print(f"  Replay start URL: {check['replay_start_url']}")
            print(f"  Looking for: role='{check['role']}', name='{check['name']}'")

            await page.goto(check["replay_start_url"])
            await page.wait_for_load_state("networkidle")

            exact, partial = await check_element(page, check["role"], check["name"])
            print(f"  On replay start page:")
            print(f"    get_by_role exact  = {exact}")
            print(f"    get_by_role partial = {partial}")

            if exact == 0 and partial == 0:
                print(f"  VERDICT: MISSING NAVIGATION STEP")
                print(f"    The element does not exist on the start page.")
                print(f"    The recorder captured sub-page actions without")
                print(f"    recording the navigation to that sub-page.")
                print(f"    Classification: MISSING_NAV_STEP (recorder gap)")
            else:
                print(f"  VERDICT: Element present on start page.")
                print(f"    This is a genuine TARGET_CHANGED -- element changed.")

            await page.close()

        await browser.close()

asyncio.run(main())
