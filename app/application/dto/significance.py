from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignificanceRenderOptions:
    threshold: float = 1.96
    beta_column: str | None = None
    longitude_column: str | None = None
    latitude_column: str | None = None
    time_column: str | None = None
    time_value: object | None = None
    spatial_mode: str = "time_slice"
    temporal_mode: str = "aggregate_space"
    location_value: object | None = None
    figure_title: str | None = None
    decimal_places: int = 4
    font_family: str | None = "Microsoft YaHei"


@dataclass
class SignificanceStats:
    total: int
    significant: int
    ratio: float
    positive: int
    negative: int

    @property
    def total_significant(self) -> int:
        return self.significant


@dataclass
class SignificanceRenderResult:
    figure: object
    stats: SignificanceStats
    hint: str

