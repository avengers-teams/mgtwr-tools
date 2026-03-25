from qfluentwidgets import CheckBox, LineEdit, SpinBox


class ModernLineEdit(LineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(36)


class ModernSpinBox(SpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(36)


class ModernCheckBox(CheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        if text:
            self.setText(text)
        self.setMinimumHeight(32)
