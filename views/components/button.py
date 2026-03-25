from qfluentwidgets import PrimaryPushButton


class ModernButton(PrimaryPushButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setMinimumHeight(38)
