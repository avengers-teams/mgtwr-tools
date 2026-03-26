from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignificancePageViewModel:
    file_path: str
    dataset: object
    chart_specs: list
    coordinate_columns: list
    time_columns: list

