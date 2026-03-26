from __future__ import annotations

import numpy as np
import pandas as pd

from app.application.dto.significance import SignificanceStats


class SignificancePolicy:
    @staticmethod
    def significance_flags(series, threshold):
        return pd.Series(np.abs(pd.to_numeric(series, errors="coerce")) >= abs(float(threshold)), index=series.index)

    @staticmethod
    def significance_stats(dataset, t_column: str, render_options, frame_provider):
        frame = frame_provider(dataset, render_options)
        t_values = pd.to_numeric(frame[t_column], errors="coerce").dropna()
        if t_values.empty:
            raise ValueError(f"{t_column} 列没有可用于显著性分析的数值")
        flags = SignificancePolicy.significance_flags(t_values, render_options.threshold)
        significant_count = int(flags.sum())
        positive_count = int((t_values[flags] > 0).sum())
        negative_count = int((t_values[flags] < 0).sum())
        total = int(len(flags))
        ratio = significant_count / total if total else 0.0
        return SignificanceStats(
            total=total,
            significant=significant_count,
            ratio=ratio,
            positive=positive_count,
            negative=negative_count,
        )

    @staticmethod
    def resolve_linked_beta_column(dataset, t_column: str, render_options):
        if render_options and render_options.beta_column:
            if render_options.beta_column in dataset.beta_columns:
                return render_options.beta_column
            raise ValueError(f"结果文件中缺少对应的系数字段: {render_options.beta_column}")

        base_name = dataset.metric_base_name(t_column)
        matched = next((column for column in dataset.beta_columns if dataset.metric_base_name(column) == base_name), None)
        if matched:
            return matched
        raise ValueError(f"未找到与 {t_column} 对应的 beta_ 字段，请手动选择系数字段")

