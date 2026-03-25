import pandas as pd
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import TransparentPushButton

from utils.dataframe_loader import ExcelDataLoader
from utils.standardization import StandardizationService
from utils.urltools import get_resource_path
from views.components.button import ModernButton
from views.components.combobox import ModernComboBox
from views.components.input import ModernLineEdit
from views.components.list_widget import ModernListWidget


class DataStandardizationWindow(QMainWindow):
    OUTPUT_MODES = [
        ("append", "追加新列"),
        ("replace", "替换原列"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据标准化工具")
        self.resize(860, 680)
        self.setMinimumSize(780, 600)
        self.setWindowIcon(QIcon(get_resource_path("favicon.ico")))
        self.df = None
        self.input_path = None
        self.output_path = None
        self.init_ui()

    def init_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        file_group = QGroupBox("数据文件")
        file_layout = QVBoxLayout(file_group)
        file_button_row = QHBoxLayout()
        import_button = ModernButton("导入 Excel")
        import_button.clicked.connect(self.select_input_file)
        output_button = ModernButton("选择输出文件")
        output_button.clicked.connect(self.select_output_file)
        file_button_row.addWidget(import_button)
        file_button_row.addWidget(output_button)
        file_layout.addLayout(file_button_row)
        self.input_label = QLabel("输入文件：未选择")
        self.input_label.setWordWrap(True)
        self.output_label = QLabel("输出文件：未选择")
        self.output_label.setWordWrap(True)
        file_layout.addWidget(self.input_label)
        file_layout.addWidget(self.output_label)
        layout.addWidget(file_group)

        column_group = QGroupBox("字段选择")
        column_layout = QVBoxLayout(column_group)
        self.column_list = ModernListWidget()
        self.column_list.setSelectionMode(QListWidget.MultiSelection)
        self.column_list.setMinimumHeight(220)
        self.column_list.itemSelectionChanged.connect(self.update_selection_count)
        column_layout.addWidget(self.column_list)
        selection_row = QHBoxLayout()
        self.selection_count_label = QLabel("已选 0 项")
        self.selection_count_label.setStyleSheet("color: #64748b;")
        clear_button = TransparentPushButton("清空已选")
        clear_button.clicked.connect(self.column_list.clearSelection)
        selection_row.addWidget(self.selection_count_label)
        selection_row.addStretch(1)
        selection_row.addWidget(clear_button)
        column_layout.addLayout(selection_row)
        layout.addWidget(column_group)

        method_group = QGroupBox("标准化设置")
        method_layout = QVBoxLayout(method_group)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("方法"))
        self.method_combo = ModernComboBox()
        for key, label in StandardizationService.method_items():
            self.method_combo.addItem(label, userData=key)
        method_row.addWidget(self.method_combo)
        method_row.addWidget(QLabel("输出模式"))
        self.output_mode_combo = ModernComboBox()
        for key, label in self.OUTPUT_MODES:
            self.output_mode_combo.addItem(label, userData=key)
        self.output_mode_combo.currentIndexChanged.connect(self.update_suffix_state)
        method_row.addWidget(self.output_mode_combo)
        method_layout.addLayout(method_row)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(QLabel("新列后缀"))
        self.suffix_input = ModernLineEdit()
        self.suffix_input.setText("std")
        self.suffix_input.setPlaceholderText("追加新列时使用，例如 std")
        suffix_row.addWidget(self.suffix_input)
        method_layout.addLayout(suffix_row)

        run_button = ModernButton("执行标准化并导出")
        run_button.clicked.connect(self.run_standardization)
        method_layout.addWidget(run_button)
        layout.addWidget(method_group)

        result_group = QGroupBox("输出结果")
        result_layout = QVBoxLayout(result_group)
        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        result_layout.addWidget(self.result_output)
        layout.addWidget(result_group)

        self.setCentralWidget(container)
        self.update_suffix_state()

    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return
        try:
            self.df = ExcelDataLoader.load_excel(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取 Excel 文件：{exc}")
            return

        self.input_path = file_path
        self.input_label.setText(f"输入文件：{file_path}")
        self.populate_column_list()
        self.result_output.setText(f"已加载数据，共 {len(self.df)} 行，{len(self.df.columns)} 列")

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "选择输出 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        self.output_path = file_path
        self.output_label.setText(f"输出文件：{file_path}")

    def populate_column_list(self):
        self.column_list.clear()
        if self.df is None:
            return
        numeric_columns = []
        for column in self.df.columns:
            numeric_series = pd.to_numeric(self.df[column], errors="coerce")
            if numeric_series.notna().any():
                numeric_columns.append(column)

        for column in numeric_columns:
            self.column_list.addItem(QListWidgetItem(str(column)))
        self.update_selection_count()

    def update_selection_count(self):
        self.selection_count_label.setText(f"已选 {len(self.column_list.selectedItems())} 项")

    def update_suffix_state(self):
        append_mode = self.output_mode_combo.currentData() == "append"
        self.suffix_input.setEnabled(append_mode)

    def run_standardization(self):
        if self.df is None:
            QMessageBox.information(self, "缺少数据", "请先导入 Excel 文件")
            return
        if not self.output_path:
            QMessageBox.information(self, "缺少输出路径", "请先选择输出文件")
            return

        columns = [item.text() for item in self.column_list.selectedItems()]
        method_key = self.method_combo.currentData()
        output_mode = self.output_mode_combo.currentData()
        suffix = self.suffix_input.text().strip()

        try:
            result_df, report_rows = StandardizationService.apply(
                self.df,
                columns,
                method_key,
                output_mode=output_mode,
                suffix=suffix,
            )
            report_df = pd.DataFrame(report_rows)
            with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
                result_df.to_excel(writer, sheet_name="data", index=False)
                report_df.to_excel(writer, sheet_name="report", index=False)
        except Exception as exc:
            self.result_output.setText(f"标准化失败：{exc}")
            return

        self.result_output.setText(
            f"标准化完成\n"
            f"输出文件：{self.output_path}\n\n"
            f"{report_df.to_string(index=False)}"
        )
