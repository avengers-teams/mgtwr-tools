import sys
from multiprocessing import freeze_support

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from utils.urltools import get_resource_path
from views.app import MainWindow
from views.theme import APP_STYLESHEET

if __name__ == '__main__':
    freeze_support()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    setThemeColor("#0078D4")
    app.setStyleSheet(APP_STYLESHEET)
    main_window = MainWindow()
    main_window.setWindowIcon(QIcon(get_resource_path("favicon.ico")))
    main_window.show()
    sys.exit(app.exec_())

