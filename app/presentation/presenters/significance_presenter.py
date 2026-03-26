from __future__ import annotations

from app.presentation.viewmodels.significance_viewmodel import SignificancePageViewModel


class SignificancePresenter:
    def __init__(self, result_file_service, significance_service):
        self.result_file_service = result_file_service
        self.significance_service = significance_service

    def load_file(self, file_path: str) -> SignificancePageViewModel:
        dataset = self.result_file_service.load_result_dataset(file_path)
        return SignificancePageViewModel(
            file_path=file_path,
            dataset=dataset,
            chart_specs=self.significance_service.available_charts(dataset),
            coordinate_columns=dataset.spatial_candidate_columns(),
            time_columns=dataset.temporal_candidate_columns(),
        )

    def render(self, dataset, t_column: str, chart_key: str, options):
        return self.significance_service.render(dataset, t_column, chart_key, options)

