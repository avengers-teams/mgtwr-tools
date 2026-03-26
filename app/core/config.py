from __future__ import annotations

import os
import sys
from pathlib import Path

APP_TITLE = "多功能数据分析工具"
APP_THEME_COLOR = "#0078D4"
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
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _ROOT_DIR


def resolve_resource_path(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    candidates = [
        project_root() / normalized,
        project_root() / "assets" / normalized,
    ]
    if normalized in {"favicon.ico", "emoji.jpg"}:
        candidates.append(project_root() / "assets" / "icons" / normalized)
    if normalized.startswith("template/"):
        candidates.append(project_root() / "assets" / "templates" / normalized.removeprefix("template/"))
    if normalized.startswith("icons/"):
        candidates.append(project_root() / "assets" / "icons" / normalized.removeprefix("icons/"))

    for candidate in candidates:
        if candidate.exists():
            return os.fspath(candidate)
    return os.fspath(candidates[0])


def stylesheet_path() -> str:
    return os.fspath(STYLES_DIR / "app.qss")


def window_icon_path() -> str:
    return resolve_resource_path("favicon.ico")

