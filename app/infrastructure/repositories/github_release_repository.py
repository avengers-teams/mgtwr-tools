from __future__ import annotations

import httpx

from app.application.dto.update import ReleaseInfo
from app.core.config import GITHUB_LATEST_RELEASE_API_URL, build_release_tag_url


class GitHubReleaseRepository:
    def __init__(self, latest_release_api_url: str = GITHUB_LATEST_RELEASE_API_URL):
        self.latest_release_api_url = latest_release_api_url

    def fetch_latest_release(self) -> ReleaseInfo | None:
        try:
            response = httpx.get(
                self.latest_release_api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "mgtwr-tools-update-checker",
                },
                timeout=8.0,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None
        version = str(payload.get("tag_name") or "").strip()
        release_url = build_release_tag_url(version)
        if not version:
            return None

        title = str(payload.get("name") or "").strip() or None
        return ReleaseInfo(version=version, release_url=release_url, title=title)
