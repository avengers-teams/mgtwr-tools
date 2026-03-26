from __future__ import annotations

from app.application.dto.update import UpdateCheckResult, UpdateStatus
from app.core.config import app_version
from app.domain.policies.versioning import is_newer_version
from app.infrastructure.repositories.github_release_repository import GitHubReleaseRepository


class UpdateService:
    def __init__(self, release_repository: GitHubReleaseRepository):
        self.release_repository = release_repository

    def fetch_update_status(self) -> UpdateStatus:
        current_version = app_version()
        latest_release = self.release_repository.fetch_latest_release()
        if latest_release is None:
            return UpdateStatus(
                current_version=current_version,
                error_message="无法连接远端仓库或未读取到发布信息。",
            )

        update_available = is_newer_version(latest_release.version, current_version)
        return UpdateStatus(
            current_version=current_version,
            latest_version=latest_release.version,
            release_url=latest_release.release_url,
            title=latest_release.title,
            update_available=update_available,
        )

    def check_for_updates(self) -> UpdateCheckResult | None:
        status = self.fetch_update_status()
        if not status.update_available or not status.latest_version or not status.release_url:
            return None
        return UpdateCheckResult(
            current_version=status.current_version,
            latest_version=status.latest_version,
            release_url=status.release_url,
            title=status.title,
        )
