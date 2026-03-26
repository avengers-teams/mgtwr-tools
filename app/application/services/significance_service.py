from __future__ import annotations

from app.application.dto.significance import SignificanceRenderResult
from app.domain.policies.significance_policy import SignificancePolicy
from app.presentation.renderers.significance_chart_factory import SignificanceChartFactory


class SignificanceAnalysisService:
    def available_charts(self, dataset):
        return SignificanceChartFactory.available_charts(dataset)

    def render(self, dataset, t_column: str, chart_key: str, options):
        stats = SignificancePolicy.significance_stats(
            dataset,
            t_column,
            options,
            SignificanceChartFactory._filtered_coefficients,
        )
        figure = SignificanceChartFactory.create_figure(dataset, t_column, chart_key, options)
        return SignificanceRenderResult(
            figure=figure,
            stats=stats,
            hint=self._build_hint(dataset, t_column, chart_key, options),
        )

    def _build_hint(self, dataset, t_column, chart_key, options):
        charts = {spec.key: spec for spec in self.available_charts(dataset)}
        spec = charts.get(chart_key)
        hint = f"当前图表：{spec.label if spec else chart_key}，统计量：{dataset.metric_display_name(t_column)}，阈值：|t| >= {options.threshold:.4f}"
        if spec and spec.requires_beta and options.beta_column:
            hint += f"，系数字段：{dataset.metric_display_name(options.beta_column)}"
        if getattr(options, "spatial_mode", None) == "aggregate_time":
            hint += "，空间展示：汇总全部时间"
        if getattr(options, "temporal_mode", None) == "single_location" and getattr(options, "location_value", None) is not None:
            if getattr(options, "location_column", None):
                hint += f"，时间展示：{options.location_column}={dataset.format_display_value(options.location_value)}"
            else:
                x_col = options.longitude_column or (dataset.coord_columns[0] if len(dataset.coord_columns) >= 1 else "X")
                y_col = options.latitude_column or (dataset.coord_columns[1] if len(dataset.coord_columns) >= 2 else "Y")
                x_value, y_value = options.location_value
                hint += f"，时间展示：{dataset.format_location_label(x_value, y_value, x_col, y_col)}"
        return hint

