from queue import Empty

import pandas as pd
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QCursor, QDesktopServices
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QLineEdit,
    QSpinBox,
)
from multiprocessing import Process, Queue
from qfluentwidgets import TransparentPushButton

from utils.dataframe_loader import ExcelDataLoader
from utils.urltools import get_resource_path
from views.background_task.analysis import analysis_process
from views.components.button import ModernButton
from views.components.combobox import ModernComboBox
from views.components.input import ModernLineEdit
from views.components.list_widget import ModernListWidget
from views.components.parameter_box import create_model_param_box


MODEL_DESCRIPTIONS = {
    "GWR": "地理加权回归，仅考虑空间异质性，适合没有时间维度的数据。",
    "MGWR": "多尺度地理加权回归，为不同变量搜索不同空间带宽。",
    "GTWR": "时空加权回归，同时搜索空间带宽和时空尺度。",
    "MGTWR": "多尺度时空加权回归，为不同变量分别搜索空间带宽与时空尺度。",
}

TEMPORAL_MODELS = {"GTWR", "MGTWR"}


class MGRWRAnalysisPage(QWidget):
    def __init__(self, console_output, task_manager):
        super().__init__()
        self.excel_data = None
        self.console_output = console_output
        self.task_manager = task_manager
        self.input_file_path = None
        self.output_file_path = None
        self.output_queue = Queue()
        self.dynamic_inputs = {}
        self.initUI()

        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.read_queue)
        self.queue_timer.start(300)

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(14)

        title_label = QLabel("数据分析")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 28px; font-weight: 700; color: #0f172a;")
        main_layout.addWidget(title_label)

        help_label = QLabel('<a href="#">查看模型参数与使用说明</a>')
        help_label.setAlignment(Qt.AlignCenter)
        help_label.setOpenExternalLinks(False)
        help_label.linkActivated.connect(self.open_help)
        help_label.setCursor(QCursor(Qt.PointingHandCursor))
        help_label.setStyleSheet("color: #5c7457; font-size: 14px;")
        main_layout.addWidget(help_label)

        self.model_desc_label = QLabel()
        self.model_desc_label.setAlignment(Qt.AlignCenter)
        self.model_desc_label.setWordWrap(True)
        self.model_desc_label.setStyleSheet("color: #64748b;")
        main_layout.addWidget(self.model_desc_label)

        file_group = QGroupBox("文件设置")
        file_layout = QVBoxLayout(file_group)
        file_button_layout = QHBoxLayout()
        import_button = ModernButton("导入 Excel 文件")
        import_button.clicked.connect(self.import_file)
        output_button = ModernButton("选择输出文件")
        output_button.clicked.connect(self.output_file)
        file_button_layout.addWidget(import_button)
        file_button_layout.addWidget(output_button)
        file_button_layout.addStretch(1)
        file_layout.addLayout(file_button_layout)

        self.file_label = QLabel("输入文件：未选择")
        self.output_file_label = QLabel("输出文件：未选择")
        self.file_label.setWordWrap(True)
        self.output_file_label.setWordWrap(True)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.output_file_label)
        main_layout.addWidget(file_group)

        model_group = QGroupBox("模型设置")
        model_layout = QGridLayout(model_group)
        model_layout.setHorizontalSpacing(16)
        model_layout.setVerticalSpacing(12)

        model_label = QLabel("模型")
        self.model_combo = ModernComboBox()
        self.model_combo.addItems(["GWR", "MGWR", "GTWR", "MGTWR"])
        self.model_combo.currentTextChanged.connect(self.update_model_state)
        model_layout.addWidget(model_label, 0, 0)
        model_layout.addWidget(self.model_combo, 0, 1)

        kernel_label = QLabel("核函数")
        self.kernel_combo = ModernComboBox()
        self.kernel_combo.addItems(["gaussian", "bisquare", "exponential"])
        model_layout.addWidget(kernel_label, 0, 2)
        model_layout.addWidget(self.kernel_combo, 0, 3)

        fixed_label = QLabel("固定带宽")
        self.fixed_combo = ModernComboBox()
        self.fixed_combo.addItems(["True", "False"])
        model_layout.addWidget(fixed_label, 1, 0)
        model_layout.addWidget(self.fixed_combo, 1, 1)

        criterion_label = QLabel("带宽准则")
        self.criterion_combo = ModernComboBox()
        self.criterion_combo.addItems(["AICc", "AIC", "BIC", "CV"])
        model_layout.addWidget(criterion_label, 1, 2)
        model_layout.addWidget(self.criterion_combo, 1, 3)

        for column in range(4):
            model_layout.setColumnStretch(column, 1)
        main_layout.addWidget(model_group)

        variable_group = QGroupBox("变量选择")
        variable_layout = QGridLayout(variable_group)
        variable_layout.setHorizontalSpacing(16)
        variable_layout.setVerticalSpacing(12)

        self.y_label = QLabel("因变量")
        self.y_combo = ModernComboBox()
        variable_layout.addWidget(self.y_label, 0, 0)
        variable_layout.addWidget(self.y_combo, 0, 1)

        self.time_label = QLabel("时间列")
        self.time_combo = ModernComboBox()
        variable_layout.addWidget(self.time_label, 0, 2)
        variable_layout.addWidget(self.time_combo, 0, 3)

        missing_label = QLabel("空值处理")
        self.missing_strategy_combo = ModernComboBox()
        self.missing_strategy_combo.addItem("忽略含空值行", userData="drop")
        self.missing_strategy_combo.addItem("用指定值填充", userData="fill")
        self.missing_strategy_combo.currentIndexChanged.connect(self.update_missing_value_state)
        variable_layout.addWidget(missing_label, 1, 0)
        variable_layout.addWidget(self.missing_strategy_combo, 1, 1)

        fill_label = QLabel("填充值")
        self.missing_fill_input = ModernLineEdit()
        self.missing_fill_input.setPlaceholderText("当空值处理为填充时生效，例如 0")
        variable_layout.addWidget(fill_label, 1, 2)
        variable_layout.addWidget(self.missing_fill_input, 1, 3)

        x_label = QLabel("自变量（多选）")
        self.x_list = ModernListWidget()
        self.x_list.setSelectionMode(QListWidget.MultiSelection)
        self.x_list.setMinimumHeight(220)
        self.x_list.itemSelectionChanged.connect(self.update_selection_counts)
        self.x_count_label = QLabel("已选 0 项")
        self.x_count_label.setStyleSheet("color: #64748b;")
        self.x_clear_button = TransparentPushButton("清空已选")
        self.x_clear_button.clicked.connect(lambda: self.clear_list_selection(self.x_list))
        variable_layout.addWidget(x_label, 2, 0)
        variable_layout.addWidget(self.x_list, 2, 1)
        variable_layout.addWidget(self.x_count_label, 3, 1, alignment=Qt.AlignRight)
        variable_layout.addWidget(self.x_clear_button, 4, 1, alignment=Qt.AlignRight)

        coords_label = QLabel("坐标列（请选择 2 列）")
        self.coords_list = ModernListWidget()
        self.coords_list.setSelectionMode(QListWidget.MultiSelection)
        self.coords_list.setMinimumHeight(220)
        self.coords_list.itemSelectionChanged.connect(self.update_selection_counts)
        self.coords_count_label = QLabel("已选 0 项")
        self.coords_count_label.setStyleSheet("color: #64748b;")
        self.coords_clear_button = TransparentPushButton("清空已选")
        self.coords_clear_button.clicked.connect(lambda: self.clear_list_selection(self.coords_list))
        variable_layout.addWidget(coords_label, 2, 2)
        variable_layout.addWidget(self.coords_list, 2, 3)
        variable_layout.addWidget(self.coords_count_label, 3, 3, alignment=Qt.AlignRight)
        variable_layout.addWidget(self.coords_clear_button, 4, 3, alignment=Qt.AlignRight)

        append_label = QLabel("追加字段（导出到 coefficients）")
        self.append_fields_list = ModernListWidget()
        self.append_fields_list.setSelectionMode(QListWidget.MultiSelection)
        self.append_fields_list.setMinimumHeight(180)
        self.append_fields_list.itemSelectionChanged.connect(self.update_selection_counts)
        self.append_fields_count_label = QLabel("已选 0 项")
        self.append_fields_count_label.setStyleSheet("color: #64748b;")
        self.append_fields_clear_button = TransparentPushButton("清空已选")
        self.append_fields_clear_button.clicked.connect(lambda: self.clear_list_selection(self.append_fields_list))
        variable_layout.addWidget(append_label, 5, 0)
        variable_layout.addWidget(self.append_fields_list, 5, 1, 1, 3)
        variable_layout.addWidget(self.append_fields_count_label, 6, 3, alignment=Qt.AlignRight)
        variable_layout.addWidget(self.append_fields_clear_button, 7, 3, alignment=Qt.AlignRight)

        for column in range(4):
            variable_layout.setColumnStretch(column, 1)
        main_layout.addWidget(variable_group)

        parameter_group = QGroupBox("参数设置")
        self.param_layout = QVBoxLayout(parameter_group)
        self.param_layout.setSpacing(10)
        main_layout.addWidget(parameter_group)

        footer_layout = QHBoxLayout()
        self.status_label = QLabel("状态：等待开始")
        self.status_label.setStyleSheet("color: #475569;")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        footer_layout.addWidget(self.status_label)

        analyze_button = ModernButton("开始分析")
        analyze_button.clicked.connect(self.start_analysis)
        footer_layout.addWidget(analyze_button)
        main_layout.addLayout(footer_layout)

        self.update_missing_value_state()
        self.update_model_state(self.model_combo.currentText())

    def open_help(self):
        help_path = get_resource_path("template/index.html")
        QDesktopServices.openUrl(QUrl.fromLocalFile(help_path))

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
        if message:
            self.console_output.append_message(message, task_id=task_id)
            self.status_label.setText(f"状态：{message}")
        elif kind == "log" and task_id is not None:
            self.console_output.append_message(event.get("message", ""), task_id=task_id)

    def import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            self.console_output.append("未选择输入文件")
            return

        try:
            self.excel_data = ExcelDataLoader.load_excel(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取 Excel 文件：{exc}")
            self.console_output.append(f"读取 Excel 失败: {exc}")
            return

        self.input_file_path = file_path
        self.file_label.setText(f"输入文件：{file_path}")
        self.console_output.append(f"已选择输入文件: {file_path}")
        self.populate_headers()

    def output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "选择输出 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            self.console_output.append("未选择输出文件")
            return

        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"

        self.output_file_path = file_path
        self.output_file_label.setText(f"输出文件：{file_path}")
        self.console_output.append(f"已选择输出文件: {file_path}")

    def populate_headers(self):
        headers = self.excel_data.columns.tolist()
        self.y_combo.clear()
        self.x_list.clear()
        self.coords_list.clear()
        self.append_fields_list.clear()
        self.time_combo.clear()

        self.y_combo.addItems(headers)
        self.time_combo.addItems(headers)
        for header in headers:
            self.x_list.addItem(QListWidgetItem(header))
            self.coords_list.addItem(QListWidgetItem(header))
            self.append_fields_list.addItem(QListWidgetItem(header))
        self.update_selection_counts()

    def update_selection_counts(self):
        self.x_count_label.setText(f"已选 {len(self.x_list.selectedItems())} 项")
        self.coords_count_label.setText(f"已选 {len(self.coords_list.selectedItems())} 项")
        self.append_fields_count_label.setText(f"已选 {len(self.append_fields_list.selectedItems())} 项")

    def clear_list_selection(self, list_widget):
        list_widget.clearSelection()

    def update_missing_value_state(self):
        strategy = self.current_missing_strategy()
        self.missing_fill_input.setEnabled(strategy == "fill")
        if strategy != "fill":
            self.missing_fill_input.clear()

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout(child_layout)

    def update_model_state(self, model):
        self.model_desc_label.setText(MODEL_DESCRIPTIONS.get(model, ""))
        is_temporal = model in TEMPORAL_MODELS
        self.time_label.setEnabled(is_temporal)
        self.time_combo.setEnabled(is_temporal)
        if not is_temporal:
            self.time_combo.setCurrentIndex(-1)

        self.clear_layout(self.param_layout)
        self.dynamic_inputs = create_model_param_box(model, self.param_layout)

    def start_analysis(self):
        model = self.model_combo.currentText()
        validation_error = self.validate_inputs(model)
        if validation_error:
            QMessageBox.warning(self, "输入不完整", validation_error)
            self.console_output.append(validation_error)
            self.status_label.setText(f"状态：{validation_error}")
            return

        y_var = self.y_combo.currentText()
        x_vars = [item.text() for item in self.x_list.selectedItems()]
        coords = [item.text() for item in self.coords_list.selectedItems()]
        t_var = self.time_combo.currentText() if model in TEMPORAL_MODELS else None
        kernel = self.kernel_combo.currentText()
        fixed = self.fixed_combo.currentText() == "True"
        criterion = self.criterion_combo.currentText()

        try:
            params = self.collect_dynamic_parameters(model)
        except ValueError as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            self.console_output.append(str(exc))
            self.status_label.setText(f"状态：{exc}")
            return

        missing_strategy = self.current_missing_strategy()
        params["missing_strategy"] = missing_strategy
        params["append_original_fields"] = [item.text() for item in self.append_fields_list.selectedItems()]
        if missing_strategy == "fill":
            try:
                params["missing_fill_value"] = self.parse_missing_fill_value()
            except ValueError as exc:
                QMessageBox.warning(self, "空值处理设置无效", str(exc))
                self.console_output.append(str(exc))
                self.status_label.setText(f"状态：{exc}")
                return
        else:
            params["missing_fill_value"] = None

        task_id = self.task_manager.create_task_id()
        process_args = (
            task_id,
            self.input_file_path,
            self.output_file_path,
            y_var,
            x_vars,
            coords,
            t_var,
            kernel,
            fixed,
            criterion,
            model,
            params,
            self.output_queue,
        )
        analysis_process_instance = Process(target=analysis_process, args=process_args)

        self.console_output.add_task_console(task_id, f"{model} #{task_id}")
        self.console_output.clear_task_console(task_id)
        self.status_label.setText(f"状态：任务 {task_id} 已启动")
        self.console_output.append_message(f"开始创建 {model} 分析任务，任务ID: {task_id}", task_id=task_id)

        try:
            analysis_process_instance.start()
            self.task_manager.add_task(task_id, analysis_process_instance, "进程", name=f"{model} 分析")
            self.task_manager.refresh_process_monitor(task_id)
            self.console_output.activate_task_console(task_id)
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", f"无法启动分析任务：{exc}")
            self.console_output.append(f"无法启动分析任务: {exc}")
            self.status_label.setText(f"状态：无法启动任务 {task_id}")

    def validate_inputs(self, model):
        if self.input_file_path is None:
            return "请先导入 Excel 文件"
        if self.output_file_path is None:
            return "请先选择输出文件"
        if self.excel_data is None or self.excel_data.empty:
            return "导入的数据为空，无法分析"

        x_vars = [item.text() for item in self.x_list.selectedItems()]
        coords = [item.text() for item in self.coords_list.selectedItems()]
        if not x_vars:
            return "请至少选择一个自变量"
        if len(coords) != 2:
            return "坐标列必须且只能选择 2 列"

        y_var = self.y_combo.currentText()
        if y_var in x_vars:
            return "因变量不能同时出现在自变量中"
        if y_var in coords:
            return "因变量不能作为坐标列"

        if model in TEMPORAL_MODELS:
            t_var = self.time_combo.currentText()
            if not t_var:
                return "当前模型需要选择时间列"
            if t_var in x_vars:
                return "时间列不能同时出现在自变量中"
            if t_var in coords:
                return "时间列不能作为坐标列"

        return None

    def collect_dynamic_parameters(self, model):
        params = {
            "thread": self.get_widget_value(self.dynamic_inputs["thread"], "线程数"),
            "constant": self.get_widget_value(self.dynamic_inputs["constant"], "包含截距项"),
            "convert": self.get_widget_value(self.dynamic_inputs["convert"], "经纬度转平面坐标"),
            "verbose": self.get_widget_value(self.dynamic_inputs["verbose"], "输出搜索过程"),
            "time_cost": self.get_widget_value(self.dynamic_inputs["time_cost"], "输出耗时"),
        }

        if model == "GWR":
            params.update({
                "bw_min": self.get_widget_value(self.dynamic_inputs["bw_min"], "带宽最小值", allow_empty=True),
                "bw_max": self.get_widget_value(self.dynamic_inputs["bw_max"], "带宽最大值", allow_empty=True),
                "tol": self.get_widget_value(self.dynamic_inputs["tol"], "收敛公差", allow_empty=False),
                "bw_decimal": self.get_widget_value(self.dynamic_inputs["bw_decimal"], "带宽精度"),
                "max_iter": self.get_widget_value(self.dynamic_inputs["max_iter"], "最大迭代次数"),
            })
        elif model == "MGWR":
            params.update({
                "bw_min": self.get_widget_value(self.dynamic_inputs["bw_min"], "带宽最小值", allow_empty=True),
                "bw_max": self.get_widget_value(self.dynamic_inputs["bw_max"], "带宽最大值", allow_empty=True),
                "tol": self.get_widget_value(self.dynamic_inputs["tol"], "收敛公差", allow_empty=False),
                "bw_decimal": self.get_widget_value(self.dynamic_inputs["bw_decimal"], "带宽精度"),
                "init_bw": self.get_widget_value(self.dynamic_inputs["init_bw"], "初始带宽", allow_empty=True),
                "multi_bw_min": self.get_widget_value(self.dynamic_inputs["multi_bw_min"], "多带宽最小值", allow_empty=True),
                "multi_bw_max": self.get_widget_value(self.dynamic_inputs["multi_bw_max"], "多带宽最大值", allow_empty=True),
                "tol_multi": self.get_widget_value(self.dynamic_inputs["tol_multi"], "多带宽收敛公差", allow_empty=False),
                "bws_same_times": self.get_widget_value(self.dynamic_inputs["bws_same_times"], "稳定次数阈值"),
                "rss_score": self.get_widget_value(self.dynamic_inputs["rss_score"], "RSS 评分"),
                "n_chunks": self.get_widget_value(self.dynamic_inputs["n_chunks"], "分块数"),
                "skip_calculate": self.get_widget_value(self.dynamic_inputs["skip_calculate"], "跳过推断"),
            })
        elif model == "GTWR":
            params.update({
                "bw_min": self.get_widget_value(self.dynamic_inputs["bw_min"], "带宽最小值", allow_empty=True),
                "bw_max": self.get_widget_value(self.dynamic_inputs["bw_max"], "带宽最大值", allow_empty=True),
                "tau_min": self.get_widget_value(self.dynamic_inputs["tau_min"], "时空尺度最小值", allow_empty=True),
                "tau_max": self.get_widget_value(self.dynamic_inputs["tau_max"], "时空尺度最大值", allow_empty=True),
                "tol": self.get_widget_value(self.dynamic_inputs["tol"], "收敛公差", allow_empty=False),
                "bw_decimal": self.get_widget_value(self.dynamic_inputs["bw_decimal"], "带宽精度"),
                "tau_decimal": self.get_widget_value(self.dynamic_inputs["tau_decimal"], "时空尺度精度"),
                "max_iter": self.get_widget_value(self.dynamic_inputs["max_iter"], "最大迭代次数"),
            })
        elif model == "MGTWR":
            params.update({
                "bw_min": self.get_widget_value(self.dynamic_inputs["bw_min"], "带宽最小值", allow_empty=True),
                "bw_max": self.get_widget_value(self.dynamic_inputs["bw_max"], "带宽最大值", allow_empty=True),
                "tau_min": self.get_widget_value(self.dynamic_inputs["tau_min"], "时空尺度最小值", allow_empty=True),
                "tau_max": self.get_widget_value(self.dynamic_inputs["tau_max"], "时空尺度最大值", allow_empty=True),
                "tol": self.get_widget_value(self.dynamic_inputs["tol"], "收敛公差", allow_empty=False),
                "bw_decimal": self.get_widget_value(self.dynamic_inputs["bw_decimal"], "带宽精度"),
                "tau_decimal": self.get_widget_value(self.dynamic_inputs["tau_decimal"], "时空尺度精度"),
                "init_bw": self.get_widget_value(self.dynamic_inputs["init_bw"], "初始带宽", allow_empty=True),
                "init_tau": self.get_widget_value(self.dynamic_inputs["init_tau"], "初始时空尺度", allow_empty=True),
                "multi_bw_min": self.get_widget_value(self.dynamic_inputs["multi_bw_min"], "多带宽最小值", allow_empty=True),
                "multi_bw_max": self.get_widget_value(self.dynamic_inputs["multi_bw_max"], "多带宽最大值", allow_empty=True),
                "multi_tau_min": self.get_widget_value(self.dynamic_inputs["multi_tau_min"], "多时空尺度最小值", allow_empty=True),
                "multi_tau_max": self.get_widget_value(self.dynamic_inputs["multi_tau_max"], "多时空尺度最大值", allow_empty=True),
                "tol_multi": self.get_widget_value(self.dynamic_inputs["tol_multi"], "多带宽收敛公差", allow_empty=False),
                "rss_score": self.get_widget_value(self.dynamic_inputs["rss_score"], "RSS 评分"),
                "n_chunks": self.get_widget_value(self.dynamic_inputs["n_chunks"], "分块数"),
                "skip_calculate": self.get_widget_value(self.dynamic_inputs["skip_calculate"], "跳过推断"),
            })

        return params

    def get_widget_value(self, widget, field_name, allow_empty=False):
        if isinstance(widget, QSpinBox):
            return int(widget.value())
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QLineEdit):
            text = widget.text().strip()
            if not text:
                return None if allow_empty else self.raise_required(field_name)
            if "," in text:
                try:
                    return [float(item.strip()) for item in text.split(",") if item.strip()]
                except ValueError as exc:
                    raise ValueError(f"{field_name} 必须是逗号分隔的数字列表") from exc
            try:
                if any(char in text.lower() for char in [".", "e"]):
                    return float(text)
                return int(text)
            except ValueError:
                try:
                    return float(text)
                except ValueError as exc:
                    raise ValueError(f"{field_name} 输入无效：{text}") from exc
        return None

    def raise_required(self, field_name):
        raise ValueError(f"{field_name} 不能为空")

    def current_missing_strategy(self):
        index = self.missing_strategy_combo.currentIndex()
        strategy = self.missing_strategy_combo.itemData(index)
        return strategy or "drop"

    def parse_missing_fill_value(self):
        text = self.missing_fill_input.text().strip()
        if not text:
            raise ValueError("空值处理选择“用指定值填充”时，必须填写填充值")
        try:
            if any(char in text.lower() for char in [".", "e"]):
                return float(text)
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError as exc:
                raise ValueError(f"填充值必须是数字：{text}") from exc
