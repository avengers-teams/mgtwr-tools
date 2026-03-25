from qfluentwidgets import ListWidget


class ModernListWidget(ListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(False)
        self.setStyleSheet("""
            QListWidget {
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(150, 165, 190, 0.95);
                border-radius: 14px;
                padding: 8px;
            }
            QListWidget::item {
                border-radius: 8px;
                padding: 6px 8px;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background: rgba(0, 120, 212, 0.16);
                color: rgba(20, 32, 52, 0.95);
            }
            QListWidget:focus {
                border: 1px solid rgba(0, 95, 184, 0.9);
            }
        """)
