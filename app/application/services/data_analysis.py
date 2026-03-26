import json
from abc import ABC, abstractmethod
from contextlib import nullcontext

import pandas as pd
from joblib import parallel_backend
from mgtwr.model import GWR, GTWR, MGWR, MGTWR
from mgtwr.sel import (
    SearchGTWRParameter,
    SearchGWRParameter,
    SearchMGTWRParameter,
    SearchMGWRParameter,
)
from app.infrastructure.repositories.dataframe_loader import ExcelDataLoader


class BaseAnalysisStrategy(ABC):
    model_name = ""

    def build_common_kwargs(self, params, kernel, fixed):
        return {
            "kernel": kernel,
            "fixed": fixed,
            "constant": params.get("constant", True),
            "thread": params.get("thread", 1),
            "convert": params.get("convert", False),
        }

    def get_parallel_context(self, params):
        thread_count = params.get("thread", 1)
        if isinstance(thread_count, int) and thread_count > 1:
            return parallel_backend("threading", n_jobs=thread_count)
        return nullcontext()

    @abstractmethod
    def fit(self, analysis, kernel, fixed, criterion, params):
        pass


class GWRStrategy(BaseAnalysisStrategy):
    model_name = "GWR"

    def fit(self, analysis, kernel, fixed, criterion, params):
        common_kwargs = self.build_common_kwargs(params, kernel, fixed)
        with self.get_parallel_context(params):
            selector = SearchGWRParameter(analysis.coords, analysis.x, analysis.y, **common_kwargs)
            bw = selector.search(
                criterion=criterion,
                bw_min=params.get("bw_min"),
                bw_max=params.get("bw_max"),
                tol=params.get("tol", 1.0e-6),
                bw_decimal=params.get("bw_decimal", 1),
                max_iter=params.get("max_iter", 200),
                verbose=params.get("verbose", False),
                time_cost=params.get("time_cost", False),
            )
            result = GWR(analysis.coords, analysis.x, analysis.y, bw, **common_kwargs).fit()
        return result, {"bw": bw}


class MGWRStrategy(BaseAnalysisStrategy):
    model_name = "MGWR"

    def fit(self, analysis, kernel, fixed, criterion, params):
        common_kwargs = self.build_common_kwargs(params, kernel, fixed)
        with self.get_parallel_context(params):
            selector = SearchMGWRParameter(analysis.coords, analysis.x, analysis.y, **common_kwargs)
            search_result = selector.search(
                criterion=criterion,
                bw_min=params.get("bw_min"),
                bw_max=params.get("bw_max"),
                tol=params.get("tol", 1.0e-6),
                bw_decimal=params.get("bw_decimal", 1),
                init_bw=params.get("init_bw"),
                multi_bw_min=params.get("multi_bw_min"),
                multi_bw_max=params.get("multi_bw_max"),
                tol_multi=params.get("tol_multi", 1.0e-5),
                bws_same_times=params.get("bws_same_times", 5),
                verbose=params.get("verbose", False),
                rss_score=params.get("rss_score", False),
                time_cost=params.get("time_cost", False),
            )
            result = MGWR(
                analysis.coords,
                analysis.x,
                analysis.y,
                selector,
                **common_kwargs,
            ).fit(
                n_chunks=params.get("n_chunks", 1),
                skip_calculate=params.get("skip_calculate", False),
            )
        return result, {
            "bws": analysis.to_serializable(search_result[0]),
            "bws_history": analysis.to_serializable(search_result[1]),
            "scores": analysis.to_serializable(search_result[2]),
            "bw_init": search_result[5],
        }


class GTWRStrategy(BaseAnalysisStrategy):
    model_name = "GTWR"

    def fit(self, analysis, kernel, fixed, criterion, params):
        common_kwargs = self.build_common_kwargs(params, kernel, fixed)
        with self.get_parallel_context(params):
            selector = SearchGTWRParameter(analysis.coords, analysis.t, analysis.x, analysis.y, **common_kwargs)
            bw, tau = selector.search(
                criterion=criterion,
                bw_min=params.get("bw_min"),
                bw_max=params.get("bw_max"),
                tau_min=params.get("tau_min"),
                tau_max=params.get("tau_max"),
                tol=params.get("tol", 1.0e-6),
                bw_decimal=params.get("bw_decimal", 1),
                tau_decimal=params.get("tau_decimal", 1),
                max_iter=params.get("max_iter", 200),
                verbose=params.get("verbose", False),
                time_cost=params.get("time_cost", False),
            )
            result = GTWR(
                analysis.coords,
                analysis.t,
                analysis.x,
                analysis.y,
                bw,
                tau,
                **common_kwargs,
            ).fit()
        return result, {"bw": bw, "tau": tau}


class MGTWRStrategy(BaseAnalysisStrategy):
    model_name = "MGTWR"

    def fit(self, analysis, kernel, fixed, criterion, params):
        common_kwargs = self.build_common_kwargs(params, kernel, fixed)
        with self.get_parallel_context(params):
            selector = SearchMGTWRParameter(analysis.coords, analysis.t, analysis.x, analysis.y, **common_kwargs)
            search_result = selector.search(
                criterion=criterion,
                bw_min=params.get("bw_min"),
                bw_max=params.get("bw_max"),
                tau_min=params.get("tau_min"),
                tau_max=params.get("tau_max"),
                tol=params.get("tol", 1.0e-6),
                bw_decimal=params.get("bw_decimal", 1),
                tau_decimal=params.get("tau_decimal", 1),
                init_bw=params.get("init_bw"),
                init_tau=params.get("init_tau"),
                multi_bw_min=params.get("multi_bw_min"),
                multi_bw_max=params.get("multi_bw_max"),
                multi_tau_min=params.get("multi_tau_min"),
                multi_tau_max=params.get("multi_tau_max"),
                tol_multi=params.get("tol_multi", 1.0e-5),
                verbose=params.get("verbose", False),
                rss_score=params.get("rss_score", False),
                time_cost=params.get("time_cost", False),
            )
            result = MGTWR(
                analysis.coords,
                analysis.t,
                analysis.x,
                analysis.y,
                selector,
                **common_kwargs,
            ).fit(
                n_chunks=params.get("n_chunks", 1),
                skip_calculate=params.get("skip_calculate", False),
            )
        return result, {
            "bws": analysis.to_serializable(search_result[0]),
            "taus": analysis.to_serializable(search_result[1]),
            "bws_history": analysis.to_serializable(search_result[2]),
            "taus_history": analysis.to_serializable(search_result[3]),
            "scores": analysis.to_serializable(search_result[4]),
            "bw_init": search_result[7],
            "tau_init": search_result[8],
        }


class AnalysisStrategyFactory:
    _strategies = {
        GWRStrategy.model_name: GWRStrategy(),
        MGWRStrategy.model_name: MGWRStrategy(),
        GTWRStrategy.model_name: GTWRStrategy(),
        MGTWRStrategy.model_name: MGTWRStrategy(),
    }

    @classmethod
    def get_strategy(cls, model_name):
        strategy = cls._strategies.get(model_name.upper())
        if strategy is None:
            raise ValueError(f"不支持的模型: {model_name}")
        return strategy


class DataAnalysis:
    def __init__(self, input_path, output_path):
        self.file_path = input_path
        self.output_path = output_path
        self.excel_data = self.get_xlsx_data(input_path)
        self.x = None
        self.y = None
        self.t = None
        self.t_display = None
        self.coords = None
        self.x_columns = []
        self.y_columns = []
        self.t_columns = []
        self.coord_columns = []
        self.cleaning_stats = {}

    @staticmethod
    def get_xlsx_data(path):
        return ExcelDataLoader.load_excel(path)

    def set_variables(self, x, y, t, coords, missing_strategy="drop", missing_fill_value=None):
        self.x_columns = x
        self.y_columns = y or []
        self.t_columns = t or []
        self.coord_columns = coords

        self.excel_data, self.cleaning_stats = ExcelDataLoader.coerce_analysis_columns(
            self.excel_data,
            x_columns=x,
            y_columns=y,
            coord_columns=coords,
            time_columns=t or [],
            missing_strategy=missing_strategy,
            missing_fill_value=missing_fill_value,
            return_stats=True,
        )
        self.x = self.excel_data[x]
        self.y = self.excel_data[y] if y else None
        self.t_display = self.excel_data[t] if t else None
        self.t = self.build_model_time_frame(self.t_display) if t else None
        self.coords = self.excel_data[coords]
        print(f"自变量列: {x}，样本数: {len(self.x)}")
        print(f"因变量列: {self.y_columns}")
        print(f"时间变量列: {self.t_columns}")
        print(f"坐标变量列: {coords}")
        self.print_cleaning_summary()

    def print_cleaning_summary(self):
        missing_rows = int(self.cleaning_stats.get("missing_rows", 0))
        if missing_rows <= 0:
            print("所选字段未检测到空值")
            return

        strategy = self.cleaning_stats.get("missing_strategy")
        if strategy == "drop":
            removed = int(self.cleaning_stats.get("rows_removed", 0))
            print(f"检测到 {missing_rows} 行在所选字段中包含空值，已忽略 {removed} 行")
        elif strategy == "fill":
            filled_cells = int(self.cleaning_stats.get("filled_cells", 0))
            fill_value = self.cleaning_stats.get("missing_fill_value")
            print(f"检测到 {missing_rows} 行在所选字段中包含空值，已使用 {fill_value} 填充 {filled_cells} 个单元格")

    def run_model(self, model, kernel, fixed, criterion, params):
        strategy = AnalysisStrategyFactory.get_strategy(model)
        result, search_result = strategy.fit(self, kernel, fixed, criterion, params)
        model_name = strategy.model_name
        self.print_summary(model_name, result, search_result)
        self.export_results(model_name, result, search_result, params, kernel, fixed, criterion)
        return result

    def export_results(self, model, result, search_result, params, kernel, fixed, criterion):
        summary_df = pd.DataFrame(self.build_summary_rows(model, result, search_result, params, kernel, fixed, criterion))
        coefficient_df = self.build_coefficients_frame(result, params)

        with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="summary", index=False)
            coefficient_df.to_excel(writer, sheet_name="coefficients", index=False)

            settings_df = pd.DataFrame(
                [{"parameter": key, "value": self.stringify(value)} for key, value in params.items()]
            )
            settings_df.to_excel(writer, sheet_name="settings", index=False)

            self.write_search_sheets(writer, search_result)

        print(f"分析结果已输出至 {self.output_path}")

    def build_summary_rows(self, model, result, search_result, params, kernel, fixed, criterion):
        rows = [
            {"item": "model", "value": model},
            {"item": "kernel", "value": kernel},
            {"item": "fixed", "value": fixed},
            {"item": "criterion", "value": criterion},
            {"item": "thread", "value": params.get("thread", 1)},
            {"item": "constant", "value": params.get("constant", True)},
            {"item": "convert", "value": params.get("convert", False)},
            {"item": "samples", "value": len(self.x)},
            {"item": "variables", "value": len(self.x_columns)},
        ]

        metric_names = [
            "R2", "adj_R2", "RSS", "sigma2", "aic", "aicc", "aic_c", "bic",
            "ENP", "tr_S", "df_model", "df_reside", "llf",
        ]
        for name in metric_names:
            if hasattr(result, name):
                rows.append({"item": name, "value": self.stringify(getattr(result, name))})

        for key, value in search_result.items():
            if key.endswith("_history"):
                continue
            rows.append({"item": f"search_{key}", "value": self.stringify(value)})
        return rows

    def build_coefficients_frame(self, result, params=None):
        variable_names = self.resolve_result_variable_names(result)
        data = {}

        for index, column_name in enumerate(variable_names):
            data[f"beta_{column_name}"] = result.betas[:, index]

        if hasattr(result, "bse"):
            for index, column_name in enumerate(variable_names):
                data[f"se_{column_name}"] = result.bse[:, index]

        t_matrix = getattr(result, "tvalues", None)
        if t_matrix is None:
            t_matrix = getattr(result, "t_values", None)
        if t_matrix is not None:
            for index, column_name in enumerate(variable_names):
                data[f"t_{column_name}"] = t_matrix[:, index]

        data["predicted"] = result.predict_value.reshape(-1)
        data["residual"] = result.reside.reshape(-1)

        coefficient_df = pd.DataFrame(data)
        for idx, column in enumerate(self.coord_columns):
            coefficient_df.insert(idx, column, self.coords.iloc[:, idx].values)

        if self.t_display is not None and self.t_columns:
            coefficient_df.insert(len(self.coord_columns), self.t_columns[0], self.t_display.iloc[:, 0].values)

        coefficient_df.insert(0, self.y_columns[0], self.y.iloc[:, 0].values)
        return self.append_original_fields_to_coefficients(coefficient_df, params or {})

    def append_original_fields_to_coefficients(self, coefficient_df, params):
        original_fields = params.get("append_original_fields") or []
        original_fields = [field for field in original_fields if field in self.excel_data.columns]
        if not original_fields:
            return coefficient_df

        rename_map = {field: f"Original_{field}" for field in original_fields}
        source = self.excel_data[original_fields].rename(columns=rename_map).reset_index(drop=True)
        coefficient_rows = coefficient_df.reset_index(drop=True)

        if len(source) != len(coefficient_rows):
            raise ValueError("追加原始字段失败：结果行数与清洗后源数据行数不一致")

        self.validate_coefficient_alignment(coefficient_rows)

        prefixed_columns = [rename_map[field] for field in original_fields if rename_map[field] in source.columns]
        combined = pd.concat([source[prefixed_columns], coefficient_rows], axis=1)
        return combined

    def resolve_result_variable_names(self, result):
        beta_count = int(result.betas.shape[1])
        if beta_count == len(self.x_columns) + 1:
            return ["Intercept"] + self.x_columns
        if beta_count == len(self.x_columns):
            return list(self.x_columns)
        raise ValueError(
            f"结果系数列数异常：期望 {len(self.x_columns)} 或 {len(self.x_columns) + 1} 列，实际为 {beta_count}"
        )

    @staticmethod
    def build_model_time_frame(timeframe):
        if timeframe is None:
            return None

        numeric_time = pd.DataFrame(index=timeframe.index)
        for column in timeframe.columns:
            series = timeframe[column]
            if pd.api.types.is_numeric_dtype(series):
                numeric_time[column] = pd.to_numeric(series, errors="coerce")
                continue

            datetime_series = pd.to_datetime(series, errors="coerce", format="mixed")
            if datetime_series.notna().sum() == 0:
                raise ValueError(f"时间列 {column} 没有可用于建模的有效值")

            origin = datetime_series.dropna().min()
            numeric_time[column] = (datetime_series - origin).dt.total_seconds() / 86400.0

        return numeric_time

    def validate_coefficient_alignment(self, coefficient_df):
        check_columns = list(self.coord_columns)
        if self.t is not None and self.t_columns:
            check_columns.append(self.t_columns[0])
        if self.y is not None and self.y_columns:
            check_columns.insert(0, self.y_columns[0])

        for column in check_columns:
            if column not in coefficient_df.columns or column not in self.excel_data.columns:
                raise ValueError(f"追加原始字段失败：缺少对齐校验列 {column}")

            expected = self.excel_data[column].reset_index(drop=True)
            actual = coefficient_df[column].reset_index(drop=True)
            if not expected.equals(actual):
                mismatch_index = next(
                    (
                        index for index, (left, right) in enumerate(zip(expected.tolist(), actual.tolist()))
                        if not ((pd.isna(left) and pd.isna(right)) or left == right)
                    ),
                    None,
                )
                if mismatch_index is None:
                    mismatch_index = 0
                raise ValueError(
                    f"追加原始字段失败：第 {mismatch_index + 1} 行的 {column} 与分析结果不一致，请检查样本顺序"
                )

    def write_search_sheets(self, writer, search_result):
        if "scores" in search_result and search_result["scores"] is not None:
            pd.DataFrame({"score": self.flatten(search_result["scores"])}).to_excel(
                writer, sheet_name="search_scores", index=False
            )

        if "bws_history" in search_result and search_result["bws_history"] is not None:
            pd.DataFrame(search_result["bws_history"]).to_excel(writer, sheet_name="bw_history", index=False)

        if "taus_history" in search_result and search_result["taus_history"] is not None:
            pd.DataFrame(search_result["taus_history"]).to_excel(writer, sheet_name="tau_history", index=False)

    def print_summary(self, model, result, search_result):
        print(f"{model} 拟合完成")
        for key, value in search_result.items():
            if key.endswith("_history"):
                continue
            print(f"{key}: {self.stringify(value)}")

        for metric in ["R2", "adj_R2", "aic", "aicc", "aic_c", "bic", "ENP", "RSS", "sigma2"]:
            if hasattr(result, metric):
                print(f"{metric}: {self.stringify(getattr(result, metric))}")

    def flatten(self, value):
        if hasattr(value, "ravel"):
            return value.ravel().tolist()
        if isinstance(value, list):
            return value
        return [value]

    def to_serializable(self, value):
        if hasattr(value, "tolist"):
            return value.tolist()
        return value

    def stringify(self, value):
        if isinstance(value, (list, dict, tuple)):
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "tolist"):
            return json.dumps(value.tolist(), ensure_ascii=False)
        return value

