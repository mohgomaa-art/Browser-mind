"""
SessionManager — Human-owned identity, AI-owned execution.

Each (persona, site_key) pair has an isolated Playwright profile directory.
This module adds a lightweight session_meta.json manifest on top, tracking:
  - auth_status: logged_in | unknown | expired
  - last_used, created_at (ISO-8601 UTC)
  - cookies_count, storage_size_kb (refreshed on demand)

Workflow:
  1. bm session open <site> --persona recorder
     → headed browser opens, user logs in, presses Enter → status=logged_in
  2. MissionWorker runs site → session is available → exploration succeeds
  3. If no session → AuthGateError raised → mission paused → user notified
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


_META_FILENAME = "session_meta.json"


@dataclass
class SessionMeta:
    site_key: str
    persona: str
    auth_status: str          # "logged_in" | "unknown" | "expired"
    last_used: Optional[str]  # ISO-8601 UTC or None
    created_at: str           # ISO-8601 UTC
    cookies_count: int
    storage_size_kb: float

    @property
    def profile_initialized(self) -> bool:
        return self.cookies_count > 0 or self.storage_size_kb > 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SessionMeta":
        return SessionMeta(
            site_key=d.get("site_key", ""),
            persona=d.get("persona", ""),
            auth_status=d.get("auth_status", "unknown"),
            last_used=d.get("last_used"),
            created_at=d.get("created_at", _utcnow()),
            cookies_count=int(d.get("cookies_count", 0)),
            storage_size_kb=float(d.get("storage_size_kb", 0.0)),
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _profile_root(store_dir: Path, persona: str, site_key: str) -> Path:
    safe_persona = persona.lower().replace(" ", "_")
    return store_dir / "profiles" / safe_persona / site_key


class SessionManager:
    """
    Manages session metadata for all (persona, site) pairs.

    Does NOT manage the Playwright context itself — AuthSession does that.
    This class only reads/writes session_meta.json and provides helpers
    for the CLI and Sidecar.
    """

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_sessions(self, persona: Optional[str] = None) -> List[SessionMeta]:
        profiles_root = self.store_dir / "profiles"
        if not profiles_root.exists():
            return []
        results = []
        for persona_dir in sorted(profiles_root.iterdir()):
            if not persona_dir.is_dir():
                continue
            if persona and persona_dir.name != persona.lower().replace(" ", "_"):
                continue
            for env_dir in sorted(persona_dir.iterdir()):
                if not env_dir.is_dir():
                    continue
                meta = self._load_or_create(env_dir, persona_dir.name, env_dir.name)
                results.append(meta)
        return results

    def get_session(self, site_key: str, persona: str) -> Optional[SessionMeta]:
        profile = _profile_root(self.store_dir, persona, site_key)
        if not profile.exists():
            return None
        return self._load_or_create(profile, persona.lower().replace(" ", "_"), site_key)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def mark_logged_in(self, site_key: str, persona: str) -> SessionMeta:
        meta = self.get_session(site_key, persona) or self._make_default(site_key, persona)
        meta.auth_status = "logged_in"
        meta.last_used = _utcnow()
        self._save(site_key, persona, meta)
        return meta

    def mark_expired(self, site_key: str, persona: str) -> SessionMeta:
        meta = self.get_session(site_key, persona) or self._make_default(site_key, persona)
        meta.auth_status = "expired"
        self._save(site_key, persona, meta)
        return meta

    def touch_last_used(self, site_key: str, persona: str) -> None:
        meta = self.get_session(site_key, persona)
        if meta is None:
            meta = self._make_default(site_key, persona)
        meta.last_used = _utcnow()
        self._save(site_key, persona, meta)

    def refresh_metadata(self, site_key: str, persona: str) -> SessionMeta:
        """Recompute cookies_count and storage_size_kb from the profile directory."""
        profile = _profile_root(self.store_dir, persona, site_key)
        meta = self._load_or_create(profile, persona.lower().replace(" ", "_"), site_key)
        meta.cookies_count = self._count_cookies(profile)
        meta.storage_size_kb = self._dir_size_kb(profile)
        self._save(site_key, persona, meta)
        return meta

    # ------------------------------------------------------------------
    # Browser helper: open headed browser for manual login
    # ------------------------------------------------------------------

    def open_for_login(self, site_key: str, persona: str, start_url: Optional[str] = None) -> None:
        """
        Open a headed Playwright browser for the user to log in manually.
        Blocks until the user presses Enter, then closes the browser and
        marks auth_status=logged_in.
        """
        asyncio.run(self._open_for_login_async(site_key, persona, start_url))

    async def _open_for_login_async(
        self, site_key: str, persona: str, start_url: Optional[str]
    ) -> None:
        from playwright.async_api import async_playwright

        profile = _profile_root(self.store_dir, persona, site_key)
        profile.mkdir(parents=True, exist_ok=True)

        url = start_url or f"https://www.{site_key.replace('_', '.')}.com/"

        print(f"\n  Opening browser for manual login")
        print(f"  Site    : {site_key}")
        print(f"  Persona : {persona}")
        print(f"  Profile : {profile}")
        print(f"  URL     : {url}")
        print(f"\n  Log in inside the browser window, then press ENTER here to save and close.")

        pw = await async_playwright().start()
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            args=[
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # Block on Enter key — run in thread so event loop stays alive
        await asyncio.get_event_loop().run_in_executor(None, input)

        await ctx.close()
        await pw.stop()

        # Persist metadata
        self.mark_logged_in(site_key, persona)
        meta = self.refresh_metadata(site_key, persona)
        print(f"\n  Session saved  -> {profile}")
        print(f"  auth_status    : logged_in")
        print(f"  cookies_count  : {meta.cookies_count}")
        print(f"  storage_size   : {meta.storage_size_kb:.1f} KB")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_create(self, profile: Path, persona: str, site_key: str) -> SessionMeta:
        meta_file = profile / _META_FILENAME
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                return SessionMeta.from_dict(data)
            except Exception:
                pass
        return self._make_default(site_key, persona)

    def _make_default(self, site_key: str, persona: str) -> SessionMeta:
        profile = _profile_root(self.store_dir, persona, site_key)
        return SessionMeta(
            site_key=site_key,
            persona=persona,
            auth_status="unknown",
            last_used=None,
            created_at=_utcnow(),
            cookies_count=self._count_cookies(profile),
            storage_size_kb=self._dir_size_kb(profile),
        )

    def _save(self, site_key: str, persona: str, meta: SessionMeta) -> None:
        profile = _profile_root(self.store_dir, persona, meta.persona)
        profile.mkdir(parents=True, exist_ok=True)
        meta_file = profile / _META_FILENAME
        meta_file.write_text(
            json.dumps(meta.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _count_cookies(profile: Path) -> int:
        """Count cookie entries stored in Chromium's Cookies SQLite file."""
        cookies_db = profile / "Default" / "Cookies"
        if not cookies_db.exists():
            # Chromium may store cookies directly in profile root
            cookies_db = profile / "Cookies"
        if not cookies_db.exists():
            return 0
        try:
            import sqlite3
            with sqlite3.connect(str(cookies_db)) as conn:
                row = conn.execute("SELECT COUNT(*) FROM cookies").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    @staticmethod
    def _dir_size_kb(profile: Path) -> float:
        if not profile.exists():
            return 0.0
        total = sum(
            f.stat().st_size
            for f in profile.rglob("*")
            if f.is_file()
        )
        return round(total / 1024, 1)
