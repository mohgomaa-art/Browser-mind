"""GitHubUploader — upload a MediaAsset to a GitHub repository via Contents API.

Uses stdlib urllib only — no extra dependencies.
Requires a personal access token with `repo` scope.
"""
from __future__ import annotations

import base64
import json as _json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from browsermind_core.media.media_asset import MediaAsset
from browsermind_core.media.upload.base import MediaUploader, UploadResult


class GitHubUploader(MediaUploader):
    destination_key = "github"

    def can_upload(self, asset: MediaAsset) -> bool:
        return bool(asset.local_path)

    async def upload(
        self,
        asset: MediaAsset,
        page=None,
        token: Optional[str] = None,
        owner: str = "",
        repo: str = "",
        path: str = "",
        commit_message: str = "",
        branch: str = "main",
        **kwargs,
    ) -> UploadResult:
        if not token or not owner or not repo:
            return UploadResult.fail("GitHubUploader requires token, owner, and repo")
        if not asset.local_path:
            return UploadResult.fail("Asset has no local_path")

        try:
            data    = Path(asset.local_path).read_bytes()
            encoded = base64.b64encode(data).decode()
            dest    = path or f"assets/{asset.content_hash[:8]}_{Path(asset.local_path).name}"
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{dest}"

            payload = _json.dumps({
                "message": commit_message or f"Add {asset.title or dest}",
                "content": encoded,
                "branch":  branch,
            }).encode()

            req = urllib.request.Request(api_url, data=payload, method="PUT")
            req.add_header("Authorization", f"token {token}")
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/vnd.github.v3+json")

            with urllib.request.urlopen(req) as resp:
                resp_data = _json.loads(resp.read())

            cdn_url = resp_data.get("content", {}).get("download_url", "")
            asset.uploaded_to = list(dict.fromkeys(asset.uploaded_to + [self.destination_key]))
            return UploadResult.ok(asset, url=cdn_url, key=self.destination_key)

        except urllib.error.HTTPError as exc:
            return UploadResult.fail(f"GitHub API HTTP {exc.code}: {exc.reason}")
        except Exception as exc:
            return UploadResult.fail(str(exc))
