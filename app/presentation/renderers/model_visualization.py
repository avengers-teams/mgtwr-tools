import json
from dataclasses import dataclass

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib import text as mtext
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

DEFAULT_FONT_FALLBACKS = [
    "Microsoft YaHei",
    "SimSun",
    "Times New Roman",
]

matplotlib.rcParams["font.family"] = DEFAULT_FONT_FALLBACKS
matplotlib.rcParams["font.sans-serif"] = DEFAULT_FONT_FALLBACKS
matplotlib.rcParams["axes.unicode_minus"] = False

TEMPORAL_MODELS = {"GTWR", "MGTWR"}


@dataclass
class ChartSpec:
    key: str
    label: str
    requires_beta: bool = False


@dataclass
class RenderOptions:
    vector_path: str | None = None
    raster_path: str | None = None
    class_count: int = 5
    stretch_method: str = "quantile"
    palette: str = "YlGnBu"
    projection: str = "EPSG:4326"
    longitude_column: str | None = None
    latitude_column: str | None = None
    time_column: str | None = None
    time_value: object | None = None
    spatial_mode: str = "time_slice"
    temporal_mode: str = "aggregate_space"
    location_column: str | None = None
    location_value: object | None = None
    category_column: str | None = None
    decimal_places: int = 4
    font_family: str | None = None
    figure_title: str | None = None
    legend_label: str | None = None
    time_slot_width: int = 2
    category_slot_width: int = 2
    figure_width: float = 8.0
    figure_height: float = 5.0
    x_box_aspect: float = 1.0
    y_box_aspect: float = 3.0
    z_box_aspect: float = 1.0


class VisualizationData:
    def __init__(self, path):
        self.path = path
        self.summary = {}
        self.settings = {}
        self.coefficients = pd.DataFrame()
        self.search_scores = None
        self.bw_history = None
        self.tau_history = None
        self.model = ""
        self.target_column = None
        self.coord_columns = []
        self.time_column = None
        self.beta_columns = []
        self.se_columns = []
        self.t_columns = []
        self.variable_names = []
        self._metadata_columns = []
        self._load()

    def _load(self):
        with pd.ExcelFile(self.path) as workbook:
            if "coefficients" not in workbook.sheet_names:
                raise ValueError("结果文件缺少 coefficients 工作表，无法可视化")

            if "summary" in workbook.sheet_names:
                summary_df = workbook.parse("summary")
                if {"item", "value"}.issubset(summary_df.columns):
                    self.summary = {
                        str(row["item"]): self._parse_cell(row["value"])
                        for _, row in summary_df.iterrows()
                    }

            if "settings" in workbook.sheet_names:
                settings_df = workbook.parse("settings")
                if {"parameter", "value"}.issubset(settings_df.columns):
                    self.settings = {
                        str(row["parameter"]): self._parse_cell(row["value"])
                        for _, row in settings_df.iterrows()
                    }

            self.coefficients = workbook.parse("coefficients")
            self.search_scores = workbook.parse("search_scores") if "search_scores" in workbook.sheet_names else None
            self.bw_history = workbook.parse("bw_history") if "bw_history" in workbook.sheet_names else None
            self.tau_history = workbook.parse("tau_history") if "tau_history" in workbook.sheet_names else None

        self.model = str(self.summary.get("model", "")).upper()
        self.beta_columns = [col for col in self.coefficients.columns if str(col).startswith("beta_")]
        self.se_columns = [col for col in self.coefficients.columns if str(col).startswith("se_")]
        self.t_columns = [col for col in self.coefficients.columns if str(col).startswith("t_")]
        self.metric_columns = self.beta_columns + self.se_columns + self.t_columns
        self.variable_names = [column.removeprefix("beta_") for column in self.beta_columns]
        self._infer_structure()

    def _infer_structure(self):
        columns = list(self.coefficients.columns)
        first_beta_index = next((i for i, c in enumerate(columns) if str(c).startswith("beta_")), len(columns))
        self._metadata_columns = columns[:first_beta_index]
        if not self._metadata_columns:
            return

        self.target_column = self._infer_target_column()
        self.coord_columns = self._infer_coord_columns()
        if self.model in TEMPORAL_MODELS:
            self.time_column = self._infer_time_column()

    def _infer_target_column(self):
        explicit_names = {"actual", "observed", "target", "真实值", "实际值", "因变量"}
        for column in self._metadata_columns:
            normalized = str(column).strip().lower()
            if normalized in explicit_names:
                return column

        excluded = set(self._infer_named_coord_columns() + ([self._infer_named_time_column()] if self._infer_named_time_column() else []))
        candidates = []
        for column in self._metadata_columns:
            if str(column).startswith("Original_") or column in excluded:
                continue
            numeric_ratio = pd.to_numeric(self.coefficients[column], errors="coerce").notna().mean()
            if numeric_ratio >= 0.8:
                candidates.append(column)

        if candidates:
            non_temporal = [column for column in candidates if not self._looks_temporal(self.coefficients[column])]
            return non_temporal[0] if non_temporal else candidates[0]

        for column in self._metadata_columns:
            if not str(column).startswith("Original_"):
                return column
        return self._metadata_columns[0]

    def _infer_coord_columns(self):
        named_columns = self._infer_named_coord_columns()
        if len(named_columns) == 2:
            return named_columns

        excluded = {self.target_column}
        time_column = self._infer_named_time_column()
        if time_column:
            excluded.add(time_column)

        numeric_candidates = []
        for column in self._metadata_columns:
            if column in excluded or str(column).startswith("Original_"):
                continue
            if pd.to_numeric(self.coefficients[column], errors="coerce").notna().mean() >= 0.8:
                numeric_candidates.append(column)

        return numeric_candidates[:2]

    def _infer_time_column(self):
        named_column = self._infer_named_time_column()
        if named_column:
            return named_column

        excluded = set(self.coord_columns)
        if self.target_column:
            excluded.add(self.target_column)
        for column in self._metadata_columns:
            if column in excluded or str(column).startswith("Original_"):
                continue
            if self._looks_temporal(self.coefficients[column]):
                return column
        return None

    def _infer_named_coord_columns(self):
        lon_keywords = ("lon", "lng", "long", "经度")
        lat_keywords = ("lat", "纬度")
        lon_column = None
        lat_column = None
        for column in self._metadata_columns:
            normalized = str(column).strip().lower()
            if lon_column is None and any(keyword in normalized for keyword in lon_keywords):
                lon_column = column
            elif lat_column is None and any(keyword in normalized for keyword in lat_keywords):
                lat_column = column
        return [column for column in (lon_column, lat_column) if column is not None]

    def _infer_named_time_column(self):
        time_keywords = ("year", "年份", "time", "date", "日期", "时间")
        for column in self._metadata_columns:
            normalized = str(column).strip().lower()
            if any(keyword in normalized for keyword in time_keywords):
                return column
        return None

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
        for column in self._metadata_columns:
            if self._looks_temporal(self.coefficients[column]):
                candidates.append(column)
        if self.time_column and self.time_column not in candidates:
            candidates.insert(0, self.time_column)
        return candidates

    def category_candidate_columns(self):
        preferred = []
        fallback = []
        for column in self.coefficients.columns:
            if column in self.beta_columns or column in self.se_columns or column in self.t_columns or column == self.time_column:
                continue
            series = self.coefficients[column].dropna()
            if series.empty or series.nunique(dropna=True) < 2:
                continue
            if series.dtype == object or str(series.dtype).startswith("category"):
                preferred.append(column)
            elif series.nunique(dropna=True) <= 100:
                fallback.append(column)
        ordered = []
        for column in preferred + fallback:
            if column not in ordered:
                ordered.append(column)
        return ordered

    def location_candidate_columns(self):
        preferred = []
        fallback = []
        excluded = set(self.beta_columns + self.se_columns + self.t_columns)
        if self.time_column:
            excluded.add(self.time_column)
        if self.target_column:
            excluded.add(self.target_column)
        excluded.update(self.coord_columns)
        excluded.update({"predicted", "residual"})
        for column in self.coefficients.columns:
            if column in excluded:
                continue
            series = self.coefficients[column].dropna()
            if series.empty or series.nunique(dropna=True) < 2:
                continue
            normalized = str(column).strip().lower()
            if series.dtype == object or str(series.dtype).startswith("category") or str(column).startswith("Original_"):
                preferred.append(column)
            elif normalized in {"id", "name", "region", "city", "county", "district", "地点", "地区", "区域"}:
                preferred.append(column)
            elif series.nunique(dropna=True) <= 100:
                fallback.append(column)
        ordered = []
        for column in preferred + fallback:
            if column not in ordered:
                ordered.append(column)
        return ordered

    def time_value_options(self, time_column):
        if not time_column or time_column not in self.coefficients.columns:
            return []
        values = self.coefficients[time_column].dropna().drop_duplicates().tolist()
        values = self._sort_temporal_values(values)
        return [(self.format_display_value(value), value) for value in values]

    def location_value_options(self, location_column=None, x_column=None, y_column=None):
        if location_column and location_column in self.coefficients.columns:
            values = self.coefficients[location_column].dropna().drop_duplicates().tolist()
            values = self._sort_temporal_values(values)
            return [(f"{location_column}={self.format_display_value(value)}", value) for value in values]
        if not x_column or not y_column:
            return []
        if x_column not in self.coefficients.columns or y_column not in self.coefficients.columns:
            return []
        locations = self.coefficients[[x_column, y_column]].dropna().drop_duplicates().copy()
        locations = self._sort_location_frame(locations, x_column, y_column)
        return [
            (self.format_location_label(row[x_column], row[y_column], x_column, y_column), (row[x_column], row[y_column]))
            for _, row in locations.iterrows()
        ]

    def available_charts(self):
        charts = [ChartSpec("predicted_actual", "实际值 vs 预测值"), ChartSpec("residual_histogram", "残差分布")]
        if self.has_spatial() or len(self.spatial_candidate_columns()) >= 2:
            charts.extend([ChartSpec("residual_spatial", "残差空间分布"), ChartSpec("regional_residual_map", "残差区域着色图")])
        if self.metric_columns:
            charts.append(ChartSpec("coefficient_distribution", "统计量分布", requires_beta=True))
            if self.has_spatial() or len(self.spatial_candidate_columns()) >= 2:
                charts.extend([
                    ChartSpec("coefficient_spatial", "统计量空间分布", requires_beta=True),
                    ChartSpec("regional_coefficient_map", "统计量区域着色图", requires_beta=True),
                ])
            if self.has_temporal() or self.temporal_candidate_columns():
                charts.extend([
                    ChartSpec("coefficient_temporal", "统计量时间趋势", requires_beta=True),
                    ChartSpec("coefficient_3d", "统计量时间-分类 3D 图", requires_beta=True),
                ])
        if self.search_scores is not None and not self.search_scores.empty:
            charts.append(ChartSpec("search_scores", "搜索评分曲线"))
        if self.bw_history is not None and not self.bw_history.empty:
            charts.append(ChartSpec("bandwidth_history", "带宽迭代历史"))
        if self.tau_history is not None and not self.tau_history.empty:
            charts.append(ChartSpec("tau_history", "时空尺度迭代历史"))
        if self._get_summary_sequence("search_bws") or self._get_summary_sequence("search_taus"):
            charts.append(ChartSpec("final_scales", "最终尺度参数"))
        return charts

    def metric_text(self, key, decimals=4, default="--"):
        value = self.summary.get(key, default)
        if isinstance(value, (float, int, np.floating, np.integer)):
            return self.format_number(value, decimals)
        return str(value)

    def get_metric_display_names(self):
        return [(column, self.metric_display_name(column)) for column in self.metric_columns]

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

    def _get_summary_sequence(self, key):
        value = self.summary.get(key)
        return value if isinstance(value, list) else []

    @staticmethod
    def _parse_cell(value):
        if isinstance(value, str):
            text = value.strip()
            if text and text[0] in "[{":
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return value

    @staticmethod
    def _looks_temporal(series):
        text_series = series.dropna()
        if text_series.empty:
            return False
        numeric_series = pd.to_numeric(text_series, errors="coerce")
        if numeric_series.notna().mean() >= 0.8 and len(numeric_series.dropna().unique()) >= 2:
            return True
        datetime_series = pd.to_datetime(text_series.astype(str), errors="coerce", format="mixed")
        return datetime_series.notna().mean() >= 0.8

    @staticmethod
    def _sort_temporal_values(values):
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
    def _sort_location_frame(frame, x_column, y_column):
        numeric_x = pd.to_numeric(frame[x_column], errors="coerce")
        numeric_y = pd.to_numeric(frame[y_column], errors="coerce")
        if numeric_x.notna().all() and numeric_y.notna().all():
            return frame.assign(__x__=numeric_x, __y__=numeric_y).sort_values(["__x__", "__y__"]).drop(columns=["__x__", "__y__"])
        return frame.assign(__x__=frame[x_column].astype(str), __y__=frame[y_column].astype(str)).sort_values(["__x__", "__y__"]).drop(columns=["__x__", "__y__"])

    @staticmethod
    def format_number(value, decimals):
        return f"{float(value):.{max(0, int(decimals))}f}"


class ChartFactory:
    REGIONAL_CHARTS = {"regional_residual_map", "regional_coefficient_map"}
    SPATIAL_CHARTS = {"residual_spatial", "regional_residual_map", "coefficient_spatial", "regional_coefficient_map"}
    COLORMAP_CHARTS = SPATIAL_CHARTS | {"coefficient_3d"}
    TIME_SLICE_CHARTS = {
        "predicted_actual",
        "residual_histogram",
        "residual_spatial",
        "regional_residual_map",
        "coefficient_distribution",
        "coefficient_spatial",
        "regional_coefficient_map",
    }
    TIME_COLUMN_CHARTS = TIME_SLICE_CHARTS | {"coefficient_temporal", "coefficient_3d"}
    CATEGORY_CHARTS = {"coefficient_3d"}

    @classmethod
    def create_figure(cls, dataset, chart_key, beta_column=None, render_options=None):
        rc_params = {
            "font.family": cls._font_family_chain(render_options),
            "font.sans-serif": cls._font_family_chain(render_options),
            "axes.unicode_minus": False,
        }
        with matplotlib.rc_context(rc=rc_params):
            figure = Figure(figsize=cls._figure_size(render_options), tight_layout=chart_key != "coefficient_3d", facecolor="white")
            axes = figure.add_subplot(111, projection="3d") if chart_key == "coefficient_3d" else figure.add_subplot(111)
            axes.set_facecolor("#fbfcfe")
            builders = {
                "predicted_actual": cls._plot_predicted_actual,
                "residual_histogram": cls._plot_residual_histogram,
                "residual_spatial": cls._plot_residual_spatial,
                "regional_residual_map": cls._plot_regional_residual_map,
                "coefficient_distribution": cls._plot_coefficient_distribution,
                "coefficient_spatial": cls._plot_coefficient_spatial,
                "regional_coefficient_map": cls._plot_regional_coefficient_map,
                "coefficient_temporal": cls._plot_coefficient_temporal,
                "coefficient_3d": cls._plot_coefficient_3d,
                "search_scores": cls._plot_search_scores,
                "bandwidth_history": cls._plot_bandwidth_history,
                "tau_history": cls._plot_tau_history,
                "final_scales": cls._plot_final_scales,
            }
            builder = builders.get(chart_key)
            if builder is None:
                raise ValueError(f"不支持的图表类型: {chart_key}")
            builder(dataset, axes, beta_column, render_options)
            cls._apply_font_family(figure, render_options)
            cls._apply_figure_layout(figure, chart_key)
            return figure

    @classmethod
    def chart_requires_spatial_options(cls, chart_key):
        return chart_key in cls.REGIONAL_CHARTS

    @classmethod
    def chart_uses_spatial_coordinates(cls, chart_key):
        return chart_key in cls.SPATIAL_CHARTS

    @classmethod
    def chart_uses_time_column(cls, chart_key):
        return chart_key in cls.TIME_COLUMN_CHARTS

    @classmethod
    def chart_uses_time_slice(cls, chart_key):
        return chart_key in cls.TIME_SLICE_CHARTS

    @classmethod
    def chart_uses_category_column(cls, chart_key):
        return chart_key in cls.CATEGORY_CHARTS

    @classmethod
    def chart_uses_colormap(cls, chart_key):
        return chart_key in cls.COLORMAP_CHARTS

    @staticmethod
    def _plot_predicted_actual(dataset, axes, _beta_column, render_options):
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        numeric = ChartFactory._coerce_numeric_columns(coefficients, [dataset.target_column, "predicted"])
        x = numeric[dataset.target_column]
        y = numeric["predicted"]
        if numeric.empty:
            raise ValueError("实际值或预测值列没有可用于绘图的数值")
        axes.scatter(x, y, alpha=0.7, color="#0f6cbd", edgecolors="none")
        min_value = min(x.min(), y.min())
        max_value = max(x.max(), y.max())
        axes.plot([min_value, max_value], [min_value, max_value], linestyle="--", color="#c42b1c", linewidth=1.4)
        axes.set_title(ChartFactory._title(render_options, "实际值 vs 预测值"))
        axes.set_xlabel("实际值")
        axes.set_ylabel("预测值")
        axes.grid(alpha=0.18)
        ChartFactory._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @staticmethod
    def _plot_residual_histogram(dataset, axes, _beta_column, render_options):
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        residuals = pd.to_numeric(coefficients["residual"], errors="coerce").dropna()
        if residuals.empty:
            raise ValueError("残差列没有可用于绘图的数值")
        decimals = ChartFactory._decimals(render_options)
        axes.hist(residuals, bins=24, color="#0f6cbd", alpha=0.82, edgecolor="white")
        axes.axvline(
            residuals.mean(),
            color="#c42b1c",
            linestyle="--",
            linewidth=1.4,
            label=f"{ChartFactory._legend_label(render_options, '均值')} {ChartFactory._format_number(residuals.mean(), decimals)}",
        )
        axes.set_title(ChartFactory._title(render_options, "残差分布"))
        axes.set_xlabel("残差")
        axes.set_ylabel("频数")
        axes.grid(axis="y", alpha=0.18)
        axes.legend(frameon=False)

    @staticmethod
    def _plot_residual_spatial(dataset, axes, _beta_column, render_options):
        x_col, y_col = ChartFactory._resolve_coordinate_columns(dataset, render_options)
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        if ChartFactory._should_aggregate_spatial(dataset, render_options):
            coefficients = ChartFactory._aggregate_spatial_frame(coefficients, x_col, y_col, ["residual"])
        numeric = ChartFactory._coerce_numeric_columns(coefficients, [x_col, y_col, "residual"])
        if numeric.empty:
            raise ValueError("坐标列或残差列没有可用于绘图的数值")
        scatter = axes.scatter(
            numeric[x_col],
            numeric[y_col],
            c=numeric["residual"],
            cmap=ChartFactory._colormap_name(render_options),
            s=36,
            alpha=0.9,
            edgecolors="none",
        )
        title = "残差空间分布"
        if ChartFactory._should_aggregate_spatial(dataset, render_options):
            title += "（时间汇总）"
        axes.set_title(ChartFactory._title(render_options, title))
        axes.set_xlabel(str(x_col))
        axes.set_ylabel(str(y_col))
        axes.grid(alpha=0.18)
        axes.figure.colorbar(scatter, ax=axes, shrink=0.9, label=ChartFactory._legend_label(render_options, "残差"), format=ChartFactory._colorbar_format(render_options))
        ChartFactory._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @classmethod
    def _plot_regional_residual_map(cls, dataset, axes, _beta_column, render_options):
        cls._plot_regional_map(dataset, axes, "residual", "残差", ChartFactory._title(render_options, "残差区域着色图"), render_options)

    @staticmethod
    def _plot_coefficient_distribution(dataset, axes, beta_column, render_options):
        if beta_column is None:
            raise ValueError("当前图表需要选择统计量字段")
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        values = pd.to_numeric(coefficients[beta_column], errors="coerce").dropna()
        if values.empty:
            raise ValueError(f"{beta_column} 列没有可用于绘图的数值")
        decimals = ChartFactory._decimals(render_options)
        axes.hist(values, bins=24, color="#0f6cbd", alpha=0.82, edgecolor="white")
        axes.axvline(
            values.mean(),
            color="#c42b1c",
            linestyle="--",
            linewidth=1.4,
            label=f"{ChartFactory._legend_label(render_options, '均值')} {ChartFactory._format_number(values.mean(), decimals)}",
        )
        metric_label = VisualizationData.metric_display_name(beta_column)
        axes.set_title(ChartFactory._title(render_options, f"{metric_label} 分布"))
        axes.set_xlabel(VisualizationData.metric_prefix_label(beta_column))
        axes.set_ylabel("频数")
        axes.grid(axis="y", alpha=0.18)
        axes.legend(frameon=False)
        ChartFactory._apply_decimal_formatters(axes, render_options, ("x",))

    @staticmethod
    def _plot_coefficient_spatial(dataset, axes, beta_column, render_options):
        if beta_column is None:
            raise ValueError("当前图表需要选择统计量字段")
        x_col, y_col = ChartFactory._resolve_coordinate_columns(dataset, render_options)
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        if ChartFactory._should_aggregate_spatial(dataset, render_options):
            coefficients = ChartFactory._aggregate_spatial_frame(coefficients, x_col, y_col, [beta_column])
        numeric = ChartFactory._coerce_numeric_columns(coefficients, [x_col, y_col, beta_column])
        if numeric.empty:
            raise ValueError("坐标列或统计量字段没有可用于绘图的数值")
        scatter = axes.scatter(
            numeric[x_col],
            numeric[y_col],
            c=numeric[beta_column],
            cmap=ChartFactory._colormap_name(render_options),
            s=36,
            alpha=0.9,
            edgecolors="none",
        )
        metric_label = VisualizationData.metric_display_name(beta_column)
        title = f"{metric_label} 空间分布"
        if ChartFactory._should_aggregate_spatial(dataset, render_options):
            title += "（时间汇总）"
        axes.set_title(ChartFactory._title(render_options, title))
        axes.set_xlabel(str(x_col))
        axes.set_ylabel(str(y_col))
        axes.grid(alpha=0.18)
        axes.figure.colorbar(
            scatter,
            ax=axes,
            shrink=0.9,
            label=ChartFactory._legend_label(render_options, VisualizationData.metric_prefix_label(beta_column)),
            format=ChartFactory._colorbar_format(render_options),
        )
        ChartFactory._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @classmethod
    def _plot_regional_coefficient_map(cls, dataset, axes, beta_column, render_options):
        if beta_column is None:
            raise ValueError("当前图表需要选择统计量字段")
        metric_name = VisualizationData.metric_display_name(beta_column)
        cls._plot_regional_map(
            dataset,
            axes,
            beta_column,
            metric_name,
            ChartFactory._title(render_options, f"{metric_name} 区域着色图"),
            render_options,
        )

    @staticmethod
    def _plot_coefficient_temporal(dataset, axes, beta_column, render_options):
        if beta_column is None:
            raise ValueError("当前图表需要选择统计量字段")
        time_column = ChartFactory._resolve_time_column(dataset, render_options)
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=False)
        numeric = ChartFactory._coerce_numeric_columns(coefficients, [beta_column])
        if numeric.empty:
            raise ValueError(f"{beta_column} 列没有可用于绘图的数值")
        grouped = numeric.groupby(time_column, sort=False)[beta_column].mean().reset_index()
        grouped = ChartFactory._sort_frame_by_time(grouped, time_column)
        axes.plot(grouped[time_column], grouped[beta_column], color="#0f6cbd", linewidth=2.0, marker="o")
        metric_label = VisualizationData.metric_display_name(beta_column)
        title = f"{metric_label} 时间趋势"
        if ChartFactory._is_single_location_mode(render_options):
            title += f"（{ChartFactory._location_label(dataset, render_options)}）"
        axes.set_title(ChartFactory._title(render_options, title))
        axes.set_xlabel(str(time_column))
        axes.set_ylabel(f"平均{VisualizationData.metric_prefix_label(beta_column)}")
        axes.grid(alpha=0.18)
        if pd.to_numeric(grouped[time_column], errors="coerce").notna().all():
            ChartFactory._apply_decimal_formatters(axes, render_options, ("x", "y"))
        else:
            ChartFactory._apply_decimal_formatters(axes, render_options, ("y",))

    @staticmethod
    def _plot_coefficient_3d(dataset, axes, beta_column, render_options):
        if beta_column is None:
            raise ValueError("当前图表需要选择统计量字段")
        time_column = ChartFactory._resolve_time_column(dataset, render_options)
        category_column = ChartFactory._resolve_category_column(dataset, render_options)
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=False)

        data = coefficients[[time_column, category_column, beta_column]].copy().dropna(subset=[time_column, category_column, beta_column])
        data[beta_column] = pd.to_numeric(data[beta_column], errors="coerce")
        data = data.dropna(subset=[beta_column])
        if data.empty:
            raise ValueError("当前结果中没有可用于 3D 图的数据")

        time_numeric = pd.to_numeric(data[time_column], errors="coerce")
        if time_numeric.notna().all():
            data["__time__"] = time_numeric
        else:
            time_as_datetime = pd.to_datetime(data[time_column].astype(str), errors="coerce", format="mixed")
            if time_as_datetime.notna().all():
                data["__time__"] = time_as_datetime.map(pd.Timestamp.toordinal)
            else:
                categories = data[time_column].astype(str).astype("category")
                slot_width = max(1, int(render_options.time_slot_width)) if render_options is not None else 2
                data["__time__"] = categories.cat.codes * slot_width

        category_numeric = pd.to_numeric(data[category_column], errors="coerce")
        if category_numeric.notna().all():
            data["__category__"] = category_numeric
            y_tick_positions = np.sort(data["__category__"].unique())
            y_tick_labels = [VisualizationData.format_display_value(value) for value in y_tick_positions]
        else:
            categories = data[category_column].astype("category")
            slot_width = max(1, int(render_options.category_slot_width)) if render_options is not None else 2
            data["__category__"] = categories.cat.codes * slot_width
            y_tick_positions = data["__category__"].drop_duplicates().tolist()
            y_tick_labels = [str(value) for value in categories.cat.categories]

        scatter = axes.scatter(
            data["__time__"],
            data["__category__"],
            data[beta_column],
            c=data[beta_column],
            cmap=ChartFactory._colormap_name(render_options),
            linewidths=0.8,
            marker="o",
        )

        time_ticks_source = VisualizationData._sort_temporal_values(data[time_column].drop_duplicates().tolist())
        if len(time_ticks_source) <= 15:
            time_tick_values = []
            for value in time_ticks_source:
                mask = data[time_column].astype(str) == str(value)
                if mask.any():
                    time_tick_values.append(data.loc[mask, "__time__"].iloc[0])
            axes.set_xticks(time_tick_values)
            axes.set_xticklabels([VisualizationData.format_display_value(value) for value in time_ticks_source], rotation=45, ha="right", fontsize=8)

        axes.set_yticks(y_tick_positions)
        axes.set_yticklabels(y_tick_labels, rotation=90, ha="right", fontsize=8)
        axes.set_xlabel(str(time_column), labelpad=16)
        axes.set_ylabel(str(category_column), labelpad=20)
        metric_label = VisualizationData.metric_display_name(beta_column)
        axes.set_zlabel(metric_label, labelpad=10)
        axes.set_title(ChartFactory._title(render_options, f"{metric_label} 时间-分类 3D 图"))
        axes.set_box_aspect(ChartFactory._box_aspect(render_options))
        axes.view_init(elev=10, azim=-35)
        axes.zaxis.set_major_formatter(FuncFormatter(ChartFactory._formatter_fn(render_options)))
        if pd.to_numeric(data[time_column], errors="coerce").notna().all():
            axes.xaxis.set_major_formatter(FuncFormatter(ChartFactory._formatter_fn(render_options)))
        if pd.to_numeric(data[category_column], errors="coerce").notna().all():
            axes.yaxis.set_major_formatter(FuncFormatter(ChartFactory._formatter_fn(render_options)))
        axes.figure.colorbar(
            scatter,
            ax=axes,
            shrink=0.45,
            aspect=20,
            pad=0.1,
            label=ChartFactory._legend_label(render_options, metric_label),
            format=ChartFactory._colorbar_format(render_options),
        )

    @staticmethod
    def _plot_search_scores(dataset, axes, _beta_column, _render_options):
        score_series = dataset.search_scores.iloc[:, 0]
        axes.plot(range(1, len(score_series) + 1), score_series, color="#0f6cbd", linewidth=2.0)
        axes.set_title(ChartFactory._title(_render_options, "搜索评分曲线"))
        axes.set_xlabel("迭代步")
        axes.set_ylabel("评分")
        axes.grid(alpha=0.18)

    @staticmethod
    def _plot_bandwidth_history(dataset, axes, _beta_column, _render_options):
        history = dataset.bw_history.copy()
        history.columns = [f"bw_{index + 1}" for index in range(history.shape[1])]
        for column in history.columns:
            axes.plot(range(1, len(history) + 1), history[column], linewidth=1.6, label=column)
        axes.set_title(ChartFactory._title(_render_options, "带宽迭代历史"))
        axes.set_xlabel("迭代步")
        axes.set_ylabel("带宽")
        axes.grid(alpha=0.18)
        axes.legend(frameon=False, ncol=min(3, len(history.columns)))

    @staticmethod
    def _plot_tau_history(dataset, axes, _beta_column, _render_options):
        history = dataset.tau_history.copy()
        history.columns = [f"tau_{index + 1}" for index in range(history.shape[1])]
        for column in history.columns:
            axes.plot(range(1, len(history) + 1), history[column], linewidth=1.6, label=column)
        axes.set_title(ChartFactory._title(_render_options, "时空尺度迭代历史"))
        axes.set_xlabel("迭代步")
        axes.set_ylabel("时空尺度")
        axes.grid(alpha=0.18)
        axes.legend(frameon=False, ncol=min(3, len(history.columns)))

    @staticmethod
    def _plot_final_scales(dataset, axes, _beta_column, render_options):
        bws = dataset._get_summary_sequence("search_bws")
        taus = dataset._get_summary_sequence("search_taus")
        count = max(len(bws), len(taus), 1)
        labels = list(dataset.variable_names) if dataset.variable_names else []
        if len(labels) < count:
            labels.extend([f"v{i + 1}" for i in range(len(labels), count)])
        positions = list(range(count))
        width = 0.36
        if bws:
            axes.bar([p - width / 2 for p in positions[:len(bws)]], bws, width=width, label="带宽", color="#0f6cbd")
        if taus:
            axes.bar([p + width / 2 for p in positions[:len(taus)]], taus, width=width, label="时空尺度", color="#8764b8")
        axes.set_xticks(positions[:count])
        axes.set_xticklabels(labels[:count], rotation=25, ha="right")
        axes.set_title(ChartFactory._title(render_options, "最终尺度参数"))
        axes.set_ylabel("参数值")
        axes.grid(axis="y", alpha=0.18)
        axes.legend(frameon=False)

    @classmethod
    def _plot_regional_map(cls, dataset, axes, value_column, display_name, title, render_options):
        if render_options is None or not render_options.vector_path:
            raise ValueError("区域着色图需要先加载 shp / geojson / gpkg 边界文件")
        if value_column not in dataset.coefficients.columns:
            raise ValueError(f"结果文件中缺少字段: {value_column}")
        gpd, rasterio, raster_show, CRS = cls._load_spatial_dependencies()
        projection = cls._resolve_projection(render_options, CRS)
        polygon_layer = cls._load_polygon_layer(gpd, render_options.vector_path, projection)
        joined_points = cls._join_points_to_polygons(dataset, gpd, projection, polygon_layer, value_column, render_options)
        aggregated = joined_points.groupby("index_right")[value_column].mean()
        polygon_layer["__value__"] = polygon_layer.index.map(aggregated)
        valid_polygons = polygon_layer.dropna(subset=["__value__"]).copy()
        if valid_polygons.empty:
            raise ValueError("没有点落入提供的矢量范围，请检查坐标列、时间切片和投影设置")

        bins, class_ids = cls._classify_values(valid_polygons["__value__"].to_numpy(dtype=float), render_options.class_count, render_options.stretch_method)
        valid_polygons["__class__"] = class_ids
        if render_options.raster_path:
            cls._draw_raster_background(axes, render_options.raster_path, projection, rasterio, raster_show, CRS)
        missing_polygons = polygon_layer[polygon_layer["__value__"].isna()]
        if not missing_polygons.empty:
            missing_polygons.plot(ax=axes, color="#eef2f7", edgecolor="#cbd5e1", linewidth=0.6, zorder=1)

        palette_colors = cls._build_palette(render_options.palette, len(bins) - 1)
        legend_handles = []
        for class_index, color in enumerate(palette_colors):
            subset = valid_polygons[valid_polygons["__class__"] == class_index]
            if subset.empty:
                continue
            subset.plot(ax=axes, color=color, edgecolor="#ffffff", linewidth=0.8, zorder=2)
            legend_handles.append(Patch(facecolor=color, edgecolor="none", label=cls._format_bin_label(bins, class_index, cls._decimals(render_options))))

        axes.set_title(title)
        axes.set_axis_off()
        if legend_handles:
            axes.legend(handles=legend_handles, title=f"{display_name} ({cls._stretch_label(render_options.stretch_method)})", loc="lower left", frameon=False)

    @staticmethod
    def _load_spatial_dependencies():
        try:
            import geopandas as gpd
            import rasterio
            from pyproj import CRS
            from rasterio.plot import show as raster_show
        except ImportError as exc:
            raise RuntimeError("区域着色图依赖 geopandas、shapely、pyproj、rasterio，请先安装 requirements 中新增的空间库") from exc
        return gpd, rasterio, raster_show, CRS

    @staticmethod
    def _resolve_projection(render_options, CRS):
        projection = (render_options.projection or "").strip()
        if not projection:
            raise ValueError("请先选择投影")
        return CRS.from_user_input(projection)

    @staticmethod
    def _load_polygon_layer(gpd, vector_path, projection):
        polygon_layer = gpd.read_file(vector_path)
        if polygon_layer.empty:
            raise ValueError("边界文件为空，无法生成区域着色图")
        polygon_layer = polygon_layer[polygon_layer.geometry.notna()].copy()
        polygon_layer = polygon_layer[polygon_layer.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        if polygon_layer.empty:
            raise ValueError("边界文件中没有可用的面要素")
        if polygon_layer.crs is None:
            polygon_layer = polygon_layer.set_crs(projection)
        else:
            polygon_layer = polygon_layer.to_crs(projection)
        return polygon_layer

    @staticmethod
    def _join_points_to_polygons(dataset, gpd, projection, polygon_layer, value_column, render_options):
        coefficients = ChartFactory._filtered_coefficients(dataset, render_options, apply_time_slice=True)
        x_col, y_col = ChartFactory._resolve_coordinate_columns(dataset, render_options)
        if ChartFactory._should_aggregate_spatial(dataset, render_options):
            coefficients = ChartFactory._aggregate_spatial_frame(coefficients, x_col, y_col, [value_column])
        points = coefficients[[x_col, y_col, value_column]].copy()
        points[x_col] = pd.to_numeric(points[x_col], errors="coerce")
        points[y_col] = pd.to_numeric(points[y_col], errors="coerce")
        points[value_column] = pd.to_numeric(points[value_column], errors="coerce")
        points = points.dropna(subset=[x_col, y_col, value_column])
        if points.empty:
            raise ValueError("可视化结果中没有可用的空间点数据")
        point_layer = gpd.GeoDataFrame(points, geometry=gpd.points_from_xy(points[x_col], points[y_col]), crs=projection)
        joined = gpd.sjoin(point_layer, polygon_layer[["geometry"]], how="inner", predicate="within")
        if joined.empty:
            joined = gpd.sjoin(point_layer, polygon_layer[["geometry"]], how="inner", predicate="intersects")
        if joined.empty:
            raise ValueError("当前坐标未匹配到任何矢量区域")
        return joined

    @staticmethod
    def _coerce_numeric_columns(frame, columns):
        numeric = frame.copy()
        for column in columns:
            numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
        return numeric.dropna(subset=columns)

    @staticmethod
    def _sort_frame_by_time(frame, time_column):
        numeric_series = pd.to_numeric(frame[time_column], errors="coerce")
        if numeric_series.notna().all():
            return frame.assign(__sort__=numeric_series).sort_values("__sort__").drop(columns="__sort__")
        datetime_series = pd.to_datetime(frame[time_column].astype(str), errors="coerce", format="mixed")
        if datetime_series.notna().all():
            return frame.assign(__sort__=datetime_series).sort_values("__sort__").drop(columns="__sort__")
        return frame.assign(__sort__=frame[time_column].astype(str)).sort_values("__sort__").drop(columns="__sort__")

    @staticmethod
    def _resolve_coordinate_columns(dataset, render_options):
        if render_options is not None and render_options.longitude_column and render_options.latitude_column:
            x_col = render_options.longitude_column
            y_col = render_options.latitude_column
        elif len(dataset.coord_columns) >= 2:
            x_col, y_col = dataset.coord_columns[:2]
        else:
            raise ValueError("请先指定结果表中的经度列和纬度列")
        missing_columns = [column for column in (x_col, y_col) if column not in dataset.coefficients.columns]
        if missing_columns:
            raise ValueError(f"结果文件中缺少坐标列: {', '.join(map(str, missing_columns))}")
        if x_col == y_col:
            raise ValueError("经度列和纬度列不能相同")
        return x_col, y_col

    @staticmethod
    def _resolve_time_column(dataset, render_options):
        time_column = render_options.time_column if render_options is not None and render_options.time_column else dataset.time_column
        if not time_column:
            raise ValueError("请先指定时间列")
        if time_column not in dataset.coefficients.columns:
            raise ValueError(f"结果文件中缺少时间列: {time_column}")
        return time_column

    @staticmethod
    def _resolve_category_column(dataset, render_options):
        if render_options is not None and render_options.category_column:
            category_column = render_options.category_column
        else:
            candidates = dataset.category_candidate_columns()
            if not candidates:
                raise ValueError("结果表中没有可用于 3D 图的分类列")
            category_column = candidates[0]
        if category_column not in dataset.coefficients.columns:
            raise ValueError(f"结果文件中缺少分类列: {category_column}")
        return category_column

    @staticmethod
    def _filtered_coefficients(dataset, render_options, apply_time_slice):
        coefficients = dataset.coefficients.copy()
        coefficients = ChartFactory._apply_location_filter(coefficients, dataset, render_options)
        if (
            not apply_time_slice
            or render_options is None
            or render_options.time_value is None
            or ChartFactory._should_aggregate_spatial(dataset, render_options)
        ):
            return coefficients
        time_column = ChartFactory._resolve_time_column(dataset, render_options)
        filtered = coefficients.loc[ChartFactory._series_matches_value(coefficients[time_column], render_options.time_value)].copy()
        if filtered.empty:
            raise ValueError(f"时间点 {render_options.time_value} 没有对应数据")
        return filtered

    @staticmethod
    def _series_matches_value(series, value):
        if isinstance(value, pd.Timestamp):
            converted = pd.to_datetime(series, errors="coerce", format="mixed")
            return converted == value
        return (series == value) | (series.astype(str) == str(value))

    @staticmethod
    def _is_single_location_mode(render_options):
        return bool(render_options is not None and render_options.temporal_mode == "single_location" and render_options.location_value is not None)

    @staticmethod
    def _should_aggregate_spatial(dataset, render_options):
        return bool(dataset.has_temporal() and render_options is not None and render_options.spatial_mode == "aggregate_time")

    @classmethod
    def _apply_location_filter(cls, frame, dataset, render_options):
        if not cls._is_single_location_mode(render_options):
            return frame
        if render_options.location_column:
            if render_options.location_column not in frame.columns:
                raise ValueError(f"结果文件中缺少地点字段: {render_options.location_column}")
            mask = cls._series_matches_value(frame[render_options.location_column], render_options.location_value)
            filtered = frame.loc[mask].copy()
            if filtered.empty:
                raise ValueError("所选地点没有对应数据")
            return filtered
        x_col, y_col = cls._resolve_coordinate_columns(dataset, render_options)
        x_value, y_value = render_options.location_value
        mask = cls._series_matches_value(frame[x_col], x_value) & cls._series_matches_value(frame[y_col], y_value)
        filtered = frame.loc[mask].copy()
        if filtered.empty:
            raise ValueError("所选地点没有对应数据")
        return filtered

    @staticmethod
    def _aggregate_spatial_frame(frame, x_col, y_col, value_columns):
        aggregated = frame[[x_col, y_col] + value_columns].copy()
        aggregated[x_col] = pd.to_numeric(aggregated[x_col], errors="coerce")
        aggregated[y_col] = pd.to_numeric(aggregated[y_col], errors="coerce")
        for column in value_columns:
            aggregated[column] = pd.to_numeric(aggregated[column], errors="coerce")
        aggregated = aggregated.dropna(subset=[x_col, y_col] + value_columns)
        if aggregated.empty:
            return aggregated
        return aggregated.groupby([x_col, y_col], as_index=False)[value_columns].mean()

    @staticmethod
    def _location_label(dataset, render_options):
        if render_options is None or render_options.location_value is None:
            return "地点"
        if render_options.location_column:
            return f"{render_options.location_column}={VisualizationData.format_display_value(render_options.location_value)}"
        x_col = render_options.longitude_column or (dataset.coord_columns[0] if len(dataset.coord_columns) >= 1 else "X")
        y_col = render_options.latitude_column or (dataset.coord_columns[1] if len(dataset.coord_columns) >= 2 else "Y")
        x_value, y_value = render_options.location_value
        return VisualizationData.format_location_label(x_value, y_value, x_col, y_col)

    @staticmethod
    def _draw_raster_background(axes, raster_path, projection, rasterio, raster_show, CRS):
        with rasterio.open(raster_path) as dataset:
            raster_crs = dataset.crs
            if raster_crs is not None and CRS.from_user_input(raster_crs) != projection:
                raise ValueError("栅格坐标系与当前投影不一致，请切换投影后重试")
            raster_show(dataset, ax=axes, alpha=0.35, zorder=0)

    @staticmethod
    def _classify_values(values, class_count, stretch_method):
        series = np.asarray(values, dtype=float)
        if series.size == 0:
            raise ValueError("没有可用于分级的数值")
        target_classes = max(2, min(int(class_count), len(np.unique(series))))
        if stretch_method == "equal_interval":
            bins = np.linspace(series.min(), series.max(), target_classes + 1)
        elif stretch_method == "quantile":
            bins = np.quantile(series, np.linspace(0, 1, target_classes + 1))
        elif stretch_method == "log":
            shifted = series - series.min() + 1e-9
            bins = np.exp(np.linspace(np.log(shifted.min()), np.log(shifted.max()), target_classes + 1))
            bins = bins + series.min() - 1e-9
        elif stretch_method == "jenks":
            bins = np.asarray(ChartFactory._jenks_breaks(series, target_classes), dtype=float)
        else:
            raise ValueError(f"不支持的分级方式: {stretch_method}")
        bins = np.unique(np.round(bins, 12))
        if len(bins) < 2:
            bins = np.array([series.min(), series.max() + 1e-9], dtype=float)
        if len(bins) - 1 < 1:
            raise ValueError("分级结果无效，请尝试其他分级方式")
        return bins, np.digitize(series, bins[1:-1], right=True)

    @staticmethod
    def _build_palette(palette_name, count):
        color_map = colormaps.get_cmap(palette_name)
        if count <= 1:
            return [color_map(0.6)]
        return [color_map(position) for position in np.linspace(0.15, 0.92, count)]

    @staticmethod
    def _format_bin_label(bins, index, decimals):
        return f"{bins[index]:.{decimals}f} - {bins[index + 1]:.{decimals}f}"

    @staticmethod
    def _stretch_label(stretch_method):
        labels = {"equal_interval": "等距", "quantile": "分位数", "jenks": "自然断点", "log": "对数拉伸"}
        return labels.get(stretch_method, stretch_method)

    @staticmethod
    def _format_number(value, decimals):
        return f"{float(value):.{max(0, int(decimals))}f}"

    @staticmethod
    def _decimals(render_options):
        return max(0, int(render_options.decimal_places)) if render_options is not None else 4

    @staticmethod
    def _colorbar_format(render_options):
        return f"%.{ChartFactory._decimals(render_options)}f"

    @staticmethod
    def _colormap_name(render_options):
        if render_options is not None and render_options.palette:
            return render_options.palette
        return "viridis"

    @staticmethod
    def _box_aspect(render_options):
        if render_options is None:
            return [1, 3, 1]
        return [
            max(0.1, float(render_options.x_box_aspect)),
            max(0.1, float(render_options.y_box_aspect)),
            max(0.1, float(render_options.z_box_aspect)),
        ]

    @staticmethod
    def _figure_size(render_options):
        if render_options is None:
            return (8.0, 5.0)
        return (
            max(1.0, float(render_options.figure_width)),
            max(1.0, float(render_options.figure_height)),
        )

    @staticmethod
    def _formatter_fn(render_options):
        decimals = ChartFactory._decimals(render_options)
        return lambda value, _pos: f"{float(value):.{decimals}f}"

    @staticmethod
    def _apply_decimal_formatters(axes, render_options, axis_names):
        formatter = FuncFormatter(ChartFactory._formatter_fn(render_options))
        if "x" in axis_names:
            axes.xaxis.set_major_formatter(formatter)
        if "y" in axis_names:
            axes.yaxis.set_major_formatter(formatter)
        if "z" in axis_names and hasattr(axes, "zaxis"):
            axes.zaxis.set_major_formatter(formatter)

    @staticmethod
    def _apply_font_family(figure, render_options):
        font_families = ChartFactory._font_family_chain(render_options)
        for text in figure.findobj(match=lambda artist: isinstance(artist, mtext.Text)):
            text.set_fontfamily(font_families)

    @staticmethod
    def _font_family_chain(render_options):
        preferred = []
        if render_options is not None and render_options.font_family:
            preferred.append(render_options.font_family)
        preferred.extend(DEFAULT_FONT_FALLBACKS)
        ordered = []
        for family in preferred:
            if family and family not in ordered:
                ordered.append(family)
        return ordered

    @staticmethod
    def _apply_figure_layout(figure, chart_key):
        if chart_key == "coefficient_3d":
            figure.subplots_adjust(left=0.08, right=0.9, bottom=0.14, top=0.9)

    @staticmethod
    def _title(render_options, default):
        if render_options is not None and render_options.figure_title:
            return render_options.figure_title
        return default

    @staticmethod
    def _legend_label(render_options, default):
        if render_options is not None and render_options.legend_label:
            return render_options.legend_label
        return default

    @staticmethod
    def _jenks_breaks(values, class_count):
        sorted_values = np.sort(np.asarray(values, dtype=float))
        n = len(sorted_values)
        if class_count <= 1 or n <= 1:
            return [sorted_values[0], sorted_values[-1]]
        mat1 = np.zeros((n + 1, class_count + 1), dtype=int)
        mat2 = np.full((n + 1, class_count + 1), np.inf, dtype=float)
        for level in range(1, class_count + 1):
            mat1[1, level] = 1
            mat2[1, level] = 0.0
        variance = 0.0
        for length in range(2, n + 1):
            sum_values = 0.0
            sum_squares = 0.0
            weight = 0.0
            for width in range(1, length + 1):
                index = length - width + 1
                value = sorted_values[index - 1]
                weight += 1.0
                sum_values += value
                sum_squares += value * value
                variance = sum_squares - (sum_values * sum_values) / weight
                lower_index = index - 1
                if lower_index != 0:
                    for level in range(2, class_count + 1):
                        candidate = variance + mat2[lower_index, level - 1]
                        if mat2[length, level] >= candidate:
                            mat1[length, level] = index
                            mat2[length, level] = candidate
            mat1[length, 1] = 1
            mat2[length, 1] = variance
        breaks = [0.0] * (class_count + 1)
        breaks[class_count] = sorted_values[-1]
        breaks[0] = sorted_values[0]
        count = class_count
        position = n
        while count > 1:
            index = mat1[position, count] - 1
            breaks[count - 1] = sorted_values[index]
            position = mat1[position, count] - 1
            count -= 1
        return breaks

