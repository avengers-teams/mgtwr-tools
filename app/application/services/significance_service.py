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
        return hint

