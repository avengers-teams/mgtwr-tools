from typing import Callable, Optional

import psutil
from PyQt5.QtCore import QThread, QTimer, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from multiprocessing import Process

from views.components.button import ModernButton


class TaskManager(QWidget):
    def __init__(self, console_manager=None, open_console_callback=None):
        super().__init__()
        self.console_manager = console_manager
        self.open_console_callback = open_console_callback
        self.tasks = {}
        self._next_task_id = 1
        self.initUI()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_resources)
        self.timer.start(1500)

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        title = QLabel("任务管理")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #0f172a;")
        main_layout.addWidget(title)

        subtitle = QLabel("查看任务状态，可重新打开对应控制台，必要时安全终止正在运行的任务。")
        subtitle.setStyleSheet("color: #64748b;")
        main_layout.addWidget(subtitle)

        table_group = QGroupBox("任务列表")
        table_layout = QVBoxLayout(table_group)

        self.task_table = QTableWidget(0, 6)
        self.task_table.setHorizontalHeaderLabels(["任务ID", "名称", "状态", "类型", "CPU%", "内存(MB)"])
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.task_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.horizontalHeader().setStretchLastSection(True)
        self.task_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.itemSelectionChanged.connect(self.on_task_selection_changed)
        table_layout.addWidget(self.task_table)
        main_layout.addWidget(table_group)

        button_layout = QHBoxLayout()
        self.open_console_button = ModernButton("打开控制台")
        self.terminate_task_button = ModernButton("终止任务")
        self.clear_completed_button = ModernButton("清理已结束任务")
        button_layout.addWidget(self.open_console_button)
        button_layout.addWidget(self.terminate_task_button)
        button_layout.addWidget(self.clear_completed_button)
        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)

        self.open_console_button.clicked.connect(self.open_selected_task_console)
        self.terminate_task_button.clicked.connect(self.terminate_task)
        self.clear_completed_button.clicked.connect(self.clear_finished_tasks)
        self.task_table.itemDoubleClicked.connect(lambda _item: self.open_selected_task_console())

    def create_task_id(self):
        task_id = self._next_task_id
        self._next_task_id += 1
        return task_id

    def add_task(self, task_id, task, task_type, name="", cancel_callback: Optional[Callable] = None):
        row_position = self.task_table.rowCount()
        self.task_table.insertRow(row_position)
        self.task_table.setItem(row_position, 0, QTableWidgetItem(str(task_id)))
        self.task_table.setItem(row_position, 1, QTableWidgetItem(name or f"{task_type}任务"))
        self.task_table.setItem(row_position, 2, QTableWidgetItem("运行中"))
        self.task_table.setItem(row_position, 3, QTableWidgetItem(task_type))
        self.task_table.setItem(row_position, 4, QTableWidgetItem("--"))
        self.task_table.setItem(row_position, 5, QTableWidgetItem("--"))

        monitor = None
        if task_type == "进程" and isinstance(task, Process) and task.pid:
            try:
                monitor = psutil.Process(task.pid)
                monitor.cpu_percent(None)
            except psutil.Error:
                monitor = None

        self.tasks[task_id] = {
            "task": task,
            "type": task_type,
            "row": row_position,
            "cancel_callback": cancel_callback,
            "monitor": monitor,
            "name": name or f"{task_type}任务",
        }
        if self.console_manager is not None:
            self.console_manager.add_task_console(task_id, name or f"任务 {task_id}")

    def update_task_status(self, task_id, status):
        task_info = self.tasks.get(task_id)
        if not task_info:
            return
        row = task_info["row"]
        self.task_table.setItem(row, 2, QTableWidgetItem(status))

    def refresh_process_monitor(self, task_id):
        task_info = self.tasks.get(task_id)
        if not task_info:
            return

        task = task_info["task"]
        if not isinstance(task, Process) or not task.pid:
            return

        if task_info["monitor"] is None:
            try:
                task_info["monitor"] = psutil.Process(task.pid)
                task_info["monitor"].cpu_percent(None)
            except psutil.Error:
                return

    def terminate_task(self):
        row = self.task_table.currentRow()
        if row == -1:
            return

        task_item = self.task_table.item(row, 0)
        if task_item is None:
            return

        task_id = int(task_item.text())
        task_info = self.tasks.get(task_id)
        if not task_info:
            return

        task = task_info["task"]
        cancel_callback = task_info.get("cancel_callback")

        if callable(cancel_callback):
            cancel_callback()

        if task_info["type"] == "线程" and isinstance(task, QThread):
            task.wait(2000)
            status = "已终止" if not task.isRunning() else "终止中"
        elif task_info["type"] == "进程" and isinstance(task, Process):
            if task.is_alive():
                task.terminate()
                task.join(timeout=2)
            status = "已终止" if not task.is_alive() else "终止失败"
        else:
            status = "已终止"

        self.update_task_status(task_id, status)
        self._set_row_usage(task_info["row"], "--", "--")

    def refresh_resources(self):
        for task_id, task_info in list(self.tasks.items()):
            task = task_info["task"]
            task_type = task_info["type"]
            row = task_info["row"]

            if task_type == "进程" and isinstance(task, Process):
                self.refresh_process_monitor(task_id)
                if task.is_alive():
                    try:
                        monitor = task_info["monitor"]
                        cpu_usage = monitor.cpu_percent(None) / max(psutil.cpu_count(), 1)
                        memory_usage = monitor.memory_info().rss / (1024 * 1024)
                        self._set_row_usage(row, f"{cpu_usage:.2f}", f"{memory_usage:.2f}")
                    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                        self._set_row_usage(row, "--", "--")
                else:
                    if self.task_table.item(row, 2).text() == "运行中":
                        exit_code = task.exitcode
                        self.update_task_status(task_id, "已完成" if exit_code == 0 else "出错")
                    self._set_row_usage(row, "--", "--")
            elif task_type == "线程" and isinstance(task, QThread):
                if task.isRunning():
                    self._set_row_usage(row, "--", "--")
                else:
                    current_status = self.task_table.item(row, 2).text()
                    if current_status == "运行中":
                        self.update_task_status(task_id, "已完成")
                    self._set_row_usage(row, "--", "--")

    def clear_finished_tasks(self):
        removable_task_ids = []
        for task_id, task_info in self.tasks.items():
            row = task_info["row"]
            status = self.task_table.item(row, 2).text()
            if status in {"已完成", "已终止", "出错"}:
                removable_task_ids.append(task_id)

        for task_id in removable_task_ids:
            self.delete_task(task_id)

    def delete_task(self, task_id):
        task_info = self.tasks.pop(task_id, None)
        if not task_info:
            return

        row_to_remove = task_info["row"]
        self.task_table.removeRow(row_to_remove)
        self._reindex_rows()

    def _reindex_rows(self):
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item is None:
                continue
            task_id = int(item.text())
            if task_id in self.tasks:
                self.tasks[task_id]["row"] = row

    def _set_row_usage(self, row, cpu_text, memory_text):
        self.task_table.setItem(row, 4, QTableWidgetItem(cpu_text))
        self.task_table.setItem(row, 5, QTableWidgetItem(memory_text))

    def on_task_selection_changed(self):
        return

    def open_selected_task_console(self):
        if self.console_manager is None:
            return
        row = self.task_table.currentRow()
        if row == -1:
            return
        item = self.task_table.item(row, 0)
        if item is None:
            return
        self.console_manager.activate_task_console(int(item.text()))
        if callable(self.open_console_callback):
            self.open_console_callback()
