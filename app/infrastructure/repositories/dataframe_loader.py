import pandas as pd


class ExcelDataLoader:
    EMPTY_MARKERS = {"", " ", "nan", "none", "null", "na", "n/a", "--", "-"}

    @classmethod
    def load_excel(cls, path):
        dataframe = pd.read_excel(path)
        dataframe.columns = [str(column).strip() for column in dataframe.columns]
        return cls.normalize_dataframe(dataframe)

    @classmethod
    def normalize_dataframe(cls, dataframe):
        normalized = dataframe.copy()
        for column in normalized.columns:
            series = normalized[column]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                cleaned = series.map(cls._clean_cell)
                normalized[column] = cleaned
                numeric_series = pd.to_numeric(cleaned, errors="coerce")
                if cleaned.notna().sum() > 0 and numeric_series.notna().sum() == cleaned.notna().sum():
                    normalized[column] = numeric_series
                    continue

                if cls._looks_like_time_column(column):
                    datetime_series = pd.to_datetime(cleaned, errors="coerce")
                    if datetime_series.notna().sum() == cleaned.notna().sum():
                        normalized[column] = datetime_series
            elif pd.api.types.is_float_dtype(series) or pd.api.types.is_integer_dtype(series):
                normalized[column] = pd.to_numeric(series, errors="coerce")

        return normalized

    @classmethod
    def coerce_analysis_columns(
        cls,
        dataframe,
        x_columns,
        y_columns,
        coord_columns,
        time_columns=None,
        missing_strategy="drop",
        missing_fill_value=None,
        return_stats=False,
    ):
        converted = dataframe.copy()
        numeric_columns = list(dict.fromkeys((x_columns or []) + (y_columns or []) + (coord_columns or [])))
        selected_columns = list(dict.fromkeys(numeric_columns + list(time_columns or [])))
        stats = {
            "rows_before": len(converted),
            "missing_rows": 0,
            "rows_removed": 0,
            "filled_cells": 0,
            "missing_strategy": missing_strategy,
            "missing_fill_value": missing_fill_value,
        }

        for column in numeric_columns:
            original = converted[column]
            numeric_series = pd.to_numeric(original, errors="coerce")
            invalid_mask = numeric_series.isna() & original.notna()
            if invalid_mask.any():
                invalid_count = int(invalid_mask.sum())
                raise ValueError(f"列 {column} 存在 {invalid_count} 个无法转换为数值的单元格")
            converted[column] = numeric_series

        for column in time_columns or []:
            series = converted[column]
            if pd.api.types.is_numeric_dtype(series):
                continue
            datetime_series = pd.to_datetime(series, errors="coerce", format="mixed")
            if (datetime_series.notna() | series.isna()).all():
                converted[column] = datetime_series
            else:
                numeric_series = pd.to_numeric(series, errors="coerce")
                invalid_mask = numeric_series.isna() & series.notna()
                if invalid_mask.any():
                    invalid_count = int(invalid_mask.sum())
                    raise ValueError(f"时间列 {column} 存在 {invalid_count} 个无法转换的单元格")
                converted[column] = numeric_series

        if selected_columns:
            missing_mask = converted[selected_columns].isna().any(axis=1)
            missing_rows = int(missing_mask.sum())
            stats["missing_rows"] = missing_rows

            if missing_rows:
                if missing_strategy == "drop":
                    converted = converted.loc[~missing_mask].reset_index(drop=True)
                    stats["rows_removed"] = missing_rows
                elif missing_strategy == "fill":
                    if missing_fill_value is None:
                        raise ValueError("缺失值处理策略为填充时，必须提供填充值")
                    stats["filled_cells"] = int(converted[selected_columns].isna().sum().sum())
                    converted.loc[:, selected_columns] = converted[selected_columns].fillna(missing_fill_value)
                else:
                    raise ValueError(f"不支持的缺失值处理策略: {missing_strategy}")

        if converted.empty:
            raise ValueError("按当前缺失值处理策略处理后没有剩余样本")

        if return_stats:
            return converted, stats
        return converted

    @classmethod
    def _clean_cell(cls, value):
        if pd.isna(value):
            return pd.NA
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() in cls.EMPTY_MARKERS:
                return pd.NA
            return stripped
        return value

    @staticmethod
    def _looks_like_time_column(column_name):
        lowered = str(column_name).lower()
        keywords = ["time", "date", "year", "month", "day", "日期", "时间", "年份", "年月"]
        return any(keyword in lowered for keyword in keywords)

