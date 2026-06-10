"""bm environment — CLI commands for managing browser environments."""
import click
import asyncio
from pathlib import Path

from browsermind_core.runtime.environment_registry import (
    resolve, get_all, register, EnvironmentEntry
)
from browsermind_core.runtime.auth_session import AuthSession, AuthSessionManager
from browsermind_core.console.session import DEFAULT_STORE


@click.group("environment", short_help="Manage browser environments")
def environment_group():
    """Manage registered web environments and their auth profiles."""


@environment_group.command("list")
def env_list():
    """List all registered environments."""
    click.echo("\n  Registered Environments:\n")
    for e in get_all():
        aliases = f"  [{', '.join(e.aliases)}]" if e.aliases else ""
        click.echo(f"  [OK] {e.key:<16} {e.start_url}{aliases}")
    click.echo()


@environment_group.command("add")
@click.option("--key", required=True, help="Environment key (e.g. mysite)")
@click.option("--url", required=True, help="Start URL (e.g. https://mysite.com)")
@click.option("--alias", multiple=True, help="Aliases (can repeat)")
@click.option("--family", default="generic")
def env_add(key, url, alias, family):
    """Register a new environment."""
    existing = resolve(key)
    if existing:
        click.echo(f"  [WARN] '{key}' already registered → {existing.start_url}")
        return

    entry = EnvironmentEntry(
        key=key,
        start_url=url,
        aliases=list(alias),
        family=family,
    )
    register(entry)
    click.echo(f"  [OK] Registered: {key} → {url}")
    click.echo(f"  Note: Custom environments are session-only. Add to environment_registry.py to persist.")


@environment_group.command("open")
@click.argument("env_key")
@click.option("--persona", default="pilot", help="Persona name")
@click.option("--url", default=None, help="Override start URL")
@click.option("--store", default=DEFAULT_STORE)
@click.option("--headless", is_flag=True)
def env_open(env_key, persona, url, store, headless):
    """Open a browser session for an environment."""
    entry = resolve(env_key)
    if entry is None:
        known = ", ".join(e.key for e in get_all())
        click.echo(f"\n  [ERR] Unknown environment: '{env_key}'")
        click.echo(f"  Known: {known}")
        return

    async def _run():
        session = AuthSession(
            entry=entry,
            persona_name=persona,
            store_dir=Path(store),
            headless=headless,
        )
        initialized = session.is_profile_initialized()
        if initialized:
            click.echo(f"\n  Restoring auth state for [{persona}] on [{entry.key}]")
        else:
            click.echo(f"\n  Fresh session — log in manually, then press Enter.")
        await session.open(url)
        click.echo("\n  Press Enter to close and save session...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await session.close()

    asyncio.run(_run())


@environment_group.command("profiles")
@click.option("--store", default=DEFAULT_STORE)
def env_profiles(store):
    """List all saved auth profiles."""
    manager = AuthSessionManager(Path(store))
    profiles = manager.list_profiles()
    if not profiles:
        click.echo("  No saved profiles found.")
        return
    click.echo("\n  Saved Auth Profiles:\n")
    for p in profiles:
        status = "[AUTH]" if p["initialized"] else "[EMPTY]"
        click.echo(f"  {status}  {p['persona']:<16} → {p['environment']:<16}  {p['profile_path']}")
    click.echo()


@environment_group.command("resolve")
@click.argument("text")
def env_resolve(text):
    """Test how a phrase resolves to an environment."""
    entry = resolve(text)
    if entry:
        click.echo(f"  [OK] '{text}' → {entry.key} ({entry.start_url})")
    else:
        click.echo(f"  [MISS] '{text}' → no match in registry")
        click.echo(f"  Known: {', '.join(e.key for e in get_all())}")
