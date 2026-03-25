import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from utils.urltools import get_resource_path
from utils.dataframe_loader import ExcelDataLoader
from utils.xlsx_tools import (
    filter_out_selected_provinces,
    generate_year_for_base_table,
    get_province_in_base_table,
    save_table_to_excel,
)
from views.components.button import ModernButton
from views.components.list_widget import ModernListWidget


class DataGenerationPage(QWidget):
    def __init__(self, console_output):
        super().__init__()
        self.console_output = console_output
        self.selected_file_path = None
        self.generated_table = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title_label = QLabel("数据生成")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 28px; font-weight: 700; color: #0f172a;")
        layout.addWidget(title_label)

        intro_label = QLabel("从模板或自定义基础表生成多年份省级数据表，适合后续爬取和分析流程。")
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet("color: #64748b;")
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        file_group = QGroupBox("基础表来源")
        file_layout = QVBoxLayout(file_group)
        file_button = ModernButton("选择自定义 Excel 文件")
        file_button.clicked.connect(self.select_file)
        self.file_label = QLabel("当前来源：默认模板")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(file_button)
        file_layout.addWidget(self.file_label)
        layout.addWidget(file_group)

        province_group = QGroupBox("省份选择")
        province_layout = QVBoxLayout(province_group)
        self.province_list = ModernListWidget()
        self.province_list.setSelectionMode(QListWidget.MultiSelection)
        self.province_list.setMinimumHeight(260)
        self.province_list.itemSelectionChanged.connect(self.update_province_selection_count)
        for province in get_province_in_base_table():
            self.province_list.addItem(QListWidgetItem(province))
        province_layout.addWidget(self.province_list)

        self.province_count_label = QLabel("已选 0 项")
        self.province_count_label.setStyleSheet("color: #64748b;")
        self.province_count_label.setAlignment(Qt.AlignRight)
        province_layout.addWidget(self.province_count_label)

        province_button_layout = QHBoxLayout()
        select_all_button = ModernButton("全选省份")
        select_all_button.clicked.connect(self.select_all_provinces)
        deselect_all_button = ModernButton("清空已选")
        deselect_all_button.clicked.connect(self.deselect_all_provinces)
        province_button_layout.addWidget(select_all_button)
        province_button_layout.addWidget(deselect_all_button)
        province_button_layout.addStretch(1)
        province_layout.addLayout(province_button_layout)
        layout.addWidget(province_group)

        year_group = QGroupBox("年份设置")
        year_layout = QVBoxLayout(year_group)
        year_hint = QLabel("输入格式：`2020,2021,2022` 或 `2019-2022`")
        year_hint.setStyleSheet("color: #64748b;")
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("例如：2020,2021,2022 或 2019-2022")
        year_layout.addWidget(year_hint)
        year_layout.addWidget(self.year_input)
        layout.addWidget(year_group)

        action_layout = QHBoxLayout()
        generate_button = ModernButton("生成数据")
        generate_button.clicked.connect(self.generate_data)
        save_button = ModernButton("保存数据")
        save_button.clicked.connect(self.save_data)
        action_layout.addWidget(generate_button)
        action_layout.addWidget(save_button)
        action_layout.addStretch(1)
        layout.addLayout(action_layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            self.console_output.append("未选择自定义基础表，继续使用默认模板")
            return

        self.selected_file_path = file_path
        self.file_label.setText(f"当前来源：{file_path}")
        self.console_output.append(f"已选择自定义基础表: {file_path}")

    def select_all_provinces(self):
        for i in range(self.province_list.count()):
            self.province_list.item(i).setSelected(True)
        self.update_province_selection_count()
        self.console_output.append("所有省份已全选")

    def deselect_all_provinces(self):
        for i in range(self.province_list.count()):
            self.province_list.item(i).setSelected(False)
        self.update_province_selection_count()
        self.console_output.append("已取消所有省份选择")

    def update_province_selection_count(self):
        self.province_count_label.setText(f"已选 {len(self.province_list.selectedItems())} 项")

    def generate_data(self):
        try:
            selected_province = [item.text() for item in self.province_list.selectedItems()]
            if not selected_province:
                QMessageBox.warning(self, "缺少省份", "请至少选择一个省份")
                self.console_output.append("未选择任何省份")
                return

            years = self.get_years_from_input(self.year_input.text())
            if not years:
                QMessageBox.warning(self, "年份无效", "年份格式错误，请输入逗号分隔年份或起止年份")
                self.console_output.append("年份输入无效，请重新输入")
                return

            self.console_output.append("正在生成数据...")
            if self.selected_file_path:
                self.console_output.append(f"使用用户提供的 Excel 文件: {self.selected_file_path}")
                base_table = ExcelDataLoader.load_excel(self.selected_file_path)
            else:
                default_template = get_resource_path('template/provincial_latitude_longitude.xlsx')
                self.console_output.append(f"使用默认基础表: {default_template}")
                base_table = ExcelDataLoader.load_excel(default_template)

            filtered_table = filter_out_selected_provinces(selected_province, base_table)
            self.generated_table = generate_year_for_base_table(years, filtered_table)
            self.console_output.append(f"数据生成完成，共 {len(self.generated_table)} 条记录")
        except Exception as exc:
            QMessageBox.critical(self, "生成失败", f"生成数据时发生错误：{exc}")
            self.console_output.append(f"生成数据时发生错误: {exc}")

    def get_years_from_input(self, input_text):
        try:
            text = input_text.strip()
            if not text:
                return None
            if '-' in text:
                start_year, end_year = map(int, text.split('-'))
                if start_year > end_year:
                    return None
                return list(range(start_year, end_year + 1))
            return [int(year.strip()) for year in text.split(',') if year.strip()]
        except ValueError:
            return None

    def save_data(self):
        if self.generated_table is None:
            QMessageBox.information(self, "暂无数据", "请先生成数据再保存")
            self.console_output.append("没有生成数据，无法保存")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "保存数据", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            self.console_output.append("未选择保存路径")
            return

        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"

        try:
            save_table_to_excel(self.generated_table, file_path)
            self.console_output.append(f"数据已保存至 {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"保存数据时发生错误：{exc}")
            self.console_output.append(f"保存数据时发生错误: {exc}")
