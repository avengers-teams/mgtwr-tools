from __future__ import annotations

from multiprocessing import Process, Queue
from queue import Empty

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel

from app.application.dto.network_analysis import NetworkMetricsOptions
from app.infrastructure.tasks.network_analysis import network_metrics_process
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.fluent_surface import FrostedPanel
from app.presentation.views.widgets.input import ModernLineEdit


class NetworkMetricsCalculationPage(QWidget):
    MODE_OPTIONS = [
        ("single", "单窗口 compare_matrix.npz"),
        ("batch", "滑动窗口根目录"),
    ]

    def __init__(self, console_output, task_manager, network_analysis_service):
        super().__init__()
        self.console_output = console_output
        self.task_manager = task_manager
        self.network_analysis_service = network_analysis_service
        self.output_queue = Queue()
        self.result_cache = {}
        self.process_tasks = {}
        self.finalized_tasks = set()
        self.init_ui()

        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.read_queue)
        self.queue_timer.start(300)
        self.process_timer = QTimer(self)
        self.process_timer.timeout.connect(self.check_process_completion)
        self.process_timer.start(500)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        header = FrostedPanel(hero=True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(12)
        header_layout.addWidget(TitleLabel("网络分析 / 指标计算"))
        desc = SubtitleLabel("支持单个 compare_matrix.npz 计算，也支持整个滑动窗口目录批处理；结果写回各窗口目录。")
        desc.setWordWrap(True)
        header_layout.addWidget(desc)
        layout.addWidget(header)

        tips = FrostedPanel()
        tips_layout = QVBoxLayout(tips)
        tips_layout.setContentsMargins(18, 16, 18, 16)
        tips_layout.setSpacing(6)
        tips_layout.addWidget(SubtitleLabel("说明"))
        help_text = BodyLabel(
            "1. 单窗口模式适合先验证一个 compare_matrix.npz。\n"
            "2. 批量模式会扫描滑动窗口根目录下的 window_* 或 windows_manifest.csv。\n"
            "3. 指标默认输出 network_metrics.csv / network_summary.csv；如勾选 GeoTIFF，需要额外提供模板栅格。"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #5b6b84;")
        tips_layout.addWidget(help_text)
        layout.addWidget(tips)

        form_panel = FrostedPanel()
        form_layout = QGridLayout(form_panel)
        form_layout.setContentsMargins(20, 18, 20, 18)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(12)

        form_layout.addWidget(QLabel("运行模式"), 0, 0)
        self.mode_combo = ModernComboBox()
        for value, label in self.MODE_OPTIONS:
            self.mode_combo.addItem(label, userData=value)
        self.mode_combo.currentIndexChanged.connect(self.update_mode_state)
        form_layout.addWidget(self.mode_combo, 0, 1, 1, 3)

        form_layout.addWidget(QLabel("矩阵文件"), 1, 0)
        self.compare_npz_input = ModernLineEdit()
        self.compare_npz_input.setPlaceholderText("选择 compare_matrix.npz")
        form_layout.addWidget(self.compare_npz_input, 1, 1, 1, 2)
        compare_button = ModernButton("选择文件")
        compare_button.clicked.connect(self.select_compare_npz)
        form_layout.addWidget(compare_button, 1, 3)

        form_layout.addWidget(QLabel("窗口根目录"), 2, 0)
        self.window_root_input = ModernLineEdit()
        self.window_root_input.setPlaceholderText("选择滑动窗口根目录")
        form_layout.addWidget(self.window_root_input, 2, 1, 1, 2)
        window_root_button = ModernButton("选择目录")
        window_root_button.clicked.connect(self.select_window_root)
        form_layout.addWidget(window_root_button, 2, 3)

        form_layout.addWidget(QLabel("单窗口输出目录"), 3, 0)
        self.out_dir_input = ModernLineEdit()
        self.out_dir_input.setPlaceholderText("留空则输出到 compare_matrix.npz 所在目录")
        form_layout.addWidget(self.out_dir_input, 3, 1, 1, 2)
        out_dir_button = ModernButton("选择目录")
        out_dir_button.clicked.connect(self.select_output_dir)
        form_layout.addWidget(out_dir_button, 3, 3)

        form_layout.addWidget(QLabel("阈值"), 4, 0)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setDecimals(6)
        self.threshold_spin.setRange(0.0, 999999.0)
        form_layout.addWidget(self.threshold_spin, 4, 1)

        form_layout.addWidget(QLabel("方向扇区数"), 4, 2)
        self.n_sectors_spin = QSpinBox()
        self.n_sectors_spin.setRange(4, 64)
        self.n_sectors_spin.setValue(8)
        form_layout.addWidget(self.n_sectors_spin, 4, 3)

        form_layout.addWidget(QLabel("并行进程数"), 5, 0)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(0, 32)
        self.workers_spin.setValue(0)
        self.workers_spin.setToolTip("仅批量模式有效，0 表示串行。")
        form_layout.addWidget(self.workers_spin, 5, 1)

        self.skip_existing_checkbox = QCheckBox("跳过已有结果")
        self.fail_fast_checkbox = QCheckBox("遇错立即停止")
        self.export_tiff_checkbox = QCheckBox("同步导出 GeoTIFF")
        self.export_tiff_checkbox.toggled.connect(self.update_mode_state)
        form_layout.addWidget(self.skip_existing_checkbox, 5, 2)
        form_layout.addWidget(self.fail_fast_checkbox, 5, 3)
        form_layout.addWidget(self.export_tiff_checkbox, 6, 0, 1, 2)

        form_layout.addWidget(QLabel("GeoTIFF 模板"), 6, 2)
        self.template_tif_input = ModernLineEdit()
        self.template_tif_input.setPlaceholderText("选择模板栅格 tif")
        form_layout.addWidget(self.template_tif_input, 6, 3)

        template_button_row = QHBoxLayout()
        template_button = ModernButton("选择模板")
        template_button.clicked.connect(self.select_template_tif)
        template_button_row.addWidget(template_button)
        template_button_row.addStretch(1)
        form_layout.addLayout(template_button_row, 7, 3)

        layout.addWidget(form_panel)

        action_group = QGroupBox("执行")
        action_layout = QVBoxLayout(action_group)
        action_layout.setSpacing(10)
        button_row = QHBoxLayout()
        start_button = ModernButton("开始计算")
        start_button.clicked.connect(self.start_task)
        button_row.addWidget(start_button)
        button_row.addStretch(1)
        action_layout.addLayout(button_row)
        self.status_label = BodyLabel("状态：待执行")
        self.status_label.setWordWrap(True)
        action_layout.addWidget(self.status_label)
        layout.addWidget(action_group)
        layout.addStretch(1)

        self.update_mode_state()

    def read_queue(self):
        while True:
            try:
                message = self.output_queue.get_nowait()
            except Empty:
                break

            if isinstance(message, dict):
                self.handle_queue_event(message)
            else:
                self.console_output.write(str(message))

    def handle_queue_event(self, event):
        task_id = event.get("task_id")
        status = event.get("status")
        message = event.get("message", "")
        kind = event.get("kind")

        if status and task_id is not None:
            self.task_manager.update_task_status(task_id, status)

        if kind == "warning" and message:
            self.console_output.append_message(message, task_id=task_id)
            return

        if kind == "result" and task_id is not None:
            self.result_cache[task_id] = event.get("result", {})
            self.finalized_tasks.add(task_id)

        if message:
            self.console_output.append_message(message, task_id=task_id)
            self.status_label.setText(f"状态：{message}")
        elif kind == "log" and task_id is not None:
            self.console_output.append_message(event.get("message", ""), task_id=task_id)

        if status == "出错" and task_id is not None:
            self.finalized_tasks.add(task_id)

    def check_process_completion(self):
        for task_id, process in list(self.process_tasks.items()):
            if process.is_alive():
                continue

            if task_id in self.finalized_tasks:
                self.process_tasks.pop(task_id, None)
                continue

            exit_code = process.exitcode
            message = self.describe_process_exit(exit_code)
            self.console_output.append_message(message, task_id=task_id)
            self.status_label.setText(f"状态：{message}")
            self.task_manager.update_task_status(task_id, "出错")
            self.finalized_tasks.add(task_id)
            self.process_tasks.pop(task_id, None)

    @staticmethod
    def describe_process_exit(exit_code):
        if exit_code is None:
            return "网络指标子进程已结束，但未返回退出码。"
        if exit_code == 0:
            return "网络指标子进程已结束，但未返回结果消息。"

        common_windows_codes = {
            3221225477: "网络指标子进程异常退出，exit code=3221225477 (0xC0000005，常见为本地库访问冲突/崩溃)。",
            3221225781: "网络指标子进程异常退出，exit code=3221225781 (0xC0000135，常见为本地依赖缺失)。",
            3221226505: "网络指标子进程异常退出，exit code=3221226505 (0xC0000409，常见为本地库栈损坏/快速失败)。",
        }
        return common_windows_codes.get(
            exit_code,
            f"网络指标子进程异常退出，exit code={exit_code}。",
        )

    def current_mode(self) -> str:
        return self.mode_combo.currentData() or "single"

    def update_mode_state(self):
        is_single = self.current_mode() == "single"
        export_tiff = self.export_tiff_checkbox.isChecked()
        self.compare_npz_input.setEnabled(is_single)
        self.out_dir_input.setEnabled(is_single)
        self.window_root_input.setEnabled(not is_single)
        self.workers_spin.setEnabled(not is_single)
        self.fail_fast_checkbox.setEnabled(not is_single)
        self.template_tif_input.setEnabled(export_tiff)

    def select_compare_npz(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 compare_matrix.npz", "", "NumPy 文件 (*.npz)")
        if file_path:
            self.compare_npz_input.setText(file_path)

    def select_window_root(self):
        directory = QFileDialog.getExistingDirectory(self, "选择滑动窗口根目录")
        if directory:
            self.window_root_input.setText(directory)

    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.out_dir_input.setText(directory)

    def select_template_tif(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择模板栅格", "", "栅格文件 (*.tif *.tiff)")
        if file_path:
            self.template_tif_input.setText(file_path)

    def build_options(self) -> NetworkMetricsOptions:
        mode = self.current_mode()
        compare_npz = self.compare_npz_input.text().strip() or None
        window_root = self.window_root_input.text().strip() or None
        out_dir = self.out_dir_input.text().strip() or None
        template_tif = self.template_tif_input.text().strip() or None

        if mode == "single" and not compare_npz:
            raise ValueError("单窗口模式必须选择 compare_matrix.npz。")
        if mode == "batch" and not window_root:
            raise ValueError("批量模式必须选择滑动窗口根目录。")
        if self.export_tiff_checkbox.isChecked() and not template_tif:
            raise ValueError("导出 GeoTIFF 时必须提供模板栅格。")

        return NetworkMetricsOptions(
            mode=mode,
            compare_npz=compare_npz,
            window_root=window_root,
            out_dir=out_dir,
            threshold=float(self.threshold_spin.value()),
            n_sectors=int(self.n_sectors_spin.value()),
            skip_existing=self.skip_existing_checkbox.isChecked(),
            fail_fast=self.fail_fast_checkbox.isChecked(),
            workers=int(self.workers_spin.value()),
            template_tif=template_tif,
            export_tiff=self.export_tiff_checkbox.isChecked(),
        )

    def start_task(self):
        try:
            options = self.build_options()
        except Exception as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            self.console_output.append(f"网络指标计算参数错误: {exc}")
            return

        task_id = self.task_manager.create_task_id()
        process = Process(target=network_metrics_process, args=(task_id, options, self.output_queue))

        self.console_output.add_task_console(task_id, f"网络分析 #{task_id}")
        self.console_output.clear_task_console(task_id)
        self.console_output.append_message(f"开始创建网络指标任务，任务ID: {task_id}", task_id=task_id)
        self.status_label.setText(f"状态：任务 {task_id} 已启动")

        try:
            process.start()
            self.task_manager.add_task(task_id, process, "进程", name="网络指标计算")
            self.task_manager.refresh_process_monitor(task_id)
            self.process_tasks[task_id] = process
            self.console_output.activate_task_console(task_id)
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", f"无法启动网络指标任务：{exc}")
            self.console_output.append(f"无法启动网络指标任务: {exc}")
            self.status_label.setText(f"状态：无法启动任务 {task_id}")
