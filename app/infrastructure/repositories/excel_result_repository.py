from __future__ import annotations

import pandas as pd

from app.core.exceptions import DataLoadError
from app.domain.models.result_dataset import ResultDataset
from app.domain.policies.column_inference import apply_structure_inference


class ExcelResultRepository:
    def load(self, path: str) -> ResultDataset:
        try:
            workbook = pd.ExcelFile(path)
        except Exception as exc:
            raise DataLoadError(f"无法读取结果文件：{exc}") from exc

        with workbook:
            if "coefficients" not in workbook.sheet_names:
                raise DataLoadError("结果文件缺少 coefficients 工作表，无法可视化")

            dataset = ResultDataset(path=path)
            if "summary" in workbook.sheet_names:
                summary_df = workbook.parse("summary")
                if {"item", "value"}.issubset(summary_df.columns):
                    dataset.summary = {
                        str(row["item"]): dataset.parse_cell(row["value"])
                        for _, row in summary_df.iterrows()
                    }

            if "settings" in workbook.sheet_names:
                settings_df = workbook.parse("settings")
                if {"parameter", "value"}.issubset(settings_df.columns):
                    dataset.settings = {
                        str(row["parameter"]): dataset.parse_cell(row["value"])
                        for _, row in settings_df.iterrows()
                    }

            dataset.coefficients = workbook.parse("coefficients")
            dataset.search_scores = workbook.parse("search_scores") if "search_scores" in workbook.sheet_names else None
            dataset.bw_history = workbook.parse("bw_history") if "bw_history" in workbook.sheet_names else None
            dataset.tau_history = workbook.parse("tau_history") if "tau_history" in workbook.sheet_names else None
            dataset.model = str(dataset.summary.get("model", "")).upper()
            return apply_structure_inference(dataset)

