"""RedditUploader — upload a MediaAsset to a Reddit post via Playwright.

Requires an authenticated Playwright page. Navigates to the subreddit submit
page, selects the image tab, attaches the file, and submits.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from browsermind_core.media.media_asset import MediaAsset, MediaType
from browsermind_core.media.upload.base import MediaUploader, UploadResult


class RedditUploader(MediaUploader):
    destination_key = "reddit"

    _SUPPORTED = {MediaType.IMAGE, MediaType.GIF}

    def can_upload(self, asset: MediaAsset) -> bool:
        return asset.media_type in self._SUPPORTED and bool(asset.local_path)

    async def upload(
        self,
        asset: MediaAsset,
        page=None,
        subreddit: str = "",
        title: str = "",
        **kwargs,
    ) -> UploadResult:
        if page is None:
            return UploadResult.fail("RedditUploader requires a Playwright page")
        if not asset.local_path:
            return UploadResult.fail("Asset has no local_path")
        try:
            submit_url = (
                f"https://www.reddit.com/r/{subreddit}/submit"
                if subreddit else
                "https://www.reddit.com/submit"
            )
            await page.goto(submit_url, wait_until="networkidle", timeout=20000)

            img_tab = await page.query_selector("[aria-label='Images & Video']")
            if img_tab:
                await img_tab.click()
                await page.wait_for_timeout(500)

            fi = await page.query_selector("input[type='file']")
            if fi:
                await fi.set_input_files(str(Path(asset.local_path).resolve()))
                await page.wait_for_timeout(1000)

            ti = await page.query_selector("textarea[placeholder*='itle'], input[placeholder*='itle']")
            if ti:
                await ti.fill(title or asset.title or "Shared via BrowserMind")

            btn = await page.query_selector("button[type='submit'], button:has-text('Post')")
            if btn:
                await btn.click()
                await page.wait_for_timeout(2000)

            asset.uploaded_to = list(dict.fromkeys(asset.uploaded_to + [self.destination_key]))
            return UploadResult.ok(asset, key=self.destination_key)
        except Exception as exc:
            return UploadResult.fail(str(exc))
