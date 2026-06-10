"""bm session — CLI commands for managing persistent browser sessions."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click


# ── Group ─────────────────────────────────────────────────────────────────────

@click.group("session", short_help="Manage persistent browser sessions")
def session_group():
    """
    Manage saved browser sessions (cookies, storage) per site and persona.

    \b
    Quick start:
      bm session ls                        # list all sessions
      bm session ls --status logged_in     # only logged-in sessions
      bm session open reddit               # log in to reddit manually
      bm session status                    # summary counts
      bm session refresh reddit            # recompute cookie/storage stats
    """


# ── bm session ls ─────────────────────────────────────────────────────────────

@session_group.command("ls")
@click.option("--persona", default=None, help="Filter by persona name")
@click.option("--status", "filter_status",
              type=click.Choice(["logged_in", "unknown", "expired"]),
              default=None, help="Filter by auth status")
@click.pass_context
def session_ls(ctx, persona, filter_status):
    """List all sessions with their auth status and metadata."""
    from browsermind_core.session.session_manager import SessionManager
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    mgr = SessionManager(store_dir)

    sessions = mgr.list_sessions(persona=persona)
    if filter_status:
        sessions = [s for s in sessions if s.auth_status == filter_status]

    if not sessions:
        click.echo("No sessions found.")
        return

    # Header
    click.echo(f"\n  {'SITE':<25} {'PERSONA':<12} {'STATUS':<12} {'LAST USED':<16} {'COOKIES':>7} {'SIZE':>8} {'AGE':>6}")
    click.echo("  " + "─" * 92)

    for s in sessions:
        status_color = {"logged_in": "green", "expired": "red", "unknown": "yellow"}.get(s.auth_status, "white")
        status_str = click.style(f"{s.auth_status:<12}", fg=status_color)

        last_used = _fmt_ago(s.last_used)
        created_at = _fmt_age(s.created_at)
        size = f"{s.storage_size_kb:.0f} KB" if s.storage_size_kb else "—"
        cookies = str(s.cookies_count) if s.cookies_count else "—"

        click.echo(
            f"  {s.site_key:<25} {s.persona:<12} {status_str} "
            f"{last_used:<16} {cookies:>7} {size:>8} {created_at:>6}"
        )

    click.echo()


# ── bm session open ───────────────────────────────────────────────────────────

@session_group.command("open")
@click.argument("site_key")
@click.option("--persona", default="recorder", show_default=True,
              help="Persona to use for the session")
@click.option("--url", default=None, help="Override the start URL")
@click.pass_context
def session_open(ctx, site_key, persona, url):
    """
    Open a headed browser for manual login.

    The browser opens with the saved profile (cookies preserved).
    Log in normally, then press ENTER in this terminal to save and close.
    The session is marked as logged_in automatically.

    \b
    Example:
      bm session open reddit --persona recorder
      bm session open github
    """
    from browsermind_core.session.session_manager import SessionManager
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    mgr = SessionManager(store_dir)

    # Try to get start URL from site registry if not provided
    start_url = url
    if not start_url:
        try:
            from browsermind_core.mission.site_registry import get_spec
            spec = get_spec(site_key)
            if spec:
                start_url = spec.login_url or spec.start_url
        except Exception:
            pass

    try:
        mgr.open_for_login(site_key, persona, start_url=start_url)
        click.echo(click.style("\n[OK] ", fg="green") + f"Session saved for {site_key} / {persona}")
        click.echo(f"     Run: bm mission resume {site_key}  (if it was paused)")
    except KeyboardInterrupt:
        click.echo("\n[Cancelled] Browser closed without saving.")
        sys.exit(1)


# ── bm session status ─────────────────────────────────────────────────────────

@session_group.command("status")
@click.pass_context
def session_status(ctx):
    """Show a summary count of sessions by auth status."""
    from browsermind_core.session.session_manager import SessionManager
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    mgr = SessionManager(store_dir)

    sessions = mgr.list_sessions()
    total = len(sessions)
    if total == 0:
        click.echo("No sessions found. Run 'bm session open <site>' to create one.")
        return

    from collections import Counter
    counts = Counter(s.auth_status for s in sessions)

    click.echo(f"\n  Session Summary  ({total} total)")
    click.echo("  " + "─" * 32)
    click.echo(f"  {click.style('logged_in', fg='green'):<20} {counts.get('logged_in', 0)}")
    click.echo(f"  {click.style('unknown', fg='yellow'):<20} {counts.get('unknown', 0)}")
    click.echo(f"  {click.style('expired', fg='red'):<20} {counts.get('expired', 0)}")
    click.echo()


# ── bm session refresh ────────────────────────────────────────────────────────

@session_group.command("refresh")
@click.argument("site_key", required=False)
@click.option("--persona", default=None, help="Persona to refresh (default: all)")
@click.pass_context
def session_refresh(ctx, site_key, persona):
    """Recompute cookie count and storage size from the profile on disk."""
    from browsermind_core.session.session_manager import SessionManager
    from browsermind_core.console.session import DEFAULT_STORE

    s = ctx.ensure_object(object)
    store_dir = Path(getattr(s, "store_dir", DEFAULT_STORE))
    mgr = SessionManager(store_dir)

    if site_key:
        p = persona or "recorder"
        meta = mgr.refresh_metadata(site_key, p)
        click.echo(
            click.style("[OK] ", fg="green")
            + f"{site_key}/{p}: cookies={meta.cookies_count}  size={meta.storage_size_kb:.1f} KB"
        )
    else:
        sessions = mgr.list_sessions(persona=persona)
        for sess in sessions:
            try:
                mgr.refresh_metadata(sess.site_key, sess.persona)
                click.echo(f"  refreshed: {sess.site_key}/{sess.persona}")
            except Exception as e:
                click.echo(f"  [WARN] {sess.site_key}/{sess.persona}: {e}")
        click.echo(f"\nRefreshed {len(sessions)} session(s).")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_ago(iso: str | None) -> str:
    """Format ISO timestamp as human-readable 'N ago' string."""
    if not iso:
        return "never"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return iso[:10]


def _fmt_age(iso: str | None) -> str:
    """Format ISO timestamp as age string (e.g. '3d')."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            return "today"
        return f"{days}d"
    except Exception:
        return "—"
