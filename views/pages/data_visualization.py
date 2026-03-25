from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SpinBox, SubtitleLabel, TitleLabel, TransparentPushButton

from utils.model_visualization import ChartFactory, RenderOptions, VisualizationData
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


class DataVisualizationPage(QWidget):
    PROJECTION_PRESETS = [
        ("EPSG:4326", "WGS 84 (EPSG:4326)"),
        ("EPSG:3857", "Web Mercator (EPSG:3857)"),
        ("EPSG:4490", "CGCS2000 (EPSG:4490)"),
        ("custom", "自定义投影"),
    ]

    STRETCH_METHODS = [
        ("equal_interval", "等距分级"),
        ("quantile", "分位数分级"),
        ("jenks", "自然断点"),
        ("log", "对数拉伸"),
    ]

    COLOR_PALETTES = [
        ("YlGnBu", "YlGnBu"),
        ("viridis", "Viridis"),
        ("OrRd", "OrRd"),
        ("Spectral", "Spectral"),
        ("coolwarm", "Coolwarm"),
    ]

    def __init__(self, console_output):
        super().__init__()
        self.console_output = console_output
        self.selected_file_path = None
        self.vector_file_path = None
        self.raster_file_path = None
        self.dataset = None
        self.chart_specs = []
        self.canvas = None
        self.metric_cards = {}
        self.coordinate_columns = []
        self.time_columns = []
        self.category_columns = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        header = FrostedPanel(hero=True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(14)

        header_layout.addWidget(TitleLabel("数据可视化"))
        desc = SubtitleLabel("加载模型分析结果，可直接查看散点图、时间曲线、尺度历史，也可叠加 shp / 栅格生成区域着色图。")
        desc.setWordWrap(True)
        header_layout.addWidget(desc)

        action_row = QHBoxLayout()
        load_button = ModernButton("加载结果文件")
        load_button.clicked.connect(self.select_file)
        save_button = TransparentPushButton("导出当前图")
        save_button.clicked.connect(self.save_current_figure)
        action_row.addWidget(load_button)
        action_row.addWidget(save_button)
        action_row.addStretch(1)
        header_layout.addLayout(action_row)

        self.file_label = BodyLabel("当前文件：未选择")
        self.file_label.setWordWrap(True)
        header_layout.addWidget(self.file_label)
        layout.addWidget(header)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(12)
        metric_grid.setVerticalSpacing(12)
        metric_names = [
            ("model", "模型"),
            ("R2", "R²"),
            ("aic", "AIC"),
            ("samples", "样本数"),
        ]
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

        control_layout.addWidget(QLabel("变量"), 0, 2)
        self.beta_combo = ModernComboBox()
        self.beta_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.beta_combo, 0, 3)

        vector_button = TransparentPushButton("选择 shp/geojson")
        vector_button.clicked.connect(self.select_vector_file)
        raster_button = TransparentPushButton("选择栅格")
        raster_button.clicked.connect(self.select_raster_file)
        clear_raster_button = TransparentPushButton("清空栅格")
        clear_raster_button.clicked.connect(self.clear_raster_file)
        control_layout.addWidget(vector_button, 1, 0)
        control_layout.addWidget(raster_button, 1, 2)
        control_layout.addWidget(clear_raster_button, 1, 3, alignment=Qt.AlignLeft)

        self.vector_label = BodyLabel("边界文件：未选择")
        self.vector_label.setWordWrap(True)
        control_layout.addWidget(self.vector_label, 2, 0, 1, 2)

        self.raster_label = BodyLabel("栅格文件：未选择")
        self.raster_label.setWordWrap(True)
        control_layout.addWidget(self.raster_label, 2, 2, 1, 2)

        control_layout.addWidget(QLabel("经度列"), 3, 0)
        self.longitude_combo = ModernComboBox()
        self.longitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.longitude_combo, 3, 1)

        control_layout.addWidget(QLabel("纬度列"), 3, 2)
        self.latitude_combo = ModernComboBox()
        self.latitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.latitude_combo, 3, 3)

        control_layout.addWidget(QLabel("时间列"), 4, 0)
        self.time_column_combo = ModernComboBox()
        self.time_column_combo.currentIndexChanged.connect(self.on_time_column_changed)
        control_layout.addWidget(self.time_column_combo, 4, 1)

        control_layout.addWidget(QLabel("时间点"), 4, 2)
        self.time_value_combo = ModernComboBox()
        self.time_value_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.time_value_combo, 4, 3)

        control_layout.addWidget(QLabel("分类列"), 5, 0)
        self.category_combo = ModernComboBox()
        self.category_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.category_combo, 5, 1)

        control_layout.addWidget(QLabel("小数位"), 5, 2)
        self.decimal_spin = SpinBox()
        self.decimal_spin.setRange(0, 8)
        self.decimal_spin.setValue(4)
        self.decimal_spin.valueChanged.connect(self.on_decimal_changed)
        control_layout.addWidget(self.decimal_spin, 5, 3)

        control_layout.addWidget(QLabel("分级数"), 6, 0)
        self.class_count_spin = SpinBox()
        self.class_count_spin.setRange(2, 9)
        self.class_count_spin.setValue(5)
        self.class_count_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.class_count_spin, 6, 1)

        control_layout.addWidget(QLabel("拉伸方式"), 6, 2)
        self.stretch_combo = ModernComboBox()
        for value, label in self.STRETCH_METHODS:
            self.stretch_combo.addItem(label, userData=value)
        self.stretch_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.stretch_combo, 6, 3)

        control_layout.addWidget(QLabel("配色"), 7, 0)
        self.palette_combo = ModernComboBox()
        for value, label in self.COLOR_PALETTES:
            self.palette_combo.addItem(label, userData=value)
        self.palette_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.palette_combo, 7, 1)

        control_layout.addWidget(QLabel("投影"), 7, 2)
        self.projection_combo = ModernComboBox()
        for value, label in self.PROJECTION_PRESETS:
            self.projection_combo.addItem(label, userData=value)
        self.projection_combo.currentIndexChanged.connect(self.on_projection_changed)
        control_layout.addWidget(self.projection_combo, 7, 3)

        self.custom_projection_input = ModernLineEdit()
        self.custom_projection_input.setPlaceholderText("输入 EPSG:xxxx 或 proj 字符串")
        self.custom_projection_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.custom_projection_input, 8, 0, 1, 4)

        self.chart_hint_label = BodyLabel("请先加载包含 summary / coefficients 的结果文件。")
        self.chart_hint_label.setWordWrap(True)
        self.chart_hint_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.chart_hint_label, 9, 0, 1, 4)
        layout.addWidget(control_panel)

        chart_panel = FrostedPanel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(18, 18, 18, 18)
        chart_layout.setSpacing(10)

        chart_layout.addWidget(SubtitleLabel("图形预览"))
        self.canvas_container = QWidget()
        self.canvas_container_layout = QVBoxLayout(self.canvas_container)
        self.canvas_container_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas_container_layout.setSpacing(0)

        placeholder = QLabel("加载结果文件后将在此处显示图表")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setMinimumHeight(480)
        placeholder.setStyleSheet("color: #6b7280;")
        self.canvas_container_layout.addWidget(placeholder)

        chart_layout.addWidget(self.canvas_container)
        layout.addWidget(chart_panel, 1)

        self.update_spatial_control_state()

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择结果 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if not file_path:
            return

        try:
            dataset = VisualizationData(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", f"无法读取结果文件：{exc}")
            self.console_output.append(f"可视化加载失败: {exc}")
            return

        self.dataset = dataset
        self.selected_file_path = file_path
        self.file_label.setText(f"当前文件：{file_path}")
        self.console_output.append(f"已加载可视化结果文件: {file_path}")
        self.populate_controls()
        self.update_metrics()
        self.render_current_chart()

    def select_vector_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择边界文件",
            "",
            "空间边界 (*.shp *.geojson *.gpkg);;所有文件 (*.*)",
        )
        if not file_path:
            return

        self.vector_file_path = file_path
        self.vector_label.setText(f"边界文件：{file_path}")
        self.console_output.append(f"已选择边界文件: {file_path}")
        self.render_current_chart()

    def select_raster_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择栅格文件",
            "",
            "栅格文件 (*.tif *.tiff *.img);;所有文件 (*.*)",
        )
        if not file_path:
            return

        self.raster_file_path = file_path
        self.raster_label.setText(f"栅格文件：{file_path}")
        self.console_output.append(f"已选择栅格文件: {file_path}")
        self.render_current_chart()

    def clear_raster_file(self):
        self.raster_file_path = None
        self.raster_label.setText("栅格文件：未选择")
        self.render_current_chart()

    def populate_controls(self):
        if self.dataset is None:
            return

        self.chart_specs = self.dataset.available_charts()
        self.chart_combo.clear()
        for spec in self.chart_specs:
            self.chart_combo.addItem(spec.label, userData=spec)

        self.beta_combo.clear()
        for column, display_name in self.dataset.get_beta_display_names():
            self.beta_combo.addItem(display_name, userData=column)

        self.coordinate_columns = self.dataset.spatial_candidate_columns()
        self.time_columns = self.dataset.temporal_candidate_columns()
        self.category_columns = self.dataset.category_candidate_columns()
        self.populate_coordinate_combos()
        self.populate_time_combos()
        self.populate_category_combo()

        if self.chart_specs:
            self.chart_combo.setCurrentIndex(0)
        if self.dataset.beta_columns:
            self.beta_combo.setCurrentIndex(0)

    def populate_coordinate_combos(self):
        self.longitude_combo.clear()
        self.latitude_combo.clear()

        for column in self.coordinate_columns:
            display_name = str(column)
            self.longitude_combo.addItem(display_name, userData=column)
            self.latitude_combo.addItem(display_name, userData=column)

        defaults = list(self.dataset.coord_columns[:2]) if self.dataset is not None else []
        if len(defaults) == 2:
            lon_index = self.longitude_combo.findData(defaults[0])
            lat_index = self.latitude_combo.findData(defaults[1])
            if lon_index >= 0:
                self.longitude_combo.setCurrentIndex(lon_index)
            if lat_index >= 0:
                self.latitude_combo.setCurrentIndex(lat_index)
        elif len(self.coordinate_columns) >= 2:
            self.longitude_combo.setCurrentIndex(0)
            self.latitude_combo.setCurrentIndex(1)

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

    def populate_category_combo(self):
        self.category_combo.clear()
        for column in self.category_columns:
            self.category_combo.addItem(str(column), userData=column)
        if self.category_columns:
            self.category_combo.setCurrentIndex(0)

    def refresh_time_value_options(self):
        self.time_value_combo.clear()
        time_column = self.time_column_combo.currentData()
        if not self.dataset or not time_column:
            return
        self.time_value_combo.addItem("全部时间", userData=None)
        for label, value in self.dataset.time_value_options(time_column):
            self.time_value_combo.addItem(label, userData=value)
        self.time_value_combo.setCurrentIndex(0)

    def update_metrics(self):
        if self.dataset is None:
            return

        decimals = self.decimal_spin.value()
        self.metric_cards["model"].set_value(self.dataset.metric_text("model", decimals))
        self.metric_cards["R2"].set_value(self.dataset.metric_text("R2", decimals))
        self.metric_cards["aic"].set_value(self.dataset.metric_text("aic", decimals))
        self.metric_cards["samples"].set_value(self.dataset.metric_text("samples", decimals))

    def current_chart_spec(self):
        index = self.chart_combo.currentIndex()
        if index < 0:
            return None
        return self.chart_combo.itemData(index)

    def current_beta_column(self):
        index = self.beta_combo.currentIndex()
        if index < 0:
            return None
        return self.beta_combo.itemData(index)

    def current_projection(self):
        projection = self.projection_combo.currentData()
        if projection == "custom":
            return self.custom_projection_input.text().strip()
        return projection

    def current_render_options(self):
        return RenderOptions(
            vector_path=self.vector_file_path,
            raster_path=self.raster_file_path,
            class_count=self.class_count_spin.value(),
            stretch_method=self.stretch_combo.currentData(),
            palette=self.palette_combo.currentData(),
            projection=self.current_projection(),
            longitude_column=self.longitude_combo.currentData(),
            latitude_column=self.latitude_combo.currentData(),
            time_column=self.time_column_combo.currentData(),
            time_value=self.time_value_combo.currentData(),
            category_column=self.category_combo.currentData(),
            decimal_places=self.decimal_spin.value(),
        )

    def on_chart_changed(self):
        self.update_spatial_control_state()
        self.render_current_chart()

    def on_time_column_changed(self):
        self.refresh_time_value_options()
        self.render_current_chart()

    def on_decimal_changed(self):
        self.update_metrics()
        self.render_current_chart()

    def on_projection_changed(self):
        is_custom = self.projection_combo.currentData() == "custom"
        self.custom_projection_input.setEnabled(is_custom)
        if not is_custom:
            self.custom_projection_input.clear()
        self.render_current_chart()

    def update_spatial_control_state(self):
        spec = self.current_chart_spec()
        uses_coordinates = bool(spec and ChartFactory.chart_uses_spatial_coordinates(spec.key))
        requires_spatial = bool(spec and ChartFactory.chart_requires_spatial_options(spec.key))
        uses_time_column = bool(spec and ChartFactory.chart_uses_time_column(spec.key))
        uses_time_slice = bool(spec and ChartFactory.chart_uses_time_slice(spec.key))
        uses_category = bool(spec and ChartFactory.chart_uses_category_column(spec.key))
        for control in (self.longitude_combo, self.latitude_combo):
            control.setEnabled(uses_coordinates)
        for control in (self.time_column_combo,):
            control.setEnabled(uses_time_column)
        for control in (self.time_value_combo,):
            control.setEnabled(uses_time_slice)
        for control in (self.category_combo,):
            control.setEnabled(uses_category)
        for control in (self.class_count_spin, self.stretch_combo, self.palette_combo, self.projection_combo, self.custom_projection_input):
            control.setEnabled(requires_spatial)
        if requires_spatial:
            self.custom_projection_input.setEnabled(self.projection_combo.currentData() == "custom")
        self.update_beta_control_state(spec)

    def update_beta_control_state(self, spec):
        requires_beta = bool(spec and spec.requires_beta)
        has_beta = self.beta_combo.count() > 0
        self.beta_combo.setEnabled(requires_beta and has_beta)
        if not has_beta:
            self.beta_combo.setToolTip("当前结果文件没有可用的系数列，只有包含 beta_ 列的结果文件才能选择变量")
        elif not requires_beta:
            self.beta_combo.setToolTip("当前图表不需要选择变量")
        else:
            self.beta_combo.setToolTip("选择要展示的变量")

    def render_current_chart(self):
        if self.dataset is None:
            return

        spec = self.current_chart_spec()
        if spec is None:
            return

        beta_column = self.current_beta_column()
        self.update_beta_control_state(spec)
        if spec.requires_beta and beta_column is None:
            self.chart_hint_label.setText("当前图表需要选择变量。")
            return

        render_options = self.current_render_options()

        try:
            figure = ChartFactory.create_figure(
                self.dataset,
                spec.key,
                beta_column=beta_column,
                render_options=render_options,
            )
        except Exception as exc:
            self.chart_hint_label.setText(f"图表渲染失败：{exc}")
            self.console_output.append(f"图表渲染失败: {exc}")
            return

        self.chart_hint_label.setText(self.build_chart_hint(spec, beta_column, render_options))
        self.replace_canvas(FigureCanvas(figure))

    def build_chart_hint(self, spec, beta_column, render_options):
        parts = [f"当前图表：{spec.label}"]
        if spec.requires_beta and beta_column:
            parts.append(f"变量：{str(beta_column).removeprefix('beta_')}")
        parts.append(f"小数位：{self.decimal_spin.value()}")
        if ChartFactory.chart_uses_spatial_coordinates(spec.key):
            if render_options.longitude_column and render_options.latitude_column:
                parts.append(f"坐标：{render_options.longitude_column} / {render_options.latitude_column}")
        if ChartFactory.chart_uses_time_column(spec.key) and render_options.time_column:
            parts.append(f"时间列：{render_options.time_column}")
        if ChartFactory.chart_uses_time_slice(spec.key) and render_options.time_value:
            parts.append(f"时间点：{render_options.time_value}")
        if ChartFactory.chart_uses_category_column(spec.key) and render_options.category_column:
            parts.append(f"分类列：{render_options.category_column}")
        if ChartFactory.chart_requires_spatial_options(spec.key):
            parts.append(f"分级：{self.stretch_combo.currentText()} / {self.class_count_spin.value()} 级")
            parts.append(f"配色：{self.palette_combo.currentText()}")
            parts.append(f"投影：{self.current_projection()}")
        return "，".join(parts)

    def replace_canvas(self, canvas):
        while self.canvas_container_layout.count():
            item = self.canvas_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.canvas = canvas
        self.canvas.setMinimumHeight(500)
        self.canvas_container_layout.addWidget(self.canvas)

    def save_current_figure(self):
        if self.canvas is None:
            QMessageBox.information(self, "暂无图表", "请先加载结果文件并生成图表")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出图表", "", "PNG 图片 (*.png);;SVG 图片 (*.svg)")
        if not file_path:
            return

        try:
            self.canvas.figure.savefig(file_path, dpi=220, bbox_inches="tight")
            self.console_output.append(f"图表已导出至 {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"无法导出图表：{exc}")
            self.console_output.append(f"图表导出失败: {exc}")
