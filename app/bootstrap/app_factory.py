from __future__ import annotations

import sys
from multiprocessing import freeze_support

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from app.bootstrap.container import AppContainer
from app.core.config import APP_THEME_COLOR, window_icon_path
from app.presentation.views.theme import load_app_stylesheet


def create_application(argv: list[str] | None = None):
    freeze_support()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv or sys.argv)
    setTheme(Theme.LIGHT)
    setThemeColor(APP_THEME_COLOR)
    app.setStyleSheet(load_app_stylesheet())

    container = AppContainer()
    main_window = container.create_main_window()
    main_window.setWindowIcon(QIcon(window_icon_path()))
    return app, main_window

