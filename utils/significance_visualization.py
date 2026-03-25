from __future__ import annotations

from dataclasses import dataclass

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from utils.model_visualization import DEFAULT_FONT_FALLBACKS, ChartFactory, VisualizationData

matplotlib.rcParams["axes.unicode_minus"] = False


@dataclass
class SignificanceChartSpec:
    key: str
    label: str


@dataclass
class SignificanceRenderOptions:
    threshold: float = 1.96
    longitude_column: str | None = None
    latitude_column: str | None = None
    time_column: str | None = None
    time_value: str | None = None
    figure_title: str | None = None
    decimal_places: int = 4
    font_family: str | None = "Microsoft YaHei"


class SignificanceChartFactory:
    @classmethod
    def available_charts(cls, dataset: VisualizationData):
        charts = [SignificanceChartSpec("summary", "显著性占比")]
        if dataset.has_spatial() or len(dataset.spatial_candidate_columns()) >= 2:
            charts.append(SignificanceChartSpec("spatial", "显著性空间分布"))
        if dataset.has_temporal() or dataset.temporal_candidate_columns():
            charts.append(SignificanceChartSpec("temporal", "显著性时间趋势"))
        return charts

    @classmethod
    def create_figure(cls, dataset: VisualizationData, t_column: str, chart_key: str, render_options: SignificanceRenderOptions):
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
            }
            builder = builders.get(chart_key)
            if builder is None:
                raise ValueError(f"不支持的显著性图表: {chart_key}")
            builder(dataset, axes, t_column, render_options)
            cls._apply_font_family(figure, render_options)
            return figure

    @classmethod
    def significance_stats(cls, dataset: VisualizationData, t_column: str, render_options: SignificanceRenderOptions):
        frame = cls._filtered_coefficients(dataset, render_options)
        t_values = pd.to_numeric(frame[t_column], errors="coerce").dropna()
        if t_values.empty:
            raise ValueError(f"{t_column} 列没有可用于显著性分析的数值")
        flags = cls._significance_flags(t_values, render_options.threshold)
        significant_count = int(flags.sum())
        total = int(len(flags))
        ratio = significant_count / total if total else 0.0
        return {"total": total, "significant": significant_count, "ratio": ratio}

    @classmethod
    def _plot_summary(cls, dataset, axes, t_column, render_options):
        frame = cls._filtered_coefficients(dataset, render_options)
        t_values = pd.to_numeric(frame[t_column], errors="coerce").dropna()
        if t_values.empty:
            raise ValueError(f"{t_column} 列没有可用于显著性分析的数值")
        flags = cls._significance_flags(t_values, render_options.threshold)
        counts = [int(flags.sum()), int((~flags).sum())]
        labels = ["显著", "不显著"]
        colors = ["#0f6cbd", "#cbd5e1"]
        bars = axes.bar(labels, counts, color=colors, width=0.55)
        for bar, value in zip(bars, counts):
            axes.text(bar.get_x() + bar.get_width() / 2, value, str(value), ha="center", va="bottom")
        ratio = counts[0] / max(1, sum(counts))
        axes.set_ylim(0, max(counts) * 1.2 if counts else 1)
        axes.set_title(cls._title(render_options, f"{VisualizationData.metric_base_name(t_column)} 显著性占比"))
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
        frame = cls._filtered_coefficients(dataset, render_options)
        x_col, y_col = ChartFactory._resolve_coordinate_columns(dataset, render_options)
        spatial = frame[[x_col, y_col, t_column]].copy()
        spatial[x_col] = pd.to_numeric(spatial[x_col], errors="coerce")
        spatial[y_col] = pd.to_numeric(spatial[y_col], errors="coerce")
        spatial[t_column] = pd.to_numeric(spatial[t_column], errors="coerce")
        spatial = spatial.dropna(subset=[x_col, y_col, t_column])
        if spatial.empty:
            raise ValueError("坐标列或 t 值列没有可用于绘图的数值")

        flags = cls._significance_flags(spatial[t_column], render_options.threshold)
        sig = spatial.loc[flags]
        nonsig = spatial.loc[~flags]

        if not nonsig.empty:
            axes.scatter(nonsig[x_col], nonsig[y_col], s=28, c="#cbd5e1", label="不显著", alpha=0.85, edgecolors="none")
        if not sig.empty:
            axes.scatter(sig[x_col], sig[y_col], s=32, c="#0f6cbd", label="显著", alpha=0.92, edgecolors="none")

        axes.set_title(cls._title(render_options, f"{VisualizationData.metric_base_name(t_column)} 显著性空间分布"))
        axes.set_xlabel(str(x_col))
        axes.set_ylabel(str(y_col))
        axes.grid(alpha=0.18)
        axes.legend(frameon=False)
        ChartFactory._apply_decimal_formatters(axes, render_options, ("x", "y"))

    @classmethod
    def _plot_temporal(cls, dataset, axes, t_column, render_options):
        frame = cls._filtered_coefficients(dataset, render_options, apply_time_slice=False)
        time_column = ChartFactory._resolve_time_column(dataset, render_options)
        data = frame[[time_column, t_column]].copy()
        data[t_column] = pd.to_numeric(data[t_column], errors="coerce")
        data = data.dropna(subset=[time_column, t_column])
        if data.empty:
            raise ValueError("时间列或 t 值列没有可用于绘图的数值")
        data["__significant__"] = cls._significance_flags(data[t_column], render_options.threshold).astype(float)
        grouped = data.groupby(time_column, sort=False)["__significant__"].mean().reset_index()
        grouped = ChartFactory._sort_frame_by_time(grouped, time_column)
        axes.plot(grouped[time_column], grouped["__significant__"], color="#0f6cbd", linewidth=2.0, marker="o")
        axes.set_ylim(0, 1.05)
        axes.set_title(cls._title(render_options, f"{VisualizationData.metric_base_name(t_column)} 显著性时间趋势"))
        axes.set_xlabel(str(time_column))
        axes.set_ylabel("显著占比")
        axes.grid(alpha=0.18)
        if pd.to_numeric(grouped[time_column], errors="coerce").notna().all():
            ChartFactory._apply_decimal_formatters(axes, render_options, ("x",))

    @staticmethod
    def _filtered_coefficients(dataset, render_options, apply_time_slice=True):
        frame = dataset.coefficients.copy()
        if not apply_time_slice or not render_options or not render_options.time_value:
            return frame
        time_column = ChartFactory._resolve_time_column(dataset, render_options)
        filtered = frame.loc[frame[time_column].astype(str) == str(render_options.time_value)].copy()
        if filtered.empty:
            raise ValueError(f"时间点 {render_options.time_value} 没有对应数据")
        return filtered

    @staticmethod
    def _significance_flags(series, threshold):
        return pd.Series(np.abs(pd.to_numeric(series, errors="coerce")) >= abs(float(threshold)), index=series.index)

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
        for text in figure.findobj(match=lambda artist: artist.__class__.__name__.endswith("Text")):
            text.set_fontfamily(font_families)

    @staticmethod
    def _title(render_options, default):
        if render_options and render_options.figure_title:
            return render_options.figure_title
        return default

    @staticmethod
    def _format_number(value, decimals):
        return f"{float(value):.{max(0, int(decimals))}f}"
