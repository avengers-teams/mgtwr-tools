from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app.core.config import stylesheet_path


def load_app_stylesheet() -> str:
    with open(stylesheet_path(), "r", encoding="utf-8") as stylesheet:
        return stylesheet.read()


def make_scrollable(widget, margins=(8, 8, 8, 8)):
    container = QWidget()
    container.setObjectName("pageContent")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(*margins)
    layout.setSpacing(0)
    layout.addWidget(widget)
    layout.addStretch(1)

    scroll_area = QScrollArea()
    scroll_area.setObjectName("pageCanvas")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll_area.setWidget(container)
    scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return scroll_area

