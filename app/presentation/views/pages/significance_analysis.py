from __future__ import annotations

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SpinBox, SubtitleLabel, TitleLabel

from app.application.dto.significance import SignificanceRenderOptions
from app.presentation.viewmodels.significance_viewmodel import SignificancePageViewModel
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.fluent_surface import FrostedPanel
from app.presentation.views.widgets.input import ModernLineEdit


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
    THRESHOLD_PRESETS = [
        ("1.645", "90%"),
        ("1.960", "95%"),
        ("2.576", "99%"),
        ("custom", "自定义"),
    ]
    COORDINATE_TYPE_OPTIONS = [
        ("geographic", "经纬度 (经度 / 纬度)"),
        ("projected", "平面坐标 (X / Y)"),
    ]
    SPATIAL_DISPLAY_OPTIONS = [
        ("time_slice", "按时间切片"),
        ("aggregate_time", "汇总全部时间"),
    ]
    TEMPORAL_DISPLAY_OPTIONS = [
        ("aggregate_space", "全部地点汇总"),
        ("single_location", "单个地点"),
    ]

    def __init__(self, console_output, presenter):
        super().__init__()
        self.console_output = console_output
        self.presenter = presenter
        self.viewmodel: SignificancePageViewModel | None = None
        self.canvas = None
        self.metric_cards = {}
        self.location_options = []
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

        guide_panel = FrostedPanel()
        guide_layout = QVBoxLayout(guide_panel)
        guide_layout.setContentsMargins(18, 16, 18, 16)
        guide_layout.setSpacing(6)
        guide_layout.addWidget(SubtitleLabel("说明"))
        guide_text = BodyLabel(
            "1. 先选择 t统计量 字段判断显著性，再结合同名 beta 字段解释影响方向和强弱。\n"
            "2. 默认阈值 |t| >= 1.96，通常对应 95% 显著性；可以切换到 90% / 99% 或自定义。\n"
            "3. 显著系数图只显示通过阈值的样本，更适合辅助解释哪些区域、哪些时间点值得重点分析。"
        )
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #5b6b84;")
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_panel)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(12)
        metric_grid.setVerticalSpacing(12)
        metric_names = [("total", "样本数"), ("significant", "显著样本"), ("ratio", "显著占比"), ("positive", "正向显著"), ("negative", "负向显著")]
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
        self.t_combo.currentIndexChanged.connect(self.on_t_column_changed)
        control_layout.addWidget(self.t_combo, 0, 3)

        control_layout.addWidget(QLabel("阈值预设"), 1, 0)
        self.threshold_preset_combo = ModernComboBox()
        for value, label in self.THRESHOLD_PRESETS:
            self.threshold_preset_combo.addItem(label, userData=value)
        self.threshold_preset_combo.currentIndexChanged.connect(self.on_threshold_preset_changed)
        control_layout.addWidget(self.threshold_preset_combo, 1, 1)

        control_layout.addWidget(QLabel("显著性阈值"), 1, 2)
        self.threshold_input = ModernLineEdit()
        self.threshold_input.setText("1.96")
        self.threshold_input.setPlaceholderText("例如 1.96")
        self.threshold_input.textChanged.connect(self.on_threshold_changed)
        control_layout.addWidget(self.threshold_input, 1, 3)

        control_layout.addWidget(QLabel("系数字段"), 2, 0)
        self.beta_combo = ModernComboBox()
        self.beta_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.beta_combo, 2, 1)

        control_layout.addWidget(QLabel("标题"), 2, 2)
        self.title_input = ModernLineEdit()
        self.title_input.setPlaceholderText("留空则使用默认标题")
        self.title_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.title_input, 2, 3)

        control_layout.addWidget(QLabel("坐标类型"), 3, 0)
        self.coordinate_type_combo = ModernComboBox()
        for value, label in self.COORDINATE_TYPE_OPTIONS:
            self.coordinate_type_combo.addItem(label, userData=value)
        self.coordinate_type_combo.currentIndexChanged.connect(self.on_coordinate_type_changed)
        control_layout.addWidget(self.coordinate_type_combo, 3, 1)

        self.longitude_label = QLabel("经度列")
        control_layout.addWidget(self.longitude_label, 3, 2)
        self.longitude_combo = ModernComboBox()
        self.longitude_combo.currentIndexChanged.connect(self.on_coordinate_selection_changed)
        control_layout.addWidget(self.longitude_combo, 3, 3)

        self.latitude_label = QLabel("纬度列")
        control_layout.addWidget(self.latitude_label, 4, 0)
        self.latitude_combo = ModernComboBox()
        self.latitude_combo.currentIndexChanged.connect(self.on_coordinate_selection_changed)
        control_layout.addWidget(self.latitude_combo, 4, 1)

        control_layout.addWidget(QLabel("时间列"), 4, 2)
        self.time_column_combo = ModernComboBox()
        self.time_column_combo.currentIndexChanged.connect(self.on_time_column_changed)
        control_layout.addWidget(self.time_column_combo, 4, 3)

        control_layout.addWidget(QLabel("时间点"), 5, 0)
        self.time_value_combo = ModernComboBox()
        self.time_value_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.time_value_combo, 5, 1)

        control_layout.addWidget(QLabel("小数位"), 5, 2)
        self.decimal_spin = SpinBox()
        self.decimal_spin.setRange(0, 6)
        self.decimal_spin.setValue(4)
        self.decimal_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.decimal_spin, 5, 3)

        control_layout.addWidget(QLabel("空间展示"), 6, 0)
        self.spatial_mode_combo = ModernComboBox()
        for value, label in self.SPATIAL_DISPLAY_OPTIONS:
            self.spatial_mode_combo.addItem(label, userData=value)
        self.spatial_mode_combo.currentIndexChanged.connect(self.on_display_mode_changed)
        control_layout.addWidget(self.spatial_mode_combo, 6, 1)

        control_layout.addWidget(QLabel("时间展示"), 6, 2)
        self.temporal_mode_combo = ModernComboBox()
        for value, label in self.TEMPORAL_DISPLAY_OPTIONS:
            self.temporal_mode_combo.addItem(label, userData=value)
        self.temporal_mode_combo.currentIndexChanged.connect(self.on_display_mode_changed)
        control_layout.addWidget(self.temporal_mode_combo, 6, 3)

        control_layout.addWidget(QLabel("地点"), 7, 0)
        self.location_combo = ModernComboBox()
        self.location_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.location_combo, 7, 1, 1, 3)

        self.chart_hint_label = BodyLabel("请先加载包含 t_ 列的结果文件。")
        self.chart_hint_label.setWordWrap(True)
        self.chart_hint_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.chart_hint_label, 8, 0, 1, 4)
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
            self.viewmodel = self.presenter.load_file(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", f"无法读取结果文件：{exc}")
            self.console_output.append(f"显著性分析加载失败: {exc}")
            return
        self.file_label.setText(f"当前文件：{self.viewmodel.file_path}")
        self.console_output.append(f"已加载显著性分析结果文件: {self.viewmodel.file_path}")
        self.populate_controls()
        self.render_current_chart()

    def populate_controls(self):
        if self.viewmodel is None:
            return
        self.chart_combo.blockSignals(True)
        self.chart_combo.clear()
        for spec in self.viewmodel.chart_specs:
            self.chart_combo.addItem(spec.label, userData=spec)
        self.chart_combo.blockSignals(False)
        self.t_combo.blockSignals(True)
        self.t_combo.clear()
        for column in self.viewmodel.dataset.t_columns:
            self.t_combo.addItem(self.viewmodel.dataset.metric_display_name(column), userData=column)
        self.t_combo.blockSignals(False)
        self.beta_combo.blockSignals(True)
        self.beta_combo.clear()
        for column in self.viewmodel.dataset.beta_columns:
            self.beta_combo.addItem(self.viewmodel.dataset.metric_display_name(column), userData=column)
        self.beta_combo.blockSignals(False)
        self.populate_coordinate_combos()
        self.populate_location_combo()
        self.populate_time_combos()
        if self.viewmodel.chart_specs:
            self.chart_combo.setCurrentIndex(0)
        if self.viewmodel.dataset.t_columns:
            self.t_combo.setCurrentIndex(0)
        self.sync_beta_selection()
        preset_index = self.threshold_preset_combo.findData("1.960")
        if preset_index >= 0:
            self.threshold_preset_combo.setCurrentIndex(preset_index)
        self.update_control_state()

    def populate_coordinate_combos(self):
        self.longitude_combo.blockSignals(True)
        self.latitude_combo.blockSignals(True)
        self.coordinate_type_combo.blockSignals(True)
        self.longitude_combo.clear()
        self.latitude_combo.clear()
        if self.viewmodel is None:
            self.coordinate_type_combo.blockSignals(False)
            self.longitude_combo.blockSignals(False)
            self.latitude_combo.blockSignals(False)
            return
        for column in self.viewmodel.coordinate_columns:
            self.longitude_combo.addItem(str(column), userData=column)
            self.latitude_combo.addItem(str(column), userData=column)
        defaults = list(self.viewmodel.dataset.coord_columns[:2])
        if len(defaults) == 2:
            lon_index = self.longitude_combo.findData(defaults[0])
            lat_index = self.latitude_combo.findData(defaults[1])
            if lon_index >= 0:
                self.longitude_combo.setCurrentIndex(lon_index)
            if lat_index >= 0:
                self.latitude_combo.setCurrentIndex(lat_index)
        self.apply_coordinate_type_default(defaults)
        self.coordinate_type_combo.blockSignals(False)
        self.longitude_combo.blockSignals(False)
        self.latitude_combo.blockSignals(False)

    def apply_coordinate_type_default(self, defaults):
        inferred = self.infer_coordinate_type(defaults)
        index = self.coordinate_type_combo.findData(inferred)
        if index >= 0:
            self.coordinate_type_combo.setCurrentIndex(index)
        self.update_coordinate_labels()

    @staticmethod
    def infer_coordinate_type(columns):
        joined = " ".join(str(column).lower() for column in columns if column)
        geographic_keywords = ["经度", "纬度", "lon", "lng", "lat", "long"]
        if any(keyword in joined for keyword in geographic_keywords):
            return "geographic"
        return "projected"

    def on_coordinate_type_changed(self):
        self.update_coordinate_labels()
        self.populate_location_combo()
        self.render_current_chart()

    def update_coordinate_labels(self):
        coordinate_type = self.coordinate_type_combo.currentData()
        if coordinate_type == "projected":
            self.longitude_label.setText("X 坐标列")
            self.latitude_label.setText("Y 坐标列")
        else:
            self.longitude_label.setText("经度列")
            self.latitude_label.setText("纬度列")

    def populate_location_combo(self):
        self.location_combo.blockSignals(True)
        self.location_combo.clear()
        self.location_combo.addItem("请选择地点", userData=None)
        if self.viewmodel is None:
            self.location_combo.blockSignals(False)
            return
        x_col = self.longitude_combo.currentData()
        y_col = self.latitude_combo.currentData()
        self.location_options = self.viewmodel.dataset.location_value_options(x_col, y_col)
        for label, value in self.location_options:
            self.location_combo.addItem(label, userData=value)
        self.location_combo.setCurrentIndex(0)
        self.location_combo.blockSignals(False)

    def populate_time_combos(self):
        self.time_column_combo.blockSignals(True)
        self.time_column_combo.clear()
        if self.viewmodel is None:
            self.time_column_combo.blockSignals(False)
            return
        for column in self.viewmodel.time_columns:
            self.time_column_combo.addItem(str(column), userData=column)
        if self.viewmodel.dataset.time_column:
            time_index = self.time_column_combo.findData(self.viewmodel.dataset.time_column)
            if time_index >= 0:
                self.time_column_combo.setCurrentIndex(time_index)
        elif self.viewmodel.time_columns:
            self.time_column_combo.setCurrentIndex(0)
        self.time_column_combo.blockSignals(False)
        self.refresh_time_value_options()

    def refresh_time_value_options(self):
        self.time_value_combo.blockSignals(True)
        self.time_value_combo.clear()
        if self.viewmodel is None:
            self.time_value_combo.blockSignals(False)
            return
        time_column = self.time_column_combo.currentData()
        if not time_column:
            self.time_value_combo.blockSignals(False)
            return
        self.time_value_combo.addItem("全部时间", userData=None)
        for label, value in self.viewmodel.dataset.time_value_options(time_column):
            self.time_value_combo.addItem(label, userData=value)
        self.time_value_combo.setCurrentIndex(0)
        self.time_value_combo.blockSignals(False)

    def on_time_column_changed(self):
        self.refresh_time_value_options()
        self.render_current_chart()

    def on_coordinate_selection_changed(self):
        self.populate_location_combo()
        self.render_current_chart()

    def on_t_column_changed(self):
        self.sync_beta_selection()
        self.render_current_chart()

    def on_threshold_changed(self):
        self.sync_threshold_preset()
        self.render_current_chart()

    def on_threshold_preset_changed(self):
        selected = self.threshold_preset_combo.currentData()
        if selected and selected != "custom":
            self.threshold_input.blockSignals(True)
            self.threshold_input.setText(selected)
            self.threshold_input.blockSignals(False)
        self.render_current_chart()

    def on_chart_changed(self):
        self.update_control_state()
        self.render_current_chart()

    def on_display_mode_changed(self):
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

    def current_beta_column(self):
        index = self.beta_combo.currentIndex()
        if index < 0:
            return None
        return self.beta_combo.itemData(index)

    def current_render_options(self):
        spec = self.current_chart_spec()
        key = spec.key if spec else ""
        spatial_mode = self.spatial_mode_combo.currentData() if key in {"spatial", "coefficient_spatial"} else "time_slice"
        temporal_mode = self.temporal_mode_combo.currentData() if key in {"temporal", "coefficient_temporal"} else "aggregate_space"
        location_value = self.location_combo.currentData() if temporal_mode == "single_location" else None
        return SignificanceRenderOptions(
            threshold=self.parse_float_input(self.threshold_input, 1.96),
            beta_column=self.current_beta_column(),
            longitude_column=self.longitude_combo.currentData(),
            latitude_column=self.latitude_combo.currentData(),
            time_column=self.time_column_combo.currentData(),
            time_value=self.time_value_combo.currentData(),
            spatial_mode=spatial_mode or "time_slice",
            temporal_mode=temporal_mode or "aggregate_space",
            location_value=location_value,
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
        uses_spatial = key in {"spatial", "coefficient_spatial"}
        uses_temporal = key in {"temporal", "coefficient_temporal"}
        uses_beta = key in {"coefficient_spatial", "coefficient_temporal"}
        uses_time_slice = key in {"summary", "spatial", "coefficient_spatial"}
        uses_temporal_dataset = bool(self.viewmodel is not None and self.viewmodel.dataset.has_temporal())
        self.coordinate_type_combo.setEnabled(uses_spatial)
        self.longitude_combo.setEnabled(uses_spatial)
        self.latitude_combo.setEnabled(uses_spatial)
        self.time_column_combo.setEnabled(uses_temporal or uses_time_slice)
        self.time_value_combo.setEnabled(uses_time_slice and self.time_column_combo.count() > 0 and self.spatial_mode_combo.currentData() != "aggregate_time")
        self.spatial_mode_combo.setEnabled(uses_spatial and uses_temporal_dataset)
        self.temporal_mode_combo.setEnabled(uses_temporal and uses_temporal_dataset)
        self.location_combo.setEnabled(uses_temporal and self.temporal_mode_combo.currentData() == "single_location")
        self.beta_combo.setEnabled(uses_beta)

    def render_current_chart(self):
        if self.viewmodel is None:
            return
        spec = self.current_chart_spec()
        t_column = self.current_t_column()
        if spec is None or t_column is None:
            return
        try:
            render_result = self.presenter.render(
                dataset=self.viewmodel.dataset,
                t_column=t_column,
                chart_key=spec.key,
                options=self.current_render_options(),
            )
        except Exception as exc:
            self.chart_hint_label.setText(f"图表渲染失败：{exc}")
            self.console_output.append(f"显著性图表渲染失败: {exc}")
            return
        self.metric_cards["total"].set_value(render_result.stats.total)
        self.metric_cards["significant"].set_value(render_result.stats.significant)
        self.metric_cards["ratio"].set_value(f"{render_result.stats.ratio:.1%}")
        self.metric_cards["positive"].set_value(render_result.stats.positive)
        self.metric_cards["negative"].set_value(render_result.stats.negative)
        self.chart_hint_label.setText(render_result.hint)
        self.replace_canvas(FigureCanvas(render_result.figure))

    def sync_beta_selection(self):
        if self.viewmodel is None or self.beta_combo.count() == 0:
            return
        t_column = self.current_t_column()
        if not t_column:
            return
        target_base = self.viewmodel.dataset.metric_base_name(t_column)
        for index in range(self.beta_combo.count()):
            beta_column = self.beta_combo.itemData(index)
            if self.viewmodel.dataset.metric_base_name(beta_column) == target_base:
                self.beta_combo.setCurrentIndex(index)
                return

    def sync_threshold_preset(self):
        current_value = self.threshold_input.text().strip()
        preset_index = self.threshold_preset_combo.findData(current_value)
        if preset_index >= 0:
            self.threshold_preset_combo.blockSignals(True)
            self.threshold_preset_combo.setCurrentIndex(preset_index)
            self.threshold_preset_combo.blockSignals(False)
            return
        custom_index = self.threshold_preset_combo.findData("custom")
        if custom_index >= 0:
            self.threshold_preset_combo.blockSignals(True)
            self.threshold_preset_combo.setCurrentIndex(custom_index)
            self.threshold_preset_combo.blockSignals(False)

    def replace_canvas(self, canvas):
        while self.canvas_container_layout.count():
            item = self.canvas_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.canvas = canvas
        self.canvas.setMinimumHeight(500)
        self.canvas_container_layout.addWidget(self.canvas)

