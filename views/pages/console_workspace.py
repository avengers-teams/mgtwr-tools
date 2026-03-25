from PyQt5.QtWidgets import QVBoxLayout, QWidget

from views.components.button import ModernButton
from views.components.fluent_surface import FrostedPanel, PageHeader, make_toolbar_row


class ConsoleWorkspacePage(QWidget):
    def __init__(self, console_manager, parent=None):
        super().__init__(parent)
        self.console_manager = console_manager
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        header_panel = FrostedPanel(hero=True)
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(14)
        header_layout.addWidget(PageHeader(
            "多任务控制台",
            "每个任务拥有独立日志页签。日志更新只写入对应控制台，不会强制切换到前台。",
            badge_text="Task Console",
        ))

        clear_button = ModernButton("清空当前")
        clear_button.clicked.connect(self.console_manager.clear)
        save_button = ModernButton("保存当前")
        save_button.clicked.connect(self.console_manager.save)
        header_layout.addWidget(make_toolbar_row(clear_button, save_button))
        layout.addWidget(header_panel)

        console_panel = FrostedPanel()
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(18, 18, 18, 18)
        console_layout.addWidget(self.console_manager)
        layout.addWidget(console_panel, 1)
