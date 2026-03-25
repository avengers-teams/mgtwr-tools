from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SpinBox, SubtitleLabel, TitleLabel

from utils.model_visualization import VisualizationData
from utils.significance_visualization import (
    SignificanceChartFactory,
    SignificanceRenderOptions,
)
from views.components.button import ModernButton
from views.components.combobox import ModernComboBox
from views.components.fluent_surface import FrostedPanel
from views.components.input import ModernLineEdit


class MetricCard(FrostedPanel):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)

        self.value_label = TitleLabel("--")
        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("color: #5b6b84;")
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


class SignificanceAnalysisPage(QWidget):
    def __init__(self, console_output):
        super().__init__()
        self.console_output = console_output
        self.dataset = None
        self.selected_file_path = None
        self.chart_specs = []
        self.canvas = None
        self.metric_cards = {}
        self.coordinate_columns = []
        self.time_columns = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        header = FrostedPanel(hero=True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(14)
        header_layout.addWidget(TitleLabel("显著性分析"))
        desc = SubtitleLabel("针对 t 值做辅助分析，快速查看哪些区域、哪些时间点达到显著性阈值。")
        desc.setWordWrap(True)
        header_layout.addWidget(desc)
        action_row = QHBoxLayout()
        load_button = ModernButton("加载结果文件")
        load_button.clicked.connect(self.select_file)
        action_row.addWidget(load_button)
        action_row.addStretch(1)
        header_layout.addLayout(action_row)
        self.file_label = BodyLabel("当前文件：未选择")
        self.file_label.setWordWrap(True)
        header_layout.addWidget(self.file_label)
        layout.addWidget(header)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(12)
        metric_grid.setVerticalSpacing(12)
        metric_names = [("total", "样本数"), ("significant", "显著样本"), ("ratio", "显著占比")]
        for index, (key, title) in enumerate(metric_names):
            card = MetricCard(title)
            self.metric_cards[key] = card
            metric_grid.addWidget(card, 0, index)
        layout.addLayout(metric_grid)

        control_panel = FrostedPanel()
        control_layout = QGridLayout(control_panel)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setHorizontalSpacing(16)
        control_layout.setVerticalSpacing(12)

        control_layout.addWidget(QLabel("图表"), 0, 0)
        self.chart_combo = ModernComboBox()
        self.chart_combo.currentIndexChanged.connect(self.on_chart_changed)
        control_layout.addWidget(self.chart_combo, 0, 1)

        control_layout.addWidget(QLabel("t统计量"), 0, 2)
        self.t_combo = ModernComboBox()
        self.t_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.t_combo, 0, 3)

        control_layout.addWidget(QLabel("显著性阈值"), 1, 0)
        self.threshold_input = ModernLineEdit()
        self.threshold_input.setText("1.96")
        self.threshold_input.setPlaceholderText("例如 1.96")
        self.threshold_input.textChanged.connect(self.on_threshold_changed)
        control_layout.addWidget(self.threshold_input, 1, 1)

        control_layout.addWidget(QLabel("标题"), 1, 2)
        self.title_input = ModernLineEdit()
        self.title_input.setPlaceholderText("留空则使用默认标题")
        self.title_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.title_input, 1, 3)

        control_layout.addWidget(QLabel("经度列"), 2, 0)
        self.longitude_combo = ModernComboBox()
        self.longitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.longitude_combo, 2, 1)

        control_layout.addWidget(QLabel("纬度列"), 2, 2)
        self.latitude_combo = ModernComboBox()
        self.latitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.latitude_combo, 2, 3)

        control_layout.addWidget(QLabel("时间列"), 3, 0)
        self.time_column_combo = ModernComboBox()
        self.time_column_combo.currentIndexChanged.connect(self.on_time_column_changed)
        control_layout.addWidget(self.time_column_combo, 3, 1)

        control_layout.addWidget(QLabel("时间点"), 3, 2)
        self.time_value_combo = ModernComboBox()
        self.time_value_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.time_value_combo, 3, 3)

        control_layout.addWidget(QLabel("小数位"), 4, 0)
        self.decimal_spin = SpinBox()
        self.decimal_spin.setRange(0, 6)
        self.decimal_spin.setValue(4)
        self.decimal_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.decimal_spin, 4, 1)

        self.chart_hint_label = BodyLabel("请先加载包含 t_ 列的结果文件。")
        self.chart_hint_label.setWordWrap(True)
        self.chart_hint_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.chart_hint_label, 5, 0, 1, 4)
        layout.addWidget(control_panel)

        chart_panel = FrostedPanel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(18, 18, 18, 18)
        chart_layout.setSpacing(10)
        chart_layout.addWidget(SubtitleLabel("图形预览"))
        self.canvas_container = QWidget()
        self.canvas_container_layout = QVBoxLayout(self.canvas_container)
        self.canvas_container_layout.setContentsMargins(0, 0, 0, 0)
        placeholder = QLabel("加载结果文件后将在此处显示显著性图表")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setMinimumHeight(480)
        placeholder.setStyleSheet("color: #6b7280;")
        self.canvas_container_layout.addWidget(placeholder)
        chart_layout.addWidget(self.canvas_container)
        layout.addWidget(chart_panel, 1)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择结果 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return
        try:
            dataset = VisualizationData(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", f"无法读取结果文件：{exc}")
            self.console_output.append(f"显著性分析加载失败: {exc}")
            return
        if not dataset.t_columns:
            QMessageBox.warning(self, "缺少 t 值", "当前结果文件没有 t_ 字段，无法进行显著性分析")
            return

        self.dataset = dataset
        self.selected_file_path = file_path
        self.file_label.setText(f"当前文件：{file_path}")
        self.console_output.append(f"已加载显著性分析结果文件: {file_path}")
        self.populate_controls()
        self.render_current_chart()

    def populate_controls(self):
        if self.dataset is None:
            return
        self.chart_specs = SignificanceChartFactory.available_charts(self.dataset)
        self.chart_combo.clear()
        for spec in self.chart_specs:
            self.chart_combo.addItem(spec.label, userData=spec)

        self.t_combo.clear()
        for column in self.dataset.t_columns:
            self.t_combo.addItem(self.dataset.metric_display_name(column), userData=column)

        self.coordinate_columns = self.dataset.spatial_candidate_columns()
        self.time_columns = self.dataset.temporal_candidate_columns()
        self.populate_coordinate_combos()
        self.populate_time_combos()

        if self.chart_specs:
            self.chart_combo.setCurrentIndex(0)
        if self.dataset.t_columns:
            self.t_combo.setCurrentIndex(0)
        self.update_control_state()

    def populate_coordinate_combos(self):
        self.longitude_combo.clear()
        self.latitude_combo.clear()
        for column in self.coordinate_columns:
            self.longitude_combo.addItem(str(column), userData=column)
            self.latitude_combo.addItem(str(column), userData=column)
        defaults = list(self.dataset.coord_columns[:2]) if self.dataset is not None else []
        if len(defaults) == 2:
            lon_index = self.longitude_combo.findData(defaults[0])
            lat_index = self.latitude_combo.findData(defaults[1])
            if lon_index >= 0:
                self.longitude_combo.setCurrentIndex(lon_index)
            if lat_index >= 0:
                self.latitude_combo.setCurrentIndex(lat_index)

    def populate_time_combos(self):
        self.time_column_combo.clear()
        for column in self.time_columns:
            self.time_column_combo.addItem(str(column), userData=column)
        if self.dataset is not None and self.dataset.time_column:
            time_index = self.time_column_combo.findData(self.dataset.time_column)
            if time_index >= 0:
                self.time_column_combo.setCurrentIndex(time_index)
        elif self.time_columns:
            self.time_column_combo.setCurrentIndex(0)
        self.refresh_time_value_options()

    def refresh_time_value_options(self):
        self.time_value_combo.clear()
        time_column = self.time_column_combo.currentData()
        if not self.dataset or not time_column:
            return
        self.time_value_combo.addItem("全部时间", userData=None)
        for label, value in self.dataset.time_value_options(time_column):
            self.time_value_combo.addItem(label, userData=value)
        self.time_value_combo.setCurrentIndex(0)

    def on_time_column_changed(self):
        self.refresh_time_value_options()
        self.render_current_chart()

    def on_threshold_changed(self):
        self.update_metric_cards()
        self.render_current_chart()

    def on_chart_changed(self):
        self.update_control_state()
        self.render_current_chart()

    def current_chart_spec(self):
        index = self.chart_combo.currentIndex()
        if index < 0:
            return None
        return self.chart_combo.itemData(index)

    def current_t_column(self):
        index = self.t_combo.currentIndex()
        if index < 0:
            return None
        return self.t_combo.itemData(index)

    def current_render_options(self):
        return SignificanceRenderOptions(
            threshold=self.parse_float_input(self.threshold_input, 1.96),
            longitude_column=self.longitude_combo.currentData(),
            latitude_column=self.latitude_combo.currentData(),
            time_column=self.time_column_combo.currentData(),
            time_value=self.time_value_combo.currentData(),
            figure_title=self.title_input.text().strip() or None,
            decimal_places=self.decimal_spin.value(),
        )

    @staticmethod
    def parse_float_input(widget, default):
        text = widget.text().strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

    def update_control_state(self):
        spec = self.current_chart_spec()
        key = spec.key if spec else ""
        uses_spatial = key == "spatial"
        uses_temporal = key == "temporal"
        uses_time_slice = key in {"summary", "spatial"}
        self.longitude_combo.setEnabled(uses_spatial)
        self.latitude_combo.setEnabled(uses_spatial)
        self.time_column_combo.setEnabled(uses_temporal or uses_time_slice)
        self.time_value_combo.setEnabled(uses_time_slice and self.time_column_combo.count() > 0)

    def update_metric_cards(self):
        if self.dataset is None:
            return
        t_column = self.current_t_column()
        if not t_column:
            return
        try:
            stats = SignificanceChartFactory.significance_stats(self.dataset, t_column, self.current_render_options())
        except Exception:
            return
        self.metric_cards["total"].set_value(stats["total"])
        self.metric_cards["significant"].set_value(stats["significant"])
        self.metric_cards["ratio"].set_value(f"{stats['ratio']:.1%}")

    def render_current_chart(self):
        if self.dataset is None:
            return
        spec = self.current_chart_spec()
        t_column = self.current_t_column()
        if spec is None or t_column is None:
            return

        render_options = self.current_render_options()
        self.update_metric_cards()
        try:
            figure = SignificanceChartFactory.create_figure(self.dataset, t_column, spec.key, render_options)
        except Exception as exc:
            self.chart_hint_label.setText(f"图表渲染失败：{exc}")
            self.console_output.append(f"显著性图表渲染失败: {exc}")
            return

        self.chart_hint_label.setText(
            f"当前图表：{spec.label}，统计量：{self.dataset.metric_display_name(t_column)}，阈值：|t| >= {render_options.threshold:.4f}"
        )
        self.replace_canvas(FigureCanvas(figure))

    def replace_canvas(self, canvas):
        while self.canvas_container_layout.count():
            item = self.canvas_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.canvas = canvas
        self.canvas.setMinimumHeight(500)
        self.canvas_container_layout.addWidget(self.canvas)
