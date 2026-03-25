from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StandardizationMethod:
    key: str
    label: str

    def transform(self, series: pd.Series) -> pd.Series:
        raise NotImplementedError

    @staticmethod
    def _safe_zero_series(series: pd.Series) -> pd.Series:
        return pd.Series(np.zeros(len(series), dtype=float), index=series.index)


@dataclass(frozen=True)
class ZScoreMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        std = float(series.std(ddof=0))
        if std == 0 or np.isnan(std):
            return self._safe_zero_series(series)
        return (series - float(series.mean())) / std


@dataclass(frozen=True)
class MinMaxMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        min_value = float(series.min())
        max_value = float(series.max())
        scale = max_value - min_value
        if scale == 0 or np.isnan(scale):
            return self._safe_zero_series(series)
        return (series - min_value) / scale


@dataclass(frozen=True)
class MaxAbsMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        max_abs = float(series.abs().max())
        if max_abs == 0 or np.isnan(max_abs):
            return self._safe_zero_series(series)
        return series / max_abs


@dataclass(frozen=True)
class RobustMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        median = float(series.median())
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0 or np.isnan(iqr):
            return self._safe_zero_series(series)
        return (series - median) / iqr


@dataclass(frozen=True)
class MeanNormalizationMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        mean_value = float(series.mean())
        scale = float(series.max()) - float(series.min())
        if scale == 0 or np.isnan(scale):
            return self._safe_zero_series(series)
        return (series - mean_value) / scale


@dataclass(frozen=True)
class DecimalScalingMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        max_abs = float(series.abs().max())
        if max_abs == 0 or np.isnan(max_abs):
            return self._safe_zero_series(series)
        digits = int(np.ceil(np.log10(max_abs + 1)))
        return series / (10 ** digits)


@dataclass(frozen=True)
class Log1PMethod(StandardizationMethod):
    def transform(self, series: pd.Series) -> pd.Series:
        if (series <= -1).any():
            raise ValueError("Log1p 标准化要求所有值均大于 -1")
        return np.log1p(series)


class StandardizationService:
    METHODS = [
        ZScoreMethod("zscore", "Z-Score 标准化"),
        MinMaxMethod("minmax", "Min-Max 归一化"),
        MaxAbsMethod("maxabs", "MaxAbs 标准化"),
        RobustMethod("robust", "Robust 标准化"),
        MeanNormalizationMethod("mean_norm", "均值归一化"),
        DecimalScalingMethod("decimal_scaling", "小数定标"),
        Log1PMethod("log1p", "Log1p 变换"),
    ]
    METHOD_MAP = {method.key: method for method in METHODS}

    @classmethod
    def method_items(cls):
        return [(method.key, method.label) for method in cls.METHODS]

    @classmethod
    def get_method(cls, key: str) -> StandardizationMethod:
        method = cls.METHOD_MAP.get(key)
        if method is None:
            raise ValueError(f"不支持的标准化方法: {key}")
        return method

    @classmethod
    def apply(
        cls,
        dataframe: pd.DataFrame,
        columns: list[str],
        method_key: str,
        output_mode: str = "append",
        suffix: str = "",
    ) -> tuple[pd.DataFrame, list[dict[str, object]]]:
        if dataframe is None or dataframe.empty:
            raise ValueError("数据为空，无法标准化")
        if not columns:
            raise ValueError("请至少选择一个字段")

        method = cls.get_method(method_key)
        result = dataframe.copy()
        report_rows = []
        normalized_suffix = suffix.strip() or method.key

        for column in columns:
            if column not in result.columns:
                raise ValueError(f"字段不存在: {column}")
            numeric_series = pd.to_numeric(result[column], errors="coerce")
            invalid_mask = numeric_series.isna() & result[column].notna()
            if invalid_mask.any():
                raise ValueError(f"字段 {column} 存在无法转换为数值的单元格")

            transformed = method.transform(numeric_series.fillna(0.0))
            transformed[result[column].isna()] = np.nan
            if output_mode == "replace":
                target_column = column
            elif output_mode == "append":
                target_column = f"{column}_{normalized_suffix}"
            else:
                raise ValueError(f"不支持的输出模式: {output_mode}")

            result[target_column] = transformed.astype(float)
            report_rows.append(
                {
                    "字段": column,
                    "输出列": target_column,
                    "方法": method.label,
                    "原均值": float(numeric_series.mean()) if numeric_series.notna().any() else np.nan,
                    "原标准差": float(numeric_series.std(ddof=0)) if numeric_series.notna().any() else np.nan,
                    "新均值": float(result[target_column].mean()) if result[target_column].notna().any() else np.nan,
                    "新标准差": float(result[target_column].std(ddof=0)) if result[target_column].notna().any() else np.nan,
                }
            )

        return result, report_rows
