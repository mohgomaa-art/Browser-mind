"""InstagramAdapter — acquire images/videos from Instagram post pages.

Requires an authenticated Playwright page. Instagram blocks all unauthenticated
headless access on media pages.
"""
from __future__ import annotations

from typing import Optional

from browsermind_core.media.adapters.base import MediaAdapter, AcquisitionResult
from browsermind_core.media.media_asset import MediaSource


class InstagramAdapter(MediaAdapter):
    source = MediaSource.INSTAGRAM

    def can_handle(self, url: str) -> bool:
        return "instagram.com" in url

    async def acquire(self, url: str, page=None, vault=None) -> AcquisitionResult:
        if page is None:
            return AcquisitionResult.fail(
                url, "InstagramAdapter requires an authenticated Playwright page"
            )
        try:
            await page.goto(url, wait_until="networkidle", timeout=25000)
            media_url = await self._extract_media_url(page)
            if not media_url:
                return AcquisitionResult.fail(url, "Could not find Instagram media URL")

            caption = await self._extract_caption(page)
            author  = await self._extract_author(page)

            from browsermind_core.media.adapters.generic import GenericHTTPAdapter
            result = await GenericHTTPAdapter().acquire(media_url, vault=None)
            if not result.success or result.asset is None:
                return result

            result.asset.source            = self.source
            result.asset.source_url        = url
            result.asset.title             = caption[:100] if caption else ""
            result.asset.author            = author
            result.asset.metadata["caption"] = caption

            if vault is not None:
                result.asset = vault.store(result.asset)
            return AcquisitionResult.ok(result.asset)

        except Exception as exc:
            return AcquisitionResult.fail(url, str(exc))

    async def _extract_media_url(self, page) -> Optional[str]:
        selectors = [
            "article img[src*='cdninstagram']",
            "article img[src*='fbcdn']",
            "img._aagt",
            "video source",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    return await el.get_attribute("src")
            except Exception:
                pass
        return None

    async def _extract_caption(self, page) -> str:
        try:
            el = await page.query_selector("h1, div._a9zs span")
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def _extract_author(self, page) -> str:
        try:
            el = await page.query_selector("a.x1i10hfl")
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""
