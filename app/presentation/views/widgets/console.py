from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import TabCloseButtonDisplayMode, TabWidget


class TaskConsole(QTextEdit):
    append_requested = pyqtSignal(str)
    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: rgba(15, 23, 42, 0.92);
                color: #edf2ff;
                font-family: Consolas, "Cascadia Mono", Monaco, monospace;
                font-size: 12px;
                border: 1px solid rgba(82, 96, 128, 0.5);
                border-radius: 16px;
                padding: 12px;
            }
        """)
        self._buffer = ""
        self.append_requested.connect(self._append_line)
        self.clear_requested.connect(self._clear_console_impl)

    def write(self, message):
        self._buffer += str(message)
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self.append_requested.emit(line)

    def flush(self):
        if self._buffer:
            self.append_requested.emit(self._buffer)
            self._buffer = ""

    def clear_console(self):
        self._buffer = ""
        self.clear_requested.emit()

    def _append_line(self, text):
        self.append(text)

    def _clear_console_impl(self):
        self.clear()


class TaskConsoleManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.console_tabs = {}
        self.console_titles = {}
        self.default_task_id = "system"
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = TabWidget()
        self.tab_widget.setMovable(True)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.ON_HOVER)
        self.tab_widget.setTabShadowEnabled(False)
        self.tab_widget.setTabMaximumWidth(220)
        self.tab_widget.setTabMinimumWidth(80)
        self.tab_widget.setStyleSheet("""
            TabWidget {
                background: transparent;
            }
            QStackedWidget {
                border: 1px solid rgba(214, 223, 236, 0.9);
                border-radius: 14px;
                background: rgba(255, 255, 255, 0.08);
            }
        """)
        self.tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)
        layout.addWidget(self.tab_widget)

        self.open_task_console(self.default_task_id, "系统", activate=True)

    def ensure_task_console(self, task_id, title=None):
        if task_id in self.console_tabs:
            if title:
                self.console_titles[task_id] = title
            return self.console_tabs[task_id]

        console = TaskConsole()
        self.console_tabs[task_id] = console
        self.console_titles[task_id] = title or f"任务 {task_id}"
        return console

    def add_task_console(self, task_id, title):
        return self.open_task_console(task_id, title, activate=False)

    def open_task_console(self, task_id, title=None, activate=True):
        console = self.ensure_task_console(task_id, title)
        tab_index = self.tab_widget.stackedWidget.indexOf(console)
        if tab_index == -1:
            tab_index = self.tab_widget.addTab(console, self.console_titles.get(task_id, title or f"任务 {task_id}"))
        elif title:
            self.tab_widget.setTabText(tab_index, title)

        self.refresh_tab_close_buttons()
        if activate:
            self.tab_widget.setCurrentIndex(tab_index)
        return console

    def rename_task_console(self, task_id, title):
        if task_id not in self.console_tabs:
            return
        self.console_titles[task_id] = title
        console = self.console_tabs[task_id]
        tab_index = self.tab_widget.stackedWidget.indexOf(console)
        if tab_index != -1:
            self.tab_widget.setTabText(tab_index, title)

    def activate_task_console(self, task_id):
        self.open_task_console(task_id, activate=True)

    def close_task_console(self, task_id):
        if task_id == self.default_task_id:
            return
        console = self.console_tabs.get(task_id)
        if console is None:
            return
        tab_index = self.tab_widget.stackedWidget.indexOf(console)
        if tab_index != -1:
            self.tab_widget.removeTab(tab_index)
            self.refresh_tab_close_buttons()

    def is_console_open(self, task_id):
        console = self.console_tabs.get(task_id)
        return console is not None and self.tab_widget.stackedWidget.indexOf(console) != -1

    def clear_task_console(self, task_id):
        console = self.console_tabs.get(task_id)
        if console is not None:
            console.clear_console()

    def append_message(self, message, task_id=None, title=None):
        target_task_id = self.default_task_id if task_id is None else task_id
        console = self.ensure_task_console(target_task_id, title or f"任务 {target_task_id}")
        console.write(f"{message}\n")

    def append(self, message):
        self.append_message(message)

    def write(self, message):
        self.console_tabs[self.default_task_id].write(message)

    def flush(self):
        self.console_tabs[self.default_task_id].flush()

    def clear(self):
        current_console = self.tab_widget.currentWidget()
        if isinstance(current_console, TaskConsole):
            current_console.clear_console()

    def save(self):
        current_console = self.tab_widget.currentWidget()
        if not isinstance(current_console, TaskConsole):
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "保存输出", "", "文本文件 (*.txt)")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(current_console.toPlainText())

    def on_tab_close_requested(self, index):
        console = self.tab_widget.widget(index)
        if console is None:
            return

        for task_id, task_console in self.console_tabs.items():
            if task_console is console:
                if task_id == self.default_task_id:
                    return
                self.tab_widget.removeTab(index)
                self.refresh_tab_close_buttons()
                return

    def refresh_tab_close_buttons(self):
        tab_index = self.tab_widget.stackedWidget.indexOf(self.console_tabs.get(self.default_task_id))
        if tab_index != -1:
            item = self.tab_widget.tabBar.tabItem(tab_index)
            if item is not None:
                item.closeButton.hide()

