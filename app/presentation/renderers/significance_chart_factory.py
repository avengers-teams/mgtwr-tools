from __future__ import annotations

import matplotlib
import pandas as pd
from matplotlib import text as mtext
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from app.application.dto.significance import SignificanceRenderOptions
from app.core.config import DEFAULT_FONT_FALLBACKS
from app.domain.models.chart_spec import ChartSpec
from app.domain.policies.significance_policy import SignificancePolicy

matplotlib.rcParams["axes.unicode_minus"] = False


class SignificanceChartFactory:
    @classmethod
    def available_charts(cls, dataset):
        charts = [ChartSpec("summary", "显著性占比")]
        if dataset.has_spatial() or len(dataset.spatial_candidate_columns()) >= 2:
            charts.append(ChartSpec("spatial", "显著性空间分布"))
            if dataset.beta_columns:
                charts.append(ChartSpec("coefficient_spatial", "显著系数空间图", requires_beta=True))
        if dataset.has_temporal() or dataset.temporal_candidate_columns():
            charts.append(ChartSpec("temporal", "显著性时间趋势"))
            if dataset.beta_columns:
                charts.append(ChartSpec("coefficient_temporal", "显著系数时间趋势", requires_beta=True))
        return charts

    @classmethod
    def create_figure(cls, dataset, t_column: str, chart_key: str, render_options: SignificanceRenderOptions):
        rc_params = {
            "font.family": cls._font_family_chain(render_options),
            "font.sans-serif": cls._font_family_chain(render_options),
            "axes.unicode_minus": False,
        }
        with matplotlib.rc_context(rc=rc_params):
            figure = Figure(figsize=(8.0, 5.0), tight_layout=True, facecolor="white")
            axes = figure.add_subplot(111)
            axes.set_facecolor("#fbfcfe")
            builders = {
                "summary": cls._plot_summary,
                "spatial": cls._plot_spatial,
                "temporal": cls._plot_temporal,
                "coefficient_spatial": cls._plot_coefficient_spatial,
                "coefficient_temporal": cls._plot_coefficient_temporal,
            }
            builder = builders.get(chart_key)
            if builder is None:
                raise ValueError(f"不支持的显著性图表: {chart_key}")
            builder(dataset, axes, t_column, render_options)
            cls._apply_font_family(figure, render_options)
            return figure

    @classmethod
    def _plot_summary(cls, dataset, axes, t_column, render_options):
        stats = SignificancePolicy.significance_stats(dataset, t_column, render_options, cls._filtered_coefficients)
        counts = [stats.total_significant, stats.total - stats.total_significant]
        labels = ["显著", "不显著"]
        colors = ["#0f6cbd", "#cbd5e1"]
        bars = axes.bar(labels, counts, color=colors, width=0.55)
        for bar, value in zip(bars, counts):
            axes.text(bar.get_x() + bar.get_width() / 2, value, str(value), ha="center", va="bottom")
        ratio = counts[0] / max(1, sum(counts))
        axes.set_ylim(0, max(counts) * 1.2 if counts else 1)
        axes.set_title(cls._title(render_options, f"{dataset.metric_base_name(t_column)} 显著性占比"))
        axes.set_ylabel("样本数")
        axes.grid(axis="y", alpha=0.18)
        axes.text(
            0.98,
            0.94,
            f"|t| >= {cls._format_number(render_options.threshold, render_options.decimal_places)}\n显著占比: {ratio:.1%}",
            transform=axes.transAxes,
            ha="right",
            va="top",
            bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#d6dfeb"},
        )

    @classmethod
    def _plot_spatial(cls, dataset, axes, t_column, render_options):
        x_col, y_col = cls._resolve_coordinate_columns(dataset, render_options)
        frame = cls._filtered_coefficients(dataset, render_options)
        if cls._should_aggregate_spatial(dataset, render_options):
            frame = cls._aggregate_spatial_frame(frame, x_col, y_col, [t_column])
        spatial = frame[[x_col, y_col, t_column]].copy()
        spatial[x_col] = pd.to_numeric(spatial[x_col], errors="coerce")
        spatial[y_col] = pd.to_numeric(spatial[y_col], errors="coerce")
        spatial[t_column] = pd.to_numeric(spatial[t_column], errors="coerce")
        spatial = spatial.dropna(subset=[x_col, y_col, t_column])
        if spatial.empty:
            raise ValueError("坐标列或 t 值列没有可用于绘图的数值")

        flags = SignificancePolicy.significance_flags(spatial[t_column], render_options.threshold)
        sig = spatial.loc[flags]
        nonsig = spatial.loc[~flags]

        if not nonsig.empty:
            axes.scatter(nonsig[x_col], nonsig[y_col], s=28, c="#cbd5e1", label="不显著", alpha=0.85, edgecolors="none")
        if not sig.empty:
            axes.scatter(sig[x_col], sig[y_col], s=32, c="#0f6cbd", label="显著", alpha=0.92, edgecolors="none")

        title = f"{dataset.metric_base_name(t_column)} 显著性空间分布"
        if cls._should_aggregate_spatial(dataset, render_options):
            title += "（时间汇总）"
        axes.set_title(cls._title(render_options, title))
        axes.set_xlabel(str(x_col))
        axes.set_ylabel(str(y_col))
        axes.grid(alpha=0.18)
        axes.legend(frameon=False)
        cls._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @classmethod
    def _plot_temporal(cls, dataset, axes, t_column, render_options):
        frame = cls._filtered_coefficients(dataset, render_options, apply_time_slice=False)
        time_column = cls._resolve_time_column(dataset, render_options)
        data = frame[[time_column, t_column]].copy()
        data[t_column] = pd.to_numeric(data[t_column], errors="coerce")
        data = data.dropna(subset=[time_column, t_column])
        if data.empty:
            raise ValueError("时间列或 t 值列没有可用于绘图的数值")
        data["__significant__"] = SignificancePolicy.significance_flags(data[t_column], render_options.threshold).astype(float)
        grouped = data.groupby(time_column, sort=False)["__significant__"].mean().reset_index()
        grouped = cls._sort_frame_by_time(grouped, time_column)
        axes.plot(grouped[time_column], grouped["__significant__"], color="#0f6cbd", linewidth=2.0, marker="o")
        axes.set_ylim(0, 1.05)
        title = f"{dataset.metric_base_name(t_column)} 显著性时间趋势"
        if cls._is_single_location_mode(render_options):
            title += f"（{cls._location_label(dataset, render_options)}）"
        axes.set_title(cls._title(render_options, title))
        axes.set_xlabel(str(time_column))
        axes.set_ylabel("显著占比")
        axes.grid(alpha=0.18)
        if pd.to_numeric(grouped[time_column], errors="coerce").notna().all():
            cls._apply_decimal_formatters(axes, render_options, ("x",))

    @classmethod
    def _plot_coefficient_spatial(cls, dataset, axes, t_column, render_options):
        beta_column = SignificancePolicy.resolve_linked_beta_column(dataset, t_column, render_options)
        x_col, y_col = cls._resolve_coordinate_columns(dataset, render_options)
        frame = cls._filtered_coefficients(dataset, render_options)
        if cls._should_aggregate_spatial(dataset, render_options):
            frame = cls._aggregate_spatial_frame(frame, x_col, y_col, [t_column, beta_column])
        data = frame[[x_col, y_col, t_column, beta_column]].copy()
        data[x_col] = pd.to_numeric(data[x_col], errors="coerce")
        data[y_col] = pd.to_numeric(data[y_col], errors="coerce")
        data[t_column] = pd.to_numeric(data[t_column], errors="coerce")
        data[beta_column] = pd.to_numeric(data[beta_column], errors="coerce")
        data = data.dropna(subset=[x_col, y_col, t_column, beta_column])
        if data.empty:
            raise ValueError("坐标列、t 值列或系数列没有可用于绘图的数值")

        flags = SignificancePolicy.significance_flags(data[t_column], render_options.threshold)
        sig = data.loc[flags]
        nonsig = data.loc[~flags]

        if not nonsig.empty:
            axes.scatter(nonsig[x_col], nonsig[y_col], s=24, c="#d5dbe5", label="不显著", alpha=0.7, edgecolors="none")
        scatter = None
        if not sig.empty:
            scatter = axes.scatter(
                sig[x_col],
                sig[y_col],
                s=34,
                c=sig[beta_column],
                cmap="RdBu_r",
                label="显著",
                alpha=0.95,
                edgecolors="none",
            )

        metric_name = dataset.metric_base_name(beta_column)
        title = f"{metric_name} 显著系数空间图"
        if cls._should_aggregate_spatial(dataset, render_options):
            title += "（时间汇总）"
        axes.set_title(cls._title(render_options, title))
        axes.set_xlabel(str(x_col))
        axes.set_ylabel(str(y_col))
        axes.grid(alpha=0.18)
        axes.legend(frameon=False)
        if scatter is not None:
            axes.figure.colorbar(scatter, ax=axes, shrink=0.9, label=f"显著系数 | {metric_name}")
        cls._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @classmethod
    def _plot_coefficient_temporal(cls, dataset, axes, t_column, render_options):
        beta_column = SignificancePolicy.resolve_linked_beta_column(dataset, t_column, render_options)
        time_column = cls._resolve_time_column(dataset, render_options)
        frame = cls._filtered_coefficients(dataset, render_options, apply_time_slice=False)
        data = frame[[time_column, t_column, beta_column]].copy()
        data[t_column] = pd.to_numeric(data[t_column], errors="coerce")
        data[beta_column] = pd.to_numeric(data[beta_column], errors="coerce")
        data = data.dropna(subset=[time_column, t_column, beta_column])
        if data.empty:
            raise ValueError("时间列、t 值列或系数列没有可用于绘图的数值")

        data["__significant__"] = SignificancePolicy.significance_flags(data[t_column], render_options.threshold)
        all_grouped = data.groupby(time_column, sort=False)[beta_column].mean().reset_index(name="__all__")
        sig_grouped = data.loc[data["__significant__"]].groupby(time_column, sort=False)[beta_column].mean().reset_index(name="__sig__")
        grouped = all_grouped.merge(sig_grouped, on=time_column, how="left")
        grouped = cls._sort_frame_by_time(grouped, time_column)

        axes.plot(grouped[time_column], grouped["__all__"], color="#94a3b8", linewidth=1.8, marker="o", label="全部样本")
        axes.plot(grouped[time_column], grouped["__sig__"], color="#0f6cbd", linewidth=2.2, marker="o", label="显著样本")
        title = f"{dataset.metric_base_name(beta_column)} 显著系数时间趋势"
        if cls._is_single_location_mode(render_options):
            title += f"（{cls._location_label(dataset, render_options)}）"
        axes.set_title(cls._title(render_options, title))
        axes.set_xlabel(str(time_column))
        axes.set_ylabel("平均系数")
        axes.grid(alpha=0.18)
        axes.legend(frameon=False)
        if pd.to_numeric(grouped[time_column], errors="coerce").notna().all():
            cls._apply_decimal_formatters(axes, render_options, ("x", "y"))
        else:
            cls._apply_decimal_formatters(axes, render_options, ("y",))

    @staticmethod
    def _filtered_coefficients(dataset, render_options, apply_time_slice=True):
        frame = dataset.coefficients.copy()
        frame = SignificanceChartFactory._apply_location_filter(frame, dataset, render_options)
        if (
            not apply_time_slice
            or not render_options
            or render_options.time_value is None
            or SignificanceChartFactory._should_aggregate_spatial(dataset, render_options)
        ):
            return frame
        time_column = SignificanceChartFactory._resolve_time_column(dataset, render_options)
        filtered = frame.loc[SignificanceChartFactory._series_matches_value(frame[time_column], render_options.time_value)].copy()
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
        x_col = render_options.longitude_column or (dataset.coord_columns[0] if len(dataset.coord_columns) >= 1 else "X")
        y_col = render_options.latitude_column or (dataset.coord_columns[1] if len(dataset.coord_columns) >= 2 else "Y")
        x_value, y_value = render_options.location_value
        return dataset.format_location_label(x_value, y_value, x_col, y_col)

    @staticmethod
    def _resolve_coordinate_columns(dataset, render_options):
        if render_options and render_options.longitude_column and render_options.latitude_column:
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
        time_column = render_options.time_column if render_options and render_options.time_column else dataset.time_column
        if not time_column:
            raise ValueError("请先指定时间列")
        if time_column not in dataset.coefficients.columns:
            raise ValueError(f"结果文件中缺少时间列: {time_column}")
        return time_column

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
    def _format_number(value, decimals):
        return f"{float(value):.{max(0, int(decimals))}f}"

    @staticmethod
    def _apply_decimal_formatters(axes, render_options, axis_names):
        decimals = max(0, int(render_options.decimal_places)) if render_options is not None else 4
        formatter = FuncFormatter(lambda value, _pos: f"{float(value):.{decimals}f}")
        if "x" in axis_names:
            axes.xaxis.set_major_formatter(formatter)
        if "y" in axis_names:
            axes.yaxis.set_major_formatter(formatter)

    @staticmethod
    def _font_family_chain(render_options):
        preferred = []
        if render_options and render_options.font_family:
            preferred.append(render_options.font_family)
        preferred.extend(DEFAULT_FONT_FALLBACKS)
        ordered = []
        for family in preferred:
            if family and family not in ordered:
                ordered.append(family)
        return ordered

    @staticmethod
    def _apply_font_family(figure, render_options):
        font_families = SignificanceChartFactory._font_family_chain(render_options)
        for text in figure.findobj(match=lambda artist: isinstance(artist, mtext.Text)):
            text.set_fontfamily(font_families)

    @staticmethod
    def _title(render_options, default):
        if render_options and render_options.figure_title:
            return render_options.figure_title
        return default

