import pandas as pd
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.application.services.spatial_export import CoefficientsSpatialExporter
from app.core.urltools import get_resource_path
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.input import ModernLineEdit


class CoefficientsToShpWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("coefficients 转 Shapefile")
        self.resize(820, 640)
        self.setMinimumSize(760, 560)
        self.setWindowIcon(QIcon(get_resource_path("favicon.ico")))

        self.dataframe = None
        self.input_path = None
        self.output_path = None
        self.sheet_names = []
        self.init_ui()

    def init_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        file_group = QGroupBox("结果文件")
        file_layout = QVBoxLayout(file_group)
        button_row = QHBoxLayout()
        load_button = ModernButton("选择结果 Excel")
        load_button.clicked.connect(self.select_input_file)
        save_button = ModernButton("选择输出 shp")
        save_button.clicked.connect(self.select_output_file)
        button_row.addWidget(load_button)
        button_row.addWidget(save_button)
        file_layout.addLayout(button_row)
        self.input_label = QLabel("输入文件：未选择")
        self.input_label.setWordWrap(True)
        self.output_label = QLabel("输出文件：未选择")
        self.output_label.setWordWrap(True)
        file_layout.addWidget(self.input_label)
        file_layout.addWidget(self.output_label)
        layout.addWidget(file_group)

        option_group = QGroupBox("导出设置")
        option_layout = QVBoxLayout(option_group)

        sheet_row = QHBoxLayout()
        sheet_row.addWidget(QLabel("工作表"))
        self.sheet_combo = ModernComboBox()
        self.sheet_combo.currentIndexChanged.connect(self.reload_selected_sheet)
        sheet_row.addWidget(self.sheet_combo)
        option_layout.addLayout(sheet_row)

        coord_row = QHBoxLayout()
        coord_row.addWidget(QLabel("经度列"))
        self.longitude_combo = ModernComboBox()
        coord_row.addWidget(self.longitude_combo)
        coord_row.addWidget(QLabel("纬度列"))
        self.latitude_combo = ModernComboBox()
        coord_row.addWidget(self.latitude_combo)
        option_layout.addLayout(coord_row)

        projection_row = QHBoxLayout()
        projection_row.addWidget(QLabel("投影"))
        self.projection_input = ModernLineEdit()
        self.projection_input.setText("EPSG:4326")
        self.projection_input.setPlaceholderText("例如 EPSG:4326")
        projection_row.addWidget(self.projection_input)
        option_layout.addLayout(projection_row)

        export_button = ModernButton("导出 Shapefile")
        export_button.clicked.connect(self.export_shapefile)
        option_layout.addWidget(export_button)
        layout.addWidget(option_group)

        result_group = QGroupBox("输出结果")
        result_layout = QVBoxLayout(result_group)
        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        result_layout.addWidget(self.result_output)
        layout.addWidget(result_group)

        self.setCentralWidget(container)

    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择结果 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return
        self.input_path = file_path
        self.input_label.setText(f"输入文件：{file_path}")
        self.load_workbook()

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "选择输出 shp 文件", "", "Shapefile (*.shp)")
        if not file_path:
            return
        if not file_path.lower().endswith(".shp"):
            file_path = f"{file_path}.shp"
        self.output_path = file_path
        self.output_label.setText(f"输出文件：{file_path}")

    def load_workbook(self):
        if not self.input_path:
            return
        try:
            dataframe, sheet_names, resolved_sheet = CoefficientsSpatialExporter.load_excel_sheet(self.input_path)
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取结果文件：{exc}")
            return

        self.sheet_names = sheet_names
        self.sheet_combo.clear()
        for sheet_name in self.sheet_names:
            self.sheet_combo.addItem(sheet_name, userData=sheet_name)
        index = self.sheet_combo.findData(resolved_sheet)
        if index >= 0:
            self.sheet_combo.setCurrentIndex(index)
        self.dataframe = dataframe
        self.populate_coordinate_columns()
        self.result_output.setText(f"已加载工作表：{resolved_sheet}\n共 {len(dataframe)} 行，{len(dataframe.columns)} 列")

    def reload_selected_sheet(self):
        if not self.input_path or self.sheet_combo.currentIndex() < 0:
            return
        try:
            dataframe, _, resolved_sheet = CoefficientsSpatialExporter.load_excel_sheet(
                self.input_path,
                self.sheet_combo.currentData(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取工作表：{exc}")
            return

        self.dataframe = dataframe
        self.populate_coordinate_columns()
        self.result_output.setText(f"已切换到工作表：{resolved_sheet}\n共 {len(dataframe)} 行，{len(dataframe.columns)} 列")

    def populate_coordinate_columns(self):
        if self.dataframe is None:
            return
        candidates = CoefficientsSpatialExporter.numeric_candidate_columns(self.dataframe)
        self.longitude_combo.clear()
        self.latitude_combo.clear()
        for column in candidates:
            self.longitude_combo.addItem(column, userData=column)
            self.latitude_combo.addItem(column, userData=column)

        lon_index = self.find_preferred_column(self.longitude_combo, ["经度", "lng", "lon", "long"])
        lat_index = self.find_preferred_column(self.latitude_combo, ["纬度", "lat"])
        if lon_index >= 0:
            self.longitude_combo.setCurrentIndex(lon_index)
        elif self.longitude_combo.count() > 0:
            self.longitude_combo.setCurrentIndex(0)
        if lat_index >= 0:
            self.latitude_combo.setCurrentIndex(lat_index)
        elif self.latitude_combo.count() > 1:
            self.latitude_combo.setCurrentIndex(1)

    @staticmethod
    def find_preferred_column(combo, keywords):
        for index in range(combo.count()):
            column = str(combo.itemData(index) or "").lower()
            if any(keyword in column for keyword in keywords):
                return index
        return -1

    def export_shapefile(self):
        if self.dataframe is None:
            QMessageBox.information(self, "缺少数据", "请先选择结果 Excel 文件")
            return
        if not self.output_path:
            QMessageBox.information(self, "缺少输出路径", "请先选择输出 shp 文件")
            return

        longitude_column = self.longitude_combo.currentData()
        latitude_column = self.latitude_combo.currentData()
        projection = self.projection_input.text().strip() or "EPSG:4326"

        try:
            exported_rows, renamed_fields = CoefficientsSpatialExporter.export_to_shp(
                self.dataframe,
                self.output_path,
                longitude_column,
                latitude_column,
                projection=projection,
            )
        except Exception as exc:
            self.result_output.setText(f"导出失败：{exc}")
            return

        renamed_hint = "、".join(map(str, renamed_fields[:8]))
        if len(renamed_fields) > 8:
            renamed_hint += " ..."
        self.result_output.setText(
            f"导出成功\n"
            f"输出文件：{self.output_path}\n"
            f"导出要素数：{exported_rows}\n"
            f"字段名已按 Shapefile 规则压缩，示例：{renamed_hint}"
        )

