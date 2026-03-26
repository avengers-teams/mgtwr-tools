from __future__ import annotations

from app.application.services.result_file_service import ResultFileService
from app.application.services.significance_service import SignificanceAnalysisService
from app.infrastructure.repositories.excel_result_repository import ExcelResultRepository
from app.presentation.presenters.significance_presenter import SignificancePresenter
from app.presentation.views.main_window import MainWindow
from app.presentation.views.pages.significance_analysis import SignificanceAnalysisPage


class AppContainer:
    def __init__(self):
        self.excel_result_repository = ExcelResultRepository()
        self.result_file_service = ResultFileService(self.excel_result_repository)
        self.significance_service = SignificanceAnalysisService()

    def create_significance_presenter(self) -> SignificancePresenter:
        return SignificancePresenter(
            result_file_service=self.result_file_service,
            significance_service=self.significance_service,
        )

    def create_significance_page(self, console_output) -> SignificanceAnalysisPage:
        return SignificanceAnalysisPage(
            console_output=console_output,
            presenter=self.create_significance_presenter(),
        )

    def create_main_window(self) -> MainWindow:
        return MainWindow(container=self)

