"""bm mission — CLI commands for the autonomous exploration mission runtime."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click


# ── Group ─────────────────────────────────────────────────────────────────────

@click.group("mission", short_help="Autonomous site exploration missions")
def mission_group():
    """
    Run autonomous exploration missions across many sites.

    \b
    Quick start:
      bm mission add github --budget 200
      bm mission add reddit --budget 200 --tag social
      bm mission add-bulk --file sites.txt --budget 200
      bm mission run --hours 8
      bm mission status
    """


# ── bm mission add ────────────────────────────────────────────────────────────

@mission_group.command("add")
@click.argument("site_key")
@click.option("--persona", default="validator", show_default=True)
@click.option("--budget", default=200, show_default=True, type=int)
@click.option("--tag", "tags", multiple=True, help="Tags (repeatable): --tag social --tag forum")
@click.option("--retries", default=2, show_default=True, type=int)
@click.pass_context
def mission_add(ctx, site_key, persona, budget, tags, retries):
    """Add a site to the mission queue."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)
    entry = queue.add(site_key, persona=persona, budget=budget,
                      tags=list(tags), max_retries=retries)
    if entry.attempts == 0 and entry.status == "pending":
        click.echo(click.style("[OK] ", fg="green") + f"Added '{site_key}' to mission queue  [{entry.id[:8]}…]")
    else:
        click.echo(click.style("[INFO] ", fg="yellow") + f"'{site_key}' already queued (status={entry.status})")


# ── bm mission add-bulk ───────────────────────────────────────────────────────

@mission_group.command("add-bulk")
@click.option("--file", "file_path", type=click.Path(exists=True),
              help="Text file — one site_key per line (lines starting with # are skipped).")
@click.option("--persona", default="validator", show_default=True)
@click.option("--budget", default=200, show_default=True, type=int)
@click.option("--tag", "tags", multiple=True)
@click.option("--retries", default=2, show_default=True, type=int)
@click.pass_context
def mission_add_bulk(ctx, file_path, persona, budget, tags, retries):
    """Add many sites from a text file (one site_key per line)."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE

    if not file_path:
        click.echo(click.style("[ERR] ", fg="red") + "Provide --file <path>", err=True)
        sys.exit(1)

    lines = Path(file_path).read_text(encoding="utf-8").splitlines()
    site_keys = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not site_keys:
        click.echo(click.style("[WARN] ", fg="yellow") + "No site keys found in file.")
        return

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)
    added = queue.add_bulk(site_keys, persona=persona, budget=budget,
                           tags=list(tags), max_retries=retries)
    click.echo(
        click.style("[OK] ", fg="green")
        + f"Added {added}/{len(site_keys)} sites to mission queue"
        + (f"  ({len(site_keys)-added} already queued)" if added < len(site_keys) else "")
    )


# ── bm mission status ─────────────────────────────────────────────────────────

@mission_group.command("status")
@click.pass_context
def mission_status(ctx):
    """Show mission queue summary (counts by status)."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)
    counts = queue.counts()
    total = queue.total()

    click.echo()
    click.echo(click.style("  Mission Queue", bold=True))
    click.echo(f"  {'Total':12} {total}")
    click.echo()
    for status, count in counts.items():
        if count == 0:
            continue
        colour = {
            "pending":  "cyan",
            "running":  "yellow",
            "done":     "green",
            "failed":   "red",
            "paused":   "magenta",
            "skipped":  "white",
        }.get(status, "white")
        bar = "█" * min(count, 40)
        click.echo(f"  {status:<12} {click.style(str(count).rjust(5), fg=colour)}  {bar}")
    click.echo()


# ── bm mission ls ─────────────────────────────────────────────────────────────

@mission_group.command("ls")
@click.option("--status", default=None,
              type=click.Choice(["pending", "running", "done", "failed", "paused", "skipped"]))
@click.option("--limit", default=50, show_default=True, type=int)
@click.pass_context
def mission_ls(ctx, status, limit):
    """List mission queue entries."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE
    import time as _time

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)
    entries = queue.list_entries(status=status)[:limit]

    if not entries:
        click.echo(click.style("  (empty)", dim=True))
        return

    click.echo()
    header = f"  {'SITE':<28}  {'STATUS':<10}  {'STEPS':<7}  {'HYPS':<6}  {'ATTEMPTS':<9}  LAST_ERROR"
    click.echo(click.style(header, bold=True))
    click.echo("  " + "-" * 75)

    for e in entries:
        colour = {
            "pending": "cyan", "running": "yellow", "done": "green",
            "failed": "red", "paused": "magenta", "skipped": "white",
        }.get(e.status, "white")
        error_preview = (e.last_error or "")[:30]
        click.echo(
            f"  {e.site_key:<28}  "
            + click.style(f"{e.status:<10}", fg=colour)
            + f"  {str(e.last_steps or ''):<7}  "
            + f"{str(e.last_hypotheses or ''):<6}  "
            + f"{e.attempts}/{e.max_retries:<6}    "
            + f"{error_preview}"
        )
    click.echo()


# ── bm mission resume ─────────────────────────────────────────────────────────

@mission_group.command("resume")
@click.argument("site_key")
@click.pass_context
def mission_resume(ctx, site_key):
    """Mark a paused mission entry as pending (re-queue for next run)."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)

    if queue.resume(site_key):
        click.echo(click.style("[OK] ", fg="green") + f"'{site_key}' re-queued as pending.")
    else:
        click.echo(click.style("[WARN] ", fg="yellow") + f"No paused entry found for '{site_key}'.")


# ── bm mission clear ──────────────────────────────────────────────────────────

@mission_group.command("clear")
@click.option("--status", required=True,
              type=click.Choice(["done", "failed", "paused", "skipped"]),
              help="Remove all entries with this status.")
@click.confirmation_option(prompt="This will permanently remove entries. Continue?")
@click.pass_context
def mission_clear(ctx, status):
    """Remove all entries with a given status from the queue."""
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)
    removed = queue.clear(status)
    click.echo(click.style("[OK] ", fg="green") + f"Removed {removed} '{status}' entries.")


# ── bm mission run ────────────────────────────────────────────────────────────

@mission_group.command("run")
@click.option("--hours", default=None, type=float,
              help="Stop after N hours (e.g. --hours 8). Default: run until queue is empty.")
@click.option("--max-sites", default=None, type=int,
              help="Stop after N sites are processed.")
@click.option("--headless", is_flag=True, default=False,
              help="Run browser headless (no visible window). Default: visible for human takeover.")
@click.option("--delay", default=3.0, show_default=True, type=float,
              help="Seconds to pause between sites.")
@click.option("--persona", default="validator", show_default=True,
              help="Default persona when not specified per-entry.")
@click.pass_context
def mission_run(ctx, hours, max_sites, headless, delay, persona):
    """
    Start the mission worker — runs sites from the queue continuously.

    \b
    Examples:
      bm mission run                    # drain queue, visible browser
      bm mission run --hours 8          # run for 8 hours
      bm mission run --headless         # no browser window
      bm mission run --max-sites 10     # process at most 10 sites

    When a bot wall or auth gate is hit, the site is marked PAUSED and the
    worker moves on. Run `bm mission resume <site_key>` after resolving it.
    """
    from browsermind_core.mission.mission_queue import MissionQueue
    from browsermind_core.mission.mission_worker import MissionWorker
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    queue = MissionQueue(store_dir)

    counts = queue.counts()
    pending = counts.get("pending", 0)
    if pending == 0:
        click.echo(click.style("[WARN] ", fg="yellow") + "No pending missions. Add some with: bm mission add <site_key>")
        return

    time_label = f"{hours}h" if hours else "∞"
    sites_label = str(max_sites) if max_sites else "∞"
    click.echo(
        f"\n  Starting MissionWorker:"
        f" pending={pending}  time={time_label}  max_sites={sites_label}"
        f"  headless={headless}\n"
    )

    def on_start(entry):
        pass  # header printed by worker

    def on_done(entry):
        pass  # result printed by worker

    worker = MissionWorker(
        queue=queue,
        session=s,
        headless=headless,
        store_dir=store_dir,
        on_site_start=on_start,
        on_site_done=on_done,
        inter_site_delay=delay,
    )

    # Graceful Ctrl-C
    import signal as _signal

    def _handle_sigint(*_):
        click.echo("\n  [MissionWorker] Interrupt received — stopping after current site...")
        worker.stop()

    try:
        _signal.signal(_signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        pass  # signal() only works on main thread

    summary = asyncio.run(worker.run(hours=hours, max_sites=max_sites))

    click.echo()
    click.echo("=" * 50)
    click.echo("MISSION SUMMARY")
    click.echo("=" * 50)
    click.echo(f"  Sites processed      : {summary['sites_done']}")
    click.echo(f"  Total steps          : {summary['total_steps']}")
    click.echo(f"  Novel hypotheses     : {summary['total_hypotheses']}")
    click.echo(f"  Affordances executed : {summary.get('total_affordances_exec', 0)}")
    click.echo(f"  Verified effects     : {summary.get('total_verified_effects', 0)}")

    final_counts = queue.counts()
    click.echo()
    for st, cnt in final_counts.items():
        if cnt:
            click.echo(f"  {st:<12} {cnt}")
    click.echo()


# ── bm mission intervene ──────────────────────────────────────────────────────

@mission_group.command("intervene")
@click.argument("site_key")
@click.option("--persona", default="validator", show_default=True,
              help="Persona whose session profile will be saved.")
@click.pass_context
def mission_intervene(ctx, site_key, persona):
    """
    Open a visible browser for manual intervention on a paused site.

    \b
    Use this when a site is stuck due to:
      - Login / authentication wall
      - CAPTCHA / Cloudflare challenge
      - Email / SMS / MFA verification
      - Any other manual step BrowserMind cannot automate

    \b
    The command will:
      1. Resolve the site URL from the registry
      2. Open a VISIBLE browser window at the site
      3. Wait for you to complete the manual steps
      4. Save the session profile (cookies, localStorage) for future runs
      5. Re-queue the site as pending

    \b
    Example:
      bm mission intervene reddit
      bm mission intervene discourse_forum --persona bot_account
    """
    asyncio.run(_do_intervene(ctx, site_key, persona))


async def _do_intervene(ctx, site_key: str, persona: str) -> None:
    import os
    import subprocess
    import time as _time
    from browsermind_core.runtime.environment_registry import resolve as resolve_env
    from browsermind_core.console.session import DEFAULT_STORE
    from browsermind_core.mission.mission_queue import MissionQueue

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))

    # Resolve site
    env_entry = resolve_env(site_key)
    if env_entry is None:
        click.echo(click.style("[ERR] ", fg="red") + f"Unknown site key: {site_key!r}")
        click.echo("      Run `bm site ls` to see available keys.")
        return

    start_url = getattr(env_entry, "login_url", None) or getattr(env_entry, "start_url", None) or ""
    if not start_url:
        click.echo(click.style("[ERR] ", fg="red") + f"No start URL for site {site_key!r}")
        return

    persona_name = persona
    safe_persona = persona_name.lower().replace(" ", "_")
    profile_dir = Path(store_dir) / "profiles" / safe_persona / env_entry.key
    profile_dir.mkdir(parents=True, exist_ok=True)

    click.echo()
    click.echo(click.style("  Human Intervention Mode", bold=True, fg="cyan"))
    click.echo(f"  Site    : {site_key}")
    click.echo(f"  URL     : {start_url}")
    click.echo(f"  Persona : {persona_name}")
    click.echo(f"  Profile : {profile_dir}")
    click.echo()
    click.echo("  A browser window will open. Complete the manual step (login, captcha, etc.)")
    click.echo("  then come back here and press ENTER to save the session.")
    click.echo()
    click.confirm("  Ready to open browser?", default=True, abort=True)
    click.echo()

    # --- Strategy 1: Raw Chrome subprocess (no CDP = Google won't block) ---
    chrome_exe = _find_chrome()
    if chrome_exe:
        click.echo(click.style("  [BROWSER] ", fg="green") + f"Launching Chrome (no automation): {chrome_exe}")
        proc = subprocess.Popen([
            chrome_exe,
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-sync",
            start_url,
        ])
        click.echo()
        click.echo("  >>> Complete the manual steps in Chrome, then press ENTER here. <<<")
        click.echo("  (You can also just close Chrome — session is saved automatically)")
        click.echo()
        input("  Press ENTER when done ... ")
        click.echo()
        click.echo("  Waiting for Chrome to save session...")
        try:
            proc.terminate()
            _time.sleep(1.5)  # Give Chrome time to flush cookies to disk
        except Exception:
            pass

    else:
        # --- Strategy 2: Playwright fallback (may be blocked by Google) ---
        from playwright.async_api import async_playwright
        click.echo(click.style("  [WARN] ", fg="yellow") +
                   "Chrome not found — using Playwright (Google sign-in may be blocked).")
        click.echo(f"         Install Chrome from https://www.google.com/chrome/ for full support.")
        click.echo()

        async with async_playwright() as pw:
            browser = None
            for channel in ("chrome", None):
                try:
                    kw = dict(
                        user_data_dir=str(profile_dir),
                        headless=False,
                        args=[
                            "--no-first-run", "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-infobars",
                        ],
                        ignore_https_errors=True,
                    )
                    if channel:
                        kw["channel"] = channel
                    browser = await pw.chromium.launch_persistent_context(**kw)
                    break
                except Exception as exc:
                    if channel:
                        pass  # try next
                    else:
                        raise

            try:
                await browser.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "window.chrome={runtime:{}};"
                )
                page = browser.pages[0] if browser.pages else await browser.new_page()
                await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                click.echo(click.style("  [BROWSER OPEN] ", fg="green") + f"Navigated to {start_url}")
                click.echo()
                click.echo("  >>> Complete the manual steps, then press ENTER here. <<<")
                click.echo()
                loop = asyncio.get_event_loop()
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                    await loop.run_in_executor(pool, lambda: input("  Press ENTER when done ... "))
                click.echo()
                click.echo("  Saving session profile...")
            finally:
                await browser.close()

    click.echo(click.style("  [OK] ", fg="green") + f"Session saved to {profile_dir}")

    # Re-queue the site as pending
    queue = MissionQueue(store_dir)
    requeued = queue.resume(site_key)
    if requeued:
        click.echo(click.style("  [OK] ", fg="green") + f"'{site_key}' re-queued as pending.")
    else:
        queue.add(site_key, persona=persona_name, budget=200)
        click.echo(click.style("  [OK] ", fg="green") + f"'{site_key}' added to queue.")
    click.echo()


def _find_chrome() -> "str | None":
    """Return the path to the Chrome executable, or None if not found."""
    import os
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        # Edge as fallback — also accepted by Google
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None
