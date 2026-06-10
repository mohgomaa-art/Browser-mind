"""PinterestAdapter — acquire images from Pinterest pin pages.

Requires a live Playwright page. Pinterest blocks unauthenticated HTTP-only
scrapers aggressively; a browser context (authenticated or not) is needed to
reach the rendered pin image URL.
"""
from __future__ import annotations

from typing import Optional

from browsermind_core.media.adapters.base import MediaAdapter, AcquisitionResult
from browsermind_core.media.media_asset import MediaSource


class PinterestAdapter(MediaAdapter):
    source = MediaSource.PINTEREST

    def can_handle(self, url: str) -> bool:
        return "pinterest.com" in url or "pin.it" in url

    async def acquire(self, url: str, page=None, vault=None) -> AcquisitionResult:
        if page is None:
            return AcquisitionResult.fail(url, "PinterestAdapter requires a Playwright page")
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            img_url = await self._extract_image_url(page)
            if not img_url:
                return AcquisitionResult.fail(url, "Could not locate pin image URL")

            title  = await self._extract_title(page)
            author = await self._extract_author(page)

            from browsermind_core.media.adapters.generic import GenericHTTPAdapter
            result = await GenericHTTPAdapter().acquire(img_url, vault=None)
            if not result.success or result.asset is None:
                return result

            result.asset.source     = self.source
            result.asset.source_url = url
            result.asset.title      = title or result.asset.title
            result.asset.author     = author
            result.asset.metadata["pin_image_url"] = img_url

            if vault is not None:
                data = None
                if result.asset.local_path:
                    from pathlib import Path
                    p = Path(result.asset.local_path)
                    if p.exists():
                        data = p.read_bytes()
                result.asset = vault.store(result.asset, data=data)
            return AcquisitionResult.ok(result.asset)

        except Exception as exc:
            return AcquisitionResult.fail(url, str(exc))

    async def _extract_image_url(self, page) -> Optional[str]:
        selectors = [
            "img[src*='pinimg.com/originals']",
            "img[src*='pinimg.com/736x']",
            "div[data-test-id='pin-closeup-image'] img",
            "img[class*='hCL']",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    src = await el.get_attribute("src")
                    if src:
                        return src.replace("/736x/", "/originals/")
            except Exception:
                pass
        return None

    async def _extract_title(self, page) -> str:
        try:
            el = await page.query_selector("h1")
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def _extract_author(self, page) -> str:
        try:
            el = await page.query_selector("a[href*='/'] span[class*='username']")
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""
