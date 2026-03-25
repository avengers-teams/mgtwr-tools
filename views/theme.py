from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


APP_STYLESHEET = """
QWidget {
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 14px;
}

QWidget#pageCanvas, QWidget#pageContent {
    background: transparent;
}

QFrame[panel="true"], QGroupBox {
    background: rgba(255, 255, 255, 0.76);
    border: 1px solid rgba(255, 255, 255, 0.92);
    border-radius: 20px;
}

QFrame[hero="true"] {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba(255, 255, 255, 0.88),
        stop: 1 rgba(245, 249, 255, 0.72)
    );
    border: 1px solid rgba(255, 255, 255, 0.96);
    border-radius: 28px;
}

QGroupBox {
    margin-top: 12px;
    padding: 18px 16px 16px 16px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: rgba(28, 43, 66, 0.92);
}

QLineEdit, QListWidget, QTextEdit, QTableWidget, QSpinBox {
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(205, 214, 228, 0.92);
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: rgba(0, 90, 158, 0.18);
}

QLineEdit:focus, QListWidget:focus, QTextEdit:focus, QTableWidget:focus, QSpinBox:focus {
    border: 1px solid rgba(0, 95, 184, 0.72);
}

QListWidget, QTableWidget {
    padding: 6px;
}

QHeaderView::section {
    background: rgba(248, 250, 253, 0.96);
    color: rgba(26, 32, 44, 0.88);
    padding: 8px;
    border: none;
    border-bottom: 1px solid rgba(221, 229, 240, 0.94);
    font-weight: 600;
}

QTableWidget {
    gridline-color: rgba(229, 234, 241, 0.88);
    background: rgba(255, 255, 255, 0.80);
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: rgba(120, 132, 152, 0.42);
    min-height: 32px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(96, 109, 132, 0.58);
}

QScrollBar::handle:vertical:pressed {
    background: rgba(74, 88, 111, 0.72);
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 4px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background: rgba(120, 132, 152, 0.42);
    min-width: 32px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: rgba(96, 109, 132, 0.58);
}

QScrollBar::handle:horizontal:pressed {
    background: rgba(74, 88, 111, 0.72);
}

QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: none;
}

QSplitter::handle {
    background: rgba(208, 216, 228, 0.74);
    height: 8px;
}

QCheckBox {
    spacing: 8px;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background: rgba(255, 255, 255, 0.56);
    border: 1px solid rgba(255, 255, 255, 0.82);
    color: rgba(40, 52, 76, 0.86);
    border-radius: 10px;
    padding: 8px 12px;
    margin-right: 6px;
}

QTabBar::tab:selected {
    background: rgba(255, 255, 255, 0.92);
    color: rgba(0, 80, 158, 0.96);
}

QTabBar::tab:hover:!selected {
    background: rgba(255, 255, 255, 0.74);
}
"""


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
