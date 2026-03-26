from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    release_url: str
    title: str | None = None


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    release_url: str
    title: str | None = None


@dataclass(frozen=True)
class UpdateStatus:
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    title: str | None = None
    update_available: bool = False
    error_message: str | None = None
