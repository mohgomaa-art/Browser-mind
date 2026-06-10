"""DiscordUploader — upload a MediaAsset to a Discord channel via Playwright.

Requires an authenticated Playwright page already focused on a channel.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from browsermind_core.media.media_asset import MediaAsset, MediaType
from browsermind_core.media.upload.base import MediaUploader, UploadResult


class DiscordUploader(MediaUploader):
    destination_key = "discord"

    _SUPPORTED = {MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.GIF}

    def can_upload(self, asset: MediaAsset) -> bool:
        return asset.media_type in self._SUPPORTED and bool(asset.local_path)

    async def upload(
        self,
        asset: MediaAsset,
        page=None,
        message: str = "",
        **kwargs,
    ) -> UploadResult:
        if page is None:
            return UploadResult.fail("DiscordUploader requires a Playwright page")
        if not asset.local_path:
            return UploadResult.fail("Asset has no local_path")
        try:
            file_input = await page.query_selector("input[type='file']")
            if file_input is None:
                btn = await page.query_selector("button[aria-label*='ttach']")
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(500)
                file_input = await page.query_selector("input[type='file']")

            if file_input is None:
                return UploadResult.fail("Could not locate Discord file input")

            await file_input.set_input_files(str(Path(asset.local_path).resolve()))
            await page.wait_for_timeout(800)

            if message:
                tb = await page.query_selector("div[role='textbox']")
                if tb:
                    await tb.fill(message)

            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)

            asset.uploaded_to = list(dict.fromkeys(asset.uploaded_to + [self.destination_key]))
            return UploadResult.ok(asset, key=self.destination_key)
        except Exception as exc:
            return UploadResult.fail(str(exc))
