"""
AuthSessionManager — manages persistent Playwright browser contexts.

Each (Persona, Environment) pair gets an isolated profile directory.
Login state (cookies, localStorage) persists across process restarts.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from browsermind_core.runtime.environment_registry import EnvironmentEntry, profile_dir


class AuthSession:
    """
    A live browser session for one (Persona, Environment) pair.
    Wraps a Playwright persistent context.
    """

    def __init__(
        self,
        entry: EnvironmentEntry,
        persona_name: str,
        store_dir: Path,
        headless: bool = False,
        resource_saver: bool = False,
    ):
        self.entry = entry
        self.persona_name = persona_name
        self.store_dir = store_dir
        self.headless = headless
        self.resource_saver = resource_saver
        self._profile = profile_dir(entry, store_dir, persona_name)
        self._context = None
        self._pw = None

    @property
    def profile_path(self) -> Path:
        return self._profile

    async def open(self, url: Optional[str] = None) -> None:
        """Open browser at url (default: entry.start_url). Restores auth state if profile exists."""
        from playwright.async_api import async_playwright

        target = url or self.entry.start_url
        self._profile.mkdir(parents=True, exist_ok=True)

        print(f"\n  Environment : {self.entry.key}")
        print(f"  Persona     : {self.persona_name}")
        print(f"  Profile     : {self._profile}")
        print(f"  URL         : {target}")

        self._pw = await async_playwright().start()

        args = [
            "--no-first-run",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-features=IsolateOrigins,site-per-process",
            "--lang=en-US,en",
            # Additional stealth: hide automation indicators
            "--excludeSwitches=enable-automation",
            "--useAutomationExtension=false",
            "--disable-extensions-except=",
            "--disable-default-apps",
            "--password-store=basic",
        ]
        if self.resource_saver:
            args += [
                "--mute-audio",
                "--disable-gpu",
                "--blink-settings=imagesEnabled=false",
                "--disable-background-networking",
            ]

        vp_size = {"width": 1280, "height": 800} if self.resource_saver else {"width": 1920, "height": 1080}

        launch_kwargs = dict(
            user_data_dir=str(self._profile),
            headless=self.headless,
            args=args,
            viewport=vp_size,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
        )

        # Prefer the real installed Chrome — Google and similar sites accept it;
        # they block Playwright's bundled Chromium.
        self._context = None
        for channel in ("chrome", None):
            try:
                kw = dict(launch_kwargs)
                if channel:
                    kw["channel"] = channel
                self._context = await self._pw.chromium.launch_persistent_context(**kw)
                if channel:
                    print(f"  Browser     : Chrome (channel={channel!r})")
                else:
                    print(f"  Browser     : Chromium (bundled)")
                break
            except Exception as exc:
                if channel:
                    print(f"  [AuthSession] Chrome not found ({exc}), falling back to Chromium")
                else:
                    raise

        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            window.chrome = { runtime: {} };
        """)

        if self.resource_saver:
            # Block heavy resources: images, fonts, media, tracking pixels
            async def _block_resource(route):
                try:
                    await route.abort()
                except Exception:
                    pass
            await self._context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,otf,mp4,mp3,ogg,wav}",
                _block_resource,
            )

        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        try:
            await page.set_viewport_size(vp_size)
        except Exception:
            pass
        await page.goto(target, wait_until="domcontentloaded")
        return page

    async def close(self) -> None:
        """Close browser. Profile (auth state) is saved automatically by Playwright."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        print(f"\n  Session saved -> {self._profile}")
        try:
            from browsermind_core.session.session_manager import SessionManager
            SessionManager(self.store_dir).touch_last_used(self.entry.key, self.persona_name)
        except Exception:
            pass

    def get_credentials(self) -> dict:
        """Fetch credentials for the active environment from the persona vault in the persistence layer.

        Values are stored Fernet-encrypted by `VaultWriter`; this method
        decrypts them transparently. Legacy plaintext entries (pre-encryption)
        are returned unchanged.
        """
        try:
            from browsermind_core.runtime.vault_writer import VaultWriter
            data = VaultWriter(str(self.store_dir), self.persona_name).load()
            env_key = self.entry.key
            return data.get("secrets", {}).get(env_key, {})
        except Exception:
            pass
        return {}

    def is_profile_initialized(self) -> bool:
        """True if profile dir exists and has content (prior login state may exist)."""
        return self._profile.exists() and any(self._profile.iterdir())

    def resolve_identity_status(self, env_key: str) -> Optional[str]:
        """Return the persisted Identity.status for (persona, env), if any.

        Looks up the canonical identity index written by the kernel. Returns
        one of {"active", "expired", "revoked", "requires_2fa"} or None when
        no identity has been provisioned for this (persona, env) pair.

        Identity records on disk live under `<store>/identity/<id>.json`;
        the index `_identity_index.json` (when present) maps `identifier ->
        {"id": ..., "persona": ..., "env": ...}` and may carry a `"status"`
        override populated by the kernel.
        """
        try:
            from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
            provider = LocalJSONPersistenceProvider(str(self.store_dir))
            # Read the identity index directly. Kernel writes it via _save_index.
            index_path = self.store_dir / "_identity_index.json"
            if not index_path.exists():
                return None
            import json
            try:
                idx = json.loads(index_path.read_text(encoding="utf-8")) or {}
            except Exception:
                return None
            for entry in idx.values():
                # Match by env. Persona match is implicit via the AuthSession.
                if entry.get("env") == env_key or entry.get("environment") == env_key:
                    if entry.get("persona") and entry["persona"] != self.persona_name:
                        continue
                    # Index may carry status; otherwise read the Identity record.
                    status = entry.get("status")
                    if status:
                        return status
                    ident_id = entry.get("id")
                    if ident_id:
                        record = provider.load("identity", ident_id)
                        if record:
                            return record.get("status")
            return None
        except Exception:
            return None

    async def get_page(self):
        if self._context:
            return self._context.pages[0] if self._context.pages else await self._context.new_page()
        return None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()


class AuthSessionManager:
    """
    Manages AuthSession lifecycle.
    Ensures one session per (Persona, Environment) at a time.
    """

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self._active: dict[tuple[str, str], AuthSession] = {}

    def get_or_create(
        self,
        entry: EnvironmentEntry,
        persona_name: str,
        headless: bool = False,
        resource_saver: bool = False,
    ) -> AuthSession:
        key = (persona_name, entry.key)
        if key not in self._active:
            self._active[key] = AuthSession(
                entry=entry,
                persona_name=persona_name,
                store_dir=self.store_dir,
                headless=headless,
                resource_saver=resource_saver,
            )
        return self._active[key]

    async def close_session(self, persona_name: str, env_key: str) -> bool:
        """Close one session and evict it from the cache.

        Returns True if a session existed and was closed. M7: prevents
        stale wrappers from accumulating in `_active` after close().
        """
        key = (persona_name, env_key)
        session = self._active.pop(key, None)
        if session is None:
            return False
        try:
            await session.close()
        except Exception:
            pass
        return True

    async def close_all(self) -> int:
        """Close every active session. Returns the number closed.

        Intended end-of-batch cleanup for callers that opted into
        session continuity (owns_session=False on ReplayEngine).
        """
        closed = 0
        keys = list(self._active.keys())
        for persona_name, env_key in keys:
            if await self.close_session(persona_name, env_key):
                closed += 1
        return closed

    def profile_initialized(self, entry: EnvironmentEntry, persona_name: str) -> bool:
        session = self.get_or_create(entry, persona_name)
        return session.is_profile_initialized()

    def list_profiles(self) -> list[dict]:
        profiles_root = self.store_dir / "profiles"
        if not profiles_root.exists():
            return []
        result = []
        for persona_dir in profiles_root.iterdir():
            if persona_dir.is_dir():
                for env_dir in persona_dir.iterdir():
                    if env_dir.is_dir():
                        result.append({
                            "persona": persona_dir.name,
                            "environment": env_dir.name,
                            "profile_path": str(env_dir),
                            "initialized": any(env_dir.iterdir()),
                        })
        return result
