from __future__ import annotations

import pandas as pd

TEMPORAL_MODELS = {"GTWR", "MGTWR"}


def apply_structure_inference(dataset):
    columns = list(dataset.coefficients.columns)
    first_beta_index = next((i for i, column in enumerate(columns) if str(column).startswith("beta_")), len(columns))
    dataset.metadata_columns = columns[:first_beta_index]
    dataset.beta_columns = [col for col in dataset.coefficients.columns if str(col).startswith("beta_")]
    dataset.se_columns = [col for col in dataset.coefficients.columns if str(col).startswith("se_")]
    dataset.t_columns = [col for col in dataset.coefficients.columns if str(col).startswith("t_")]
    dataset.metric_columns = dataset.beta_columns + dataset.se_columns + dataset.t_columns
    dataset.variable_names = [column.removeprefix("beta_") for column in dataset.beta_columns]
    dataset.target_column = infer_target_column(dataset)
    dataset.coord_columns = infer_coord_columns(dataset)
    dataset.time_column = infer_time_column(dataset) if dataset.model in TEMPORAL_MODELS else None
    return dataset


def infer_target_column(dataset):
    explicit_names = {"actual", "observed", "target", "真实值", "实际值", "因变量"}
    for column in dataset.metadata_columns:
        normalized = str(column).strip().lower()
        if normalized in explicit_names:
            return column

    excluded = set(infer_named_coord_columns(dataset))
    named_time = infer_named_time_column(dataset)
    if named_time:
        excluded.add(named_time)

    candidates = []
    for column in dataset.metadata_columns:
        if str(column).startswith("Original_") or column in excluded:
            continue
        numeric_ratio = pd.to_numeric(dataset.coefficients[column], errors="coerce").notna().mean()
        if numeric_ratio >= 0.8:
            candidates.append(column)

    if candidates:
        non_temporal = [column for column in candidates if not dataset.looks_temporal(dataset.coefficients[column])]
        return non_temporal[0] if non_temporal else candidates[0]

    for column in dataset.metadata_columns:
        if not str(column).startswith("Original_"):
            return column
    return dataset.metadata_columns[0] if dataset.metadata_columns else None


def infer_coord_columns(dataset):
    named_columns = infer_named_coord_columns(dataset)
    if len(named_columns) == 2:
        return named_columns

    excluded = {dataset.target_column}
    time_column = infer_named_time_column(dataset)
    if time_column:
        excluded.add(time_column)

    numeric_candidates = []
    for column in dataset.metadata_columns:
        if column in excluded or str(column).startswith("Original_"):
            continue
        if pd.to_numeric(dataset.coefficients[column], errors="coerce").notna().mean() >= 0.8:
            numeric_candidates.append(column)
    return numeric_candidates[:2]


def infer_time_column(dataset):
    named_column = infer_named_time_column(dataset)
    if named_column:
        return named_column

    excluded = set(dataset.coord_columns)
    if dataset.target_column:
        excluded.add(dataset.target_column)
    for column in dataset.metadata_columns:
        if column in excluded or str(column).startswith("Original_"):
            continue
        if dataset.looks_temporal(dataset.coefficients[column]):
            return column
    return None


def infer_named_coord_columns(dataset):
    lon_keywords = ("lon", "lng", "long", "经度")
    lat_keywords = ("lat", "纬度")
    lon_column = None
    lat_column = None
    for column in dataset.metadata_columns:
        normalized = str(column).strip().lower()
        if lon_column is None and any(keyword in normalized for keyword in lon_keywords):
            lon_column = column
        elif lat_column is None and any(keyword in normalized for keyword in lat_keywords):
            lat_column = column
    return [column for column in (lon_column, lat_column) if column is not None]


def infer_named_time_column(dataset):
    time_keywords = ("year", "年份", "time", "date", "日期", "时间")
    for column in dataset.metadata_columns:
        normalized = str(column).strip().lower()
        if any(keyword in normalized for keyword in time_keywords):
            return column
    return None

