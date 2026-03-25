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

from utils.urltools import get_resource_path
from utils.dataframe_loader import ExcelDataLoader
from views.components.button import ModernButton
from views.components.list_widget import ModernListWidget


class VIFWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Variance Inflation Factor (VIF) 分析")
        self.resize(760, 620)
        self.setMinimumSize(680, 520)
        self.setWindowIcon(QIcon(get_resource_path("favicon.ico")))
        self.df = None
        self.initUI()

    def initUI(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        import_group = QGroupBox("数据导入")
        import_layout = QVBoxLayout(import_group)
        self.import_button = ModernButton("导入 Excel 文件")
        self.import_button.clicked.connect(self.import_file)
        self.file_label = QLabel("当前文件：未选择")
        self.file_label.setWordWrap(True)
        import_layout.addWidget(self.import_button)
        import_layout.addWidget(self.file_label)
        layout.addWidget(import_group)

        var_group = QGroupBox("自变量选择")
        var_layout = QVBoxLayout(var_group)
        self.var_list = ModernListWidget()
        self.var_list.setSelectionMode(QListWidget.MultiSelection)
        self.var_list.setMinimumHeight(220)
        self.var_list.itemSelectionChanged.connect(self.update_selection_count)
        var_layout.addWidget(self.var_list)
        selection_row = QHBoxLayout()
        self.selection_count_label = QLabel("已选 0 项")
        self.selection_count_label.setStyleSheet("color: #64748b;")
        self.clear_selection_button = TransparentPushButton("清空已选")
        self.clear_selection_button.clicked.connect(self.var_list.clearSelection)
        selection_row.addWidget(self.selection_count_label)
        selection_row.addStretch(1)
        selection_row.addWidget(self.clear_selection_button)
        var_layout.addLayout(selection_row)
        layout.addWidget(var_group)

        self.analyze_button = ModernButton("开始分析")
        self.analyze_button.clicked.connect(self.start_analysis)
        layout.addWidget(self.analyze_button)

        result_group = QGroupBox("输出结果")
        result_layout = QVBoxLayout(result_group)
        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        result_layout.addWidget(self.result_output)
        layout.addWidget(result_group)

        self.setCentralWidget(container)

    def import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return

        try:
            self.df = ExcelDataLoader.load_excel(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取 Excel 文件：{exc}")
            return

        self.file_label.setText(f"当前文件：{file_path}")
        self.populate_variable_list()

    def populate_variable_list(self):
        if self.df is None:
            return
        self.var_list.clear()
        for col in self.df.columns:
            self.var_list.addItem(QListWidgetItem(col))
        self.update_selection_count()

    def update_selection_count(self):
        self.selection_count_label.setText(f"已选 {len(self.var_list.selectedItems())} 项")

    def start_analysis(self):
        if self.df is None:
            QMessageBox.information(self, "缺少数据", "请先导入 Excel 文件")
            return

        selected_vars = [item.text() for item in self.var_list.selectedItems()]
        if not selected_vars:
            self.result_output.setText("请选择要进行分析的自变量。")
            return

        try:
            X = self.df[selected_vars]
            vif_data = pd.DataFrame()
            vif_data["Feature"] = X.columns
            vif_data["VIF"] = [self.calculate_vif(X.values, i) for i in range(X.shape[1])]
            self.result_output.setText("VIF 分析结果:\n" + vif_data.to_string(index=False))
        except Exception as exc:
            self.result_output.setText(f"分析过程中出现错误: {exc}")

    def calculate_vif(self, X, i):
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        return variance_inflation_factor(X, i)
