from qfluentwidgets import ComboBox


class ModernComboBox(ComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(36)
