from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

from views.components.button import ModernButton
from views.pages.data_validation.variance_Inflation_factor import VIFWindow


class AdditionalWindows(QWidget):
    """包含 6 个按钮的页面，其中一个用于打开 VIF 分析窗口。"""

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title = QLabel("其他功能")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #0f172a;")
        layout.addWidget(title)

        desc = QLabel("提供补充型分析工具，当前已接入 VIF 因子独立性检验。")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #64748b;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        vif = ModernButton("VIF 因子独立性检验")
        vif.clicked.connect(self.open_vif_window)
        layout.addWidget(vif)
        layout.addStretch(1)

    def open_vif_window(self):
        self.vif_window = VIFWindow()
        self.vif_window.show()
