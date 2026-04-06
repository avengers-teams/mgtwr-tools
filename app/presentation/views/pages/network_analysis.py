from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.fluent_surface import ActionPanel, PageHeader


class NetworkAnalysisHomePage(QWidget):
    def __init__(self, navigate_callback):
        super().__init__()
        self.navigate_callback = navigate_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "网络分析",
                "整合滑动窗口网络指标计算与地图展示。先在“指标计算”生成 network_metrics.csv / network_summary.csv，再到“指标展示”里做预览和批量导图。",
            )
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.addWidget(
            self.build_panel(
                "指标计算",
                "读取 compare_matrix.npz 或滑动窗口根目录，批量生成网络指标和窗口汇总表。",
                "前往计算",
                "network_metrics_calculation",
            ),
            0,
            0,
        )
        grid.addWidget(
            self.build_panel(
                "指标展示",
                "加载窗口指标结果，预览 Strength / Distance / Direction 图，并批量导出窗口配对地图。",
                "前往展示",
                "network_metrics_display",
            ),
            0,
            1,
        )

        layout.addLayout(grid)
        layout.addStretch(1)

    def build_panel(self, title: str, description: str, button_text: str, route_key: str):
        panel = ActionPanel(title, description)
        button = ModernButton(button_text)
        button.clicked.connect(lambda: self.navigate_callback(route_key))
        panel.body_layout.addWidget(button)
        return panel
