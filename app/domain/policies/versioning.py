from __future__ import annotations

import re


def parse_version(version: str | None) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version or "")
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)


def is_newer_version(candidate_version: str | None, current_version: str | None) -> bool:
    candidate = parse_version(candidate_version)
    current = parse_version(current_version)
    width = max(len(candidate), len(current))
    padded_candidate = candidate + (0,) * (width - len(candidate))
    padded_current = current + (0,) * (width - len(current))
    return padded_candidate > padded_current
