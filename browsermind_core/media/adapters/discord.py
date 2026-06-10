"""DiscordAdapter — acquire media from Discord CDN links or message pages.

Two modes:
  1. Direct CDN URL (cdn.discordapp.com/attachments/…) → plain HTTP download
  2. Message page URL  → Playwright page required to extract CDN link
"""
from __future__ import annotations

from typing import Optional

from browsermind_core.media.adapters.base import MediaAdapter, AcquisitionResult
from browsermind_core.media.media_asset import MediaSource


_CDN_PREFIXES = (
    "https://cdn.discordapp.com/",
    "https://media.discordapp.net/",
    "https://cdn.discordapp.net/",
)


class DiscordAdapter(MediaAdapter):
    source = MediaSource.DISCORD

    def can_handle(self, url: str) -> bool:
        return "discord.com" in url or "discordapp.com" in url or "discordapp.net" in url

    async def acquire(self, url: str, page=None, vault=None) -> AcquisitionResult:
        if any(url.startswith(p) for p in _CDN_PREFIXES):
            return await self._acquire_cdn(url, vault)
        if page is not None:
            return await self._acquire_via_page(url, page, vault)
        return AcquisitionResult.fail(
            url, "DiscordAdapter: provide a CDN URL or a Playwright page"
        )

    async def _acquire_cdn(self, url: str, vault) -> AcquisitionResult:
        from browsermind_core.media.adapters.generic import GenericHTTPAdapter
        result = await GenericHTTPAdapter().acquire(url, vault=None)
        if result.success and result.asset is not None:
            result.asset.source = self.source
            if vault is not None:
                data = None
                if result.asset.local_path:
                    from pathlib import Path
                    p = Path(result.asset.local_path)
                    if p.exists():
                        data = p.read_bytes()
                result.asset = vault.store(result.asset, data=data)
        return result

    async def _acquire_via_page(self, url: str, page, vault) -> AcquisitionResult:
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            imgs = await page.query_selector_all("img[src*='cdn.discordapp']")
            if not imgs:
                return AcquisitionResult.fail(url, "No Discord CDN images found on page")
            img_url = await imgs[0].get_attribute("src")
            return await self._acquire_cdn(img_url or url, vault)
        except Exception as exc:
            return AcquisitionResult.fail(url, str(exc))
