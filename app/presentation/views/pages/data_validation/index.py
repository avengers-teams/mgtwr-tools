from PyQt5.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.fluent_surface import ActionPanel, PageHeader
from app.presentation.views.pages.data_validation.coefficients_to_shp import CoefficientsToShpWindow
from app.presentation.views.pages.data_validation.data_standardization import DataStandardizationWindow
from app.presentation.views.pages.data_validation.variance_Inflation_factor import VIFWindow


class AdditionalWindows(QWidget):
    def __init__(self):
        super().__init__()
        self.vif_window = None
        self.shp_window = None
        self.standardization_window = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("其他功能"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        grid.addWidget(
            self.build_tool_panel(
                "VIF 因子独立性检验",
                "用于快速检查自变量共线性。",
                "打开 VIF 工具",
                self.open_vif_window,
            ),
            0,
            0,
        )
        grid.addWidget(
            self.build_tool_panel(
                "coefficients 转 Shapefile",
                "将模型结果中的 coefficients 工作表按经纬度导出为点要素 shp 文件。",
                "打开导出工具",
                self.open_shp_window,
            ),
            0,
            1,
        )
        grid.addWidget(
            self.build_tool_panel(
                "数据标准化",
                "支持 Z-Score、Min-Max、Robust、MaxAbs 等多种常用标准化方法。",
                "打开标准化工具",
                self.open_standardization_window,
            ),
            1,
            0,
            1,
            2,
        )

        layout.addLayout(grid)
        layout.addStretch(1)

    @staticmethod
    def build_tool_panel(title, description, button_text, callback):
        panel = ActionPanel(title, description)
        button = ModernButton(button_text)
        button.clicked.connect(callback)
        panel.body_layout.addWidget(button)
        return panel

    def has_open_tool_windows(self):
        return any(window is not None and window.isVisible() for window in self._tool_windows())

    def close_tool_windows(self):
        for window in self._tool_windows():
            if window is not None and window.isVisible():
                window.close()

    def _tool_windows(self):
        return (
            self.vif_window,
            self.shp_window,
            self.standardization_window,
        )

    @staticmethod
    def _show_window(window):
        window.show()
        window.raise_()
        window.activateWindow()

    def open_vif_window(self):
        if self.vif_window is None or not self.vif_window.isVisible():
            self.vif_window = VIFWindow()
        self._show_window(self.vif_window)

    def open_shp_window(self):
        if self.shp_window is None or not self.shp_window.isVisible():
            self.shp_window = CoefficientsToShpWindow()
        self._show_window(self.shp_window)

    def open_standardization_window(self):
        if self.standardization_window is None or not self.standardization_window.isVisible():
            self.standardization_window = DataStandardizationWindow()
        self._show_window(self.standardization_window)
