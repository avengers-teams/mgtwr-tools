from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel


class FrostedPanel(QFrame):
    def __init__(self, parent=None, hero=False):
        super().__init__(parent)
        self.setProperty("panel", not hero)
        if hero:
            self.setProperty("hero", True)


class PageHeader(QWidget):
    def __init__(self, title, subtitle="", badge_text="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if badge_text:
            badge = QLabel(badge_text)
            badge.setStyleSheet("""
                QLabel {
                    background: rgba(255, 255, 255, 0.74);
                    border: 1px solid rgba(255, 255, 255, 0.9);
                    border-radius: 11px;
                    color: rgba(0, 90, 158, 0.92);
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: 600;
                }
            """)
            layout.addWidget(badge, 0)

        title_label = TitleLabel(title)
        layout.addWidget(title_label, 0)

        if subtitle:
            subtitle_label = SubtitleLabel(subtitle)
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label, 0)


class SectionHeader(QWidget):
    def __init__(self, title, description="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_label = SubtitleLabel(title)
        layout.addWidget(title_label)

        if description:
            desc_label = BodyLabel(description)
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)


class ActionPanel(FrostedPanel):
    def __init__(self, title, description="", accent=None, parent=None):
        super().__init__(parent)
        if accent:
            self.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 rgba(255, 255, 255, 0.88),
                        stop: 1 {accent}
                    );
                    border: 1px solid rgba(255, 255, 255, 0.92);
                    border-radius: 22px;
                }}
            """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title_label = SubtitleLabel(title)
        layout.addWidget(title_label)

        if description:
            desc_label = BodyLabel(description)
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 4, 0, 0)
        self.body_layout.setSpacing(10)
        layout.addLayout(self.body_layout)


class StatPill(QFrame):
    def __init__(self, title, value, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid rgba(255, 255, 255, 0.92);
                border-radius: 18px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        value_label = TitleLabel(str(value))
        layout.addWidget(value_label)

        title_label = BodyLabel(title)
        layout.addWidget(title_label)


def make_toolbar_row(*widgets):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return row

