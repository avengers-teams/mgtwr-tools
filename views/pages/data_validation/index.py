from PyQt5.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from views.components.button import ModernButton
from views.components.fluent_surface import ActionPanel, PageHeader
from views.pages.data_validation.coefficients_to_shp import CoefficientsToShpWindow
from views.pages.data_validation.data_standardization import DataStandardizationWindow
from views.pages.data_validation.variance_Inflation_factor import VIFWindow


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

        layout.addWidget(PageHeader("其他功能", "补充型工具页，放与建模主链路解耦的独立工具。"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        grid.addWidget(
            self.build_tool_panel(
                "VIF 因子独立性检验",
                "用于快速检查自变量共线性。",
                "打开 VIF 工具",
                self.open_vif_window,
                accent="rgba(37, 99, 235, 0.08)",
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
                accent="rgba(5, 150, 105, 0.08)",
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
                accent="rgba(217, 119, 6, 0.08)",
            ),
            1,
            0,
            1,
            2,
        )

        layout.addLayout(grid)
        layout.addStretch(1)

    @staticmethod
    def build_tool_panel(title, description, button_text, callback, accent):
        panel = ActionPanel(title, description, accent=accent)
        button = ModernButton(button_text)
        button.clicked.connect(callback)
        panel.body_layout.addWidget(button)
        return panel

    def open_vif_window(self):
        self.vif_window = VIFWindow()
        self.vif_window.show()
        self.vif_window.raise_()
        self.vif_window.activateWindow()

    def open_shp_window(self):
        self.shp_window = CoefficientsToShpWindow()
        self.shp_window.show()
        self.shp_window.raise_()
        self.shp_window.activateWindow()

    def open_standardization_window(self):
        self.standardization_window = DataStandardizationWindow()
        self.standardization_window.show()
        self.standardization_window.raise_()
        self.standardization_window.activateWindow()
