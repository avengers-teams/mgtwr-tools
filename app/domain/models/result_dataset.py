from __future__ import annotations

from dataclasses import dataclass, field

import json
import numpy as np
import pandas as pd


@dataclass
class ResultDataset:
    path: str
    summary: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    coefficients: pd.DataFrame = field(default_factory=pd.DataFrame)
    search_scores: pd.DataFrame | None = None
    bw_history: pd.DataFrame | None = None
    tau_history: pd.DataFrame | None = None
    model: str = ""
    target_column: str | None = None
    coord_columns: list = field(default_factory=list)
    time_column: str | None = None
    beta_columns: list = field(default_factory=list)
    se_columns: list = field(default_factory=list)
    t_columns: list = field(default_factory=list)
    metric_columns: list = field(default_factory=list)
    variable_names: list = field(default_factory=list)
    metadata_columns: list = field(default_factory=list)

    def has_spatial(self):
        return len(self.coord_columns) == 2 and all(column in self.coefficients.columns for column in self.coord_columns)

    def has_temporal(self):
        return bool(self.time_column and self.time_column in self.coefficients.columns)

    def spatial_candidate_columns(self):
        numeric_columns = []
        for column in self.coefficients.columns:
            if pd.to_numeric(self.coefficients[column], errors="coerce").notna().any():
                numeric_columns.append(column)
        return numeric_columns

    def temporal_candidate_columns(self):
        candidates = []
        for column in self.metadata_columns:
            if self.looks_temporal(self.coefficients[column]):
                candidates.append(column)
        if self.time_column and self.time_column not in candidates:
            candidates.insert(0, self.time_column)
        return candidates

    def time_value_options(self, time_column):
        if not time_column or time_column not in self.coefficients.columns:
            return []
        values = self.coefficients[time_column].dropna().drop_duplicates().tolist()
        values = self.sort_temporal_values(values)
        return [(self.format_display_value(value), value) for value in values]

    def location_value_options(self, x_column, y_column):
        if not x_column or not y_column:
            return []
        if x_column not in self.coefficients.columns or y_column not in self.coefficients.columns:
            return []
        locations = self.coefficients[[x_column, y_column]].dropna().drop_duplicates().copy()
        locations = self.sort_location_frame(locations, x_column, y_column)
        return [
            (self.format_location_label(row[x_column], row[y_column], x_column, y_column), (row[x_column], row[y_column]))
            for _, row in locations.iterrows()
        ]

    def metric_text(self, key, decimals=4, default="--"):
        value = self.summary.get(key, default)
        if isinstance(value, (float, int, np.floating, np.integer)):
            return self.format_number(value, decimals)
        return str(value)

    @staticmethod
    def metric_prefix_label(column):
        column = str(column)
        if column.startswith("beta_"):
            return "系数"
        if column.startswith("se_"):
            return "标准误"
        if column.startswith("t_"):
            return "t值"
        return "统计量"

    @staticmethod
    def metric_base_name(column):
        column = str(column)
        for prefix in ("beta_", "se_", "t_"):
            if column.startswith(prefix):
                return column.removeprefix(prefix)
        return column

    @classmethod
    def metric_display_name(cls, column):
        return f"{cls.metric_prefix_label(column)} | {cls.metric_base_name(column)}"

    @staticmethod
    def parse_cell(value):
        if isinstance(value, str):
            text = value.strip()
            if text and text[0] in "[{":
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return value

    @staticmethod
    def looks_temporal(series):
        text_series = series.dropna()
        if text_series.empty:
            return False
        numeric_series = pd.to_numeric(text_series, errors="coerce")
        if numeric_series.notna().mean() >= 0.8 and len(numeric_series.dropna().unique()) >= 2:
            return True
        datetime_series = pd.to_datetime(text_series.astype(str), errors="coerce", format="mixed")
        return datetime_series.notna().mean() >= 0.8

    @staticmethod
    def sort_temporal_values(values):
        numeric_series = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce")
        if numeric_series.notna().all():
            return [value for _, value in sorted(zip(numeric_series.tolist(), values), key=lambda item: item[0])]
        datetime_series = pd.to_datetime(pd.Series(values, dtype="object").astype(str), errors="coerce", format="mixed")
        if datetime_series.notna().all():
            return [value for _, value in sorted(zip(datetime_series.tolist(), values), key=lambda item: item[0])]
        return sorted(values, key=lambda value: str(value))

    @staticmethod
    def format_display_value(value):
        if isinstance(value, pd.Timestamp):
            if value.normalize() == value:
                return value.strftime("%Y-%m-%d")
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    @classmethod
    def format_location_label(cls, x_value, y_value, x_column, y_column):
        return f"{x_column}={cls.format_display_value(x_value)} | {y_column}={cls.format_display_value(y_value)}"

    @staticmethod
    def sort_location_frame(frame, x_column, y_column):
        numeric_x = pd.to_numeric(frame[x_column], errors="coerce")
        numeric_y = pd.to_numeric(frame[y_column], errors="coerce")
        if numeric_x.notna().all() and numeric_y.notna().all():
            return frame.assign(__x__=numeric_x, __y__=numeric_y).sort_values(["__x__", "__y__"]).drop(columns=["__x__", "__y__"])
        return frame.assign(__x__=frame[x_column].astype(str), __y__=frame[y_column].astype(str)).sort_values(["__x__", "__y__"]).drop(columns=["__x__", "__y__"])

    @staticmethod
    def format_number(value, decimals):
        return f"{float(value):.{max(0, int(decimals))}f}"

