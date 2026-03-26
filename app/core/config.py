from __future__ import annotations

import os
import sys
from pathlib import Path

APP_TITLE = "多功能数据分析工具"
APP_DESCRIPTION = (
    "MGTWR 模型分析、结果可视化、显著性分析与若干数据处理工具。"
)
APP_THEME_COLOR = "#0078D4"
VERSION_FILE_NAME = "version"
GITHUB_REPOSITORY = "avengers-teams/mgtwr-tools"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
GITHUB_RELEASE_TAG_URL_PREFIX = f"{GITHUB_RELEASES_URL}/tag/"
GITHUB_LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
DEFAULT_SIGNIFICANCE_THRESHOLD = 1.96
DEFAULT_DECIMAL_PLACES = 4
DEFAULT_FONT_FALLBACKS = [
    "Microsoft YaHei",
    "SimSun",
    "Times New Roman",
]

_ROOT_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = _ROOT_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
STYLES_DIR = ASSETS_DIR / "styles"
TEMPLATES_DIR = ASSETS_DIR / "templates"


def project_root() -> Path:
    return runtime_roots()[0]


def runtime_roots() -> list[Path]:
    roots: list[Path] = []

    module_root = Path(__file__).resolve().parents[2]
    roots.append(module_root)

    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
        if executable_root not in roots:
            roots.append(executable_root)

        try:
            compiled_root = Path(__compiled__.containing_dir).resolve()  # type: ignore[name-defined]
        except Exception:
            compiled_root = None
        if compiled_root is not None and compiled_root not in roots:
            roots.append(compiled_root)

    return roots


def version_file_path() -> Path:
    for root in runtime_roots():
        candidate = root / VERSION_FILE_NAME
        if candidate.exists():
            return candidate
    return runtime_roots()[0] / VERSION_FILE_NAME


def app_version(default: str = "0.0.0.0") -> str:
    version_path = version_file_path()
    try:
        content = version_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return default

    for line in content:
        value = line.strip()
        if value:
            return value
    return default


def build_release_tag_url(version: str | None) -> str:
    normalized = str(version or "").strip()
    if not normalized:
        return GITHUB_RELEASES_URL
    return f"{GITHUB_RELEASE_TAG_URL_PREFIX}{normalized}"


def resolve_resource_path(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    candidates = []
    for root in runtime_roots():
        candidates.extend(
            [
                root / normalized,
                root / "assets" / normalized,
            ]
        )
        if normalized in {"favicon.ico", "emoji.jpg"}:
            candidates.append(root / "assets" / "icons" / normalized)
        if normalized.startswith("template/"):
            candidates.append(root / "assets" / "templates" / normalized.removeprefix("template/"))
        if normalized.startswith("icons/"):
            candidates.append(root / "assets" / "icons" / normalized.removeprefix("icons/"))

    for candidate in candidates:
        if candidate.exists():
            return os.fspath(candidate)
    return os.fspath(candidates[0])


def stylesheet_path() -> str:
    return os.fspath(STYLES_DIR / "app.qss")


def window_icon_path() -> str:
    return resolve_resource_path("favicon.ico")
