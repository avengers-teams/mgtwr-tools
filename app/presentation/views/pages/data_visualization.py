from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib import colormaps
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAction, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SpinBox, SubtitleLabel, TitleLabel, TransparentPushButton
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu

from app.presentation.renderers.model_visualization import ChartFactory, RenderOptions, VisualizationData
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.fluent_surface import FrostedPanel
from app.presentation.views.widgets.input import ModernLineEdit


class PaletteMenuItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = option.rect.adjusted(6, 3, -6, -3)
        if option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 108, 189, 18))
            painter.drawRoundedRect(rect, 8, 8)
        elif option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 108, 189, 28))
            painter.drawRoundedRect(rect, 8, 8)

        action = index.data(Qt.UserRole)
        icon = action.icon() if isinstance(action, QAction) else QIcon()
        if not icon.isNull():
            preview_rect = rect.adjusted(12, 7, -12, -7)
            painter.drawPixmap(preview_rect, icon.pixmap(preview_rect.size()))

        if option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 108, 189))
            painter.drawRoundedRect(rect.left() + 2, rect.top() + 8, 3, rect.height() - 16, 1.5, 1.5)

        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(42)
        return size


class PalettePreviewComboBox(ModernComboBox):
    def _createComboMenu(self):
        menu = ComboBoxMenu(self)
        menu.view.setItemDelegate(PaletteMenuItemDelegate(menu.view))
        menu.setItemHeight(42)
        return menu

    def paintEvent(self, event):
        super().paintEvent(event)
        icon = self.itemIcon(self.currentIndex()) if self.currentIndex() >= 0 else QIcon()
        if icon.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        preview_rect = self.rect().adjusted(12, 8, -34, -8)
        pixmap = icon.pixmap(preview_rect.size())
        painter.drawPixmap(preview_rect, pixmap)
        painter.end()


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
    FONT_OPTIONS = [
        ("微软雅黑", "Microsoft YaHei"),
        ("宋体", "SimSun"),
        ("新罗马", "Times New Roman"),
    ]

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
        self.palette_names = sorted(colormaps)
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

        control_layout.addWidget(QLabel("统计量"), 0, 2)
        self.beta_combo = ModernComboBox()
        self.beta_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.beta_combo, 0, 3)

        control_layout.addWidget(QLabel("标题"), 1, 0)
        self.title_input = ModernLineEdit()
        self.title_input.setPlaceholderText("留空则使用默认标题")
        self.title_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.title_input, 1, 1)

        control_layout.addWidget(QLabel("图例名称"), 1, 2)
        self.legend_input = ModernLineEdit()
        self.legend_input.setPlaceholderText("留空则使用默认图例名称")
        self.legend_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.legend_input, 1, 3)

        control_layout.addWidget(QLabel("字体"), 2, 0)
        self.font_combo = ModernComboBox()
        self.font_combo.currentIndexChanged.connect(self.on_font_changed)
        control_layout.addWidget(self.font_combo, 2, 1)

        control_layout.addWidget(QLabel("配色"), 2, 2)
        self.palette_combo = PalettePreviewComboBox()
        self.palette_combo.setIconSize(QSize(176, 24))
        self.palette_combo.setMinimumWidth(220)
        self.palette_combo.setMinimumHeight(44)
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)
        control_layout.addWidget(self.palette_combo, 2, 3)

        vector_button = ModernButton("选择 shp/geojson")
        vector_button.clicked.connect(self.select_vector_file)
        raster_button = ModernButton("选择栅格")
        raster_button.clicked.connect(self.select_raster_file)
        clear_raster_button = TransparentPushButton("清空栅格")
        clear_raster_button.clicked.connect(self.clear_raster_file)
        control_layout.addWidget(vector_button, 3, 0)
        control_layout.addWidget(raster_button, 3, 2)
        control_layout.addWidget(clear_raster_button, 3, 3, alignment=Qt.AlignLeft)

        self.vector_label = BodyLabel("边界文件：未选择")
        self.vector_label.setWordWrap(True)
        control_layout.addWidget(self.vector_label, 4, 0, 1, 2)

        self.raster_label = BodyLabel("栅格文件：未选择")
        self.raster_label.setWordWrap(True)
        control_layout.addWidget(self.raster_label, 4, 2, 1, 2)

        control_layout.addWidget(QLabel("经度列"), 5, 0)
        self.longitude_combo = ModernComboBox()
        self.longitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.longitude_combo, 5, 1)

        control_layout.addWidget(QLabel("纬度列"), 6, 2)
        self.latitude_combo = ModernComboBox()
        self.latitude_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.latitude_combo, 6, 3)

        control_layout.addWidget(QLabel("时间列"), 6, 0)
        self.time_column_combo = ModernComboBox()
        self.time_column_combo.currentIndexChanged.connect(self.on_time_column_changed)
        control_layout.addWidget(self.time_column_combo, 6, 1)

        control_layout.addWidget(QLabel("时间点"), 7, 2)
        self.time_value_combo = ModernComboBox()
        self.time_value_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.time_value_combo, 7, 3)

        control_layout.addWidget(QLabel("分类列"), 7, 0)
        self.category_combo = ModernComboBox()
        self.category_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.category_combo, 7, 1)

        control_layout.addWidget(QLabel("小数位"), 8, 2)
        self.decimal_spin = SpinBox()
        self.decimal_spin.setRange(0, 8)
        self.decimal_spin.setValue(4)
        self.decimal_spin.valueChanged.connect(self.on_decimal_changed)
        control_layout.addWidget(self.decimal_spin, 8, 3)

        control_layout.addWidget(QLabel("时间占位宽度"), 8, 0)
        self.time_slot_width_spin = SpinBox()
        self.time_slot_width_spin.setRange(1, 20)
        self.time_slot_width_spin.setValue(2)
        self.time_slot_width_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.time_slot_width_spin, 8, 1)

        control_layout.addWidget(QLabel("分类占位宽度"), 9, 2)
        self.category_slot_width_spin = SpinBox()
        self.category_slot_width_spin.setRange(1, 20)
        self.category_slot_width_spin.setValue(2)
        self.category_slot_width_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.category_slot_width_spin, 9, 3)

        control_layout.addWidget(QLabel("图宽"), 9, 0)
        self.figure_width_input = ModernLineEdit()
        self.figure_width_input.setText("8")
        self.figure_width_input.setPlaceholderText("例如 15")
        self.figure_width_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.figure_width_input, 9, 1)

        control_layout.addWidget(QLabel("图高"), 10, 2)
        self.figure_height_input = ModernLineEdit()
        self.figure_height_input.setText("5")
        self.figure_height_input.setPlaceholderText("例如 10")
        self.figure_height_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.figure_height_input, 10, 3)

        control_layout.addWidget(QLabel("X轴比例"), 10, 0)
        self.x_box_aspect_input = ModernLineEdit()
        self.x_box_aspect_input.setText("1")
        self.x_box_aspect_input.setPlaceholderText("例如 1")
        self.x_box_aspect_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.x_box_aspect_input, 10, 1)

        control_layout.addWidget(QLabel("Y轴比例"), 11, 2)
        self.y_box_aspect_input = ModernLineEdit()
        self.y_box_aspect_input.setText("3")
        self.y_box_aspect_input.setPlaceholderText("例如 3.5")
        self.y_box_aspect_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.y_box_aspect_input, 11, 3)

        control_layout.addWidget(QLabel("Z轴比例"), 11, 0)
        self.z_box_aspect_input = ModernLineEdit()
        self.z_box_aspect_input.setText("1")
        self.z_box_aspect_input.setPlaceholderText("例如 1")
        self.z_box_aspect_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.z_box_aspect_input, 11, 1)

        control_layout.addWidget(QLabel("分级数"), 12, 2)
        self.class_count_spin = SpinBox()
        self.class_count_spin.setRange(2, 9)
        self.class_count_spin.setValue(5)
        self.class_count_spin.valueChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.class_count_spin, 12, 3)

        control_layout.addWidget(QLabel("拉伸方式"), 12, 0)
        self.stretch_combo = ModernComboBox()
        for value, label in self.STRETCH_METHODS:
            self.stretch_combo.addItem(label, userData=value)
        self.stretch_combo.currentIndexChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.stretch_combo, 12, 1)

        control_layout.addWidget(QLabel("投影"), 13, 0)
        self.projection_combo = ModernComboBox()
        for value, label in self.PROJECTION_PRESETS:
            self.projection_combo.addItem(label, userData=value)
        self.projection_combo.currentIndexChanged.connect(self.on_projection_changed)
        control_layout.addWidget(self.projection_combo, 13, 1)

        self.custom_projection_input = ModernLineEdit()
        self.custom_projection_input.setPlaceholderText("输入 EPSG:xxxx 或 proj 字符串")
        self.custom_projection_input.textChanged.connect(self.render_current_chart)
        control_layout.addWidget(self.custom_projection_input, 13, 2, 1, 2)

        self.chart_hint_label = BodyLabel("请先加载包含 summary / coefficients 的结果文件。")
        self.chart_hint_label.setWordWrap(True)
        self.chart_hint_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.chart_hint_label, 14, 0, 1, 4)
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

        self.populate_font_combo()
        self.populate_palette_combo()
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
        for column, display_name in self.dataset.get_metric_display_names():
            self.beta_combo.addItem(display_name, userData=column)

        self.coordinate_columns = self.dataset.spatial_candidate_columns()
        self.time_columns = self.dataset.temporal_candidate_columns()
        self.category_columns = self.dataset.category_candidate_columns()
        self.populate_coordinate_combos()
        self.populate_time_combos()
        self.populate_category_combo()

        if self.chart_specs:
            self.chart_combo.setCurrentIndex(0)
        if self.dataset.metric_columns:
            self.beta_combo.setCurrentIndex(0)

    def populate_font_combo(self):
        self.font_combo.clear()
        for label, family in self.FONT_OPTIONS:
            self.font_combo.addItem(label, userData=family)

        self.font_combo.setToolTip("仅支持 微软雅黑 / 宋体 / 新罗马")
        default_index = self.font_combo.findData("Microsoft YaHei")
        self.font_combo.setCurrentIndex(default_index if default_index >= 0 else 0)
        self.apply_font_combo_preview(self.font_combo.currentData())

    def populate_palette_combo(self):
        self.palette_combo.clear()
        for palette_name in self.palette_names:
            self.palette_combo.addItem("", self.create_palette_icon(palette_name), palette_name)

        default_index = self.palette_combo.findData("viridis")
        if default_index >= 0:
            self.palette_combo.setCurrentIndex(default_index)
        self.palette_combo.setToolTip(str(self.palette_combo.currentData() or ""))

    def create_palette_icon(self, palette_name, width=176, height=24):
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        cmap = colormaps.get_cmap(palette_name)
        for x in range(width):
            rgba = cmap(x / max(1, width - 1))
            color = QColor.fromRgbF(rgba[0], rgba[1], rgba[2], rgba[3])
            painter.setPen(color)
            painter.drawLine(x, 0, x, height)
        painter.end()
        return QIcon(pixmap)

    def update_palette_preview(self):
        return

    def apply_font_combo_preview(self, family):
        if family:
            self.font_combo.setFont(QFont(family, self.font_combo.font().pointSize()))

    def on_font_changed(self):
        family = self.font_combo.currentData()
        self.apply_font_combo_preview(family)
        self.render_current_chart()

    def on_palette_changed(self):
        palette_name = self.palette_combo.currentData()
        self.palette_combo.setToolTip(str(palette_name) if palette_name else "")
        self.update_palette_preview()
        self.render_current_chart()

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
            font_family=self.font_combo.currentData(),
            figure_title=self.title_input.text().strip() or None,
            legend_label=self.legend_input.text().strip() or None,
            time_slot_width=self.time_slot_width_spin.value(),
            category_slot_width=self.category_slot_width_spin.value(),
            figure_width=self.parse_float_input(self.figure_width_input, 8.0),
            figure_height=self.parse_float_input(self.figure_height_input, 5.0),
            x_box_aspect=self.parse_float_input(self.x_box_aspect_input, 1.0),
            y_box_aspect=self.parse_float_input(self.y_box_aspect_input, 3.0),
            z_box_aspect=self.parse_float_input(self.z_box_aspect_input, 1.0),
        )

    def parse_float_input(self, widget, default):
        text = widget.text().strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

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
        uses_time_slot_width = bool(spec and spec.key == "coefficient_3d")
        uses_palette = bool(spec and ChartFactory.chart_uses_colormap(spec.key))
        for control in (self.longitude_combo, self.latitude_combo):
            control.setEnabled(uses_coordinates)
        for control in (self.time_column_combo,):
            control.setEnabled(uses_time_column)
        for control in (self.time_value_combo,):
            control.setEnabled(uses_time_slice)
        for control in (self.category_combo,):
            control.setEnabled(uses_category)
        self.time_slot_width_spin.setEnabled(uses_time_slot_width)
        self.category_slot_width_spin.setEnabled(uses_time_slot_width)
        self.figure_width_input.setEnabled(uses_time_slot_width)
        self.figure_height_input.setEnabled(uses_time_slot_width)
        self.x_box_aspect_input.setEnabled(uses_time_slot_width)
        self.y_box_aspect_input.setEnabled(uses_time_slot_width)
        self.z_box_aspect_input.setEnabled(uses_time_slot_width)
        self.palette_combo.setEnabled(uses_palette)
        for control in (self.class_count_spin, self.stretch_combo, self.projection_combo, self.custom_projection_input):
            control.setEnabled(requires_spatial)
        if requires_spatial:
            self.custom_projection_input.setEnabled(self.projection_combo.currentData() == "custom")
        self.update_beta_control_state(spec)

    def update_beta_control_state(self, spec):
        requires_beta = bool(spec and spec.requires_beta)
        has_beta = self.beta_combo.count() > 0
        self.beta_combo.setEnabled(requires_beta and has_beta)
        if not has_beta:
            self.beta_combo.setToolTip("当前结果文件没有可用的统计量字段，至少需要包含 beta_ / se_ / t_ 中的一类字段")
        elif not requires_beta:
            self.beta_combo.setToolTip("当前图表不需要选择统计量字段")
        else:
            self.beta_combo.setToolTip("选择要展示的统计量字段")

    def render_current_chart(self):
        if self.dataset is None:
            return

        spec = self.current_chart_spec()
        if spec is None:
            return

        beta_column = self.current_beta_column()
        self.update_beta_control_state(spec)
        if spec.requires_beta and beta_column is None:
            self.chart_hint_label.setText("当前图表需要选择统计量字段。")
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
            parts.append(f"统计量：{self.dataset.metric_display_name(beta_column)}")
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
        if render_options.font_family:
            parts.append(f"字体：{render_options.font_family}")
        if spec.key == "coefficient_3d":
            parts.append(f"时间占位宽度：{self.time_slot_width_spin.value()}")
            parts.append(f"分类占位宽度：{self.category_slot_width_spin.value()}")
            parts.append(
                f"图尺寸：{self.figure_width_input.text().strip() or '8'} / {self.figure_height_input.text().strip() or '5'}"
            )
            parts.append(
                f"轴比例：{self.x_box_aspect_input.text().strip() or '1'} / {self.y_box_aspect_input.text().strip() or '3'} / {self.z_box_aspect_input.text().strip() or '1'}"
            )
        if ChartFactory.chart_requires_spatial_options(spec.key):
            parts.append(f"分级：{self.stretch_combo.currentText()} / {self.class_count_spin.value()} 级")
            parts.append(f"配色：{self.palette_combo.currentData()}")
            parts.append(f"投影：{self.current_projection()}")
        elif self.palette_combo.currentData():
            parts.append(f"配色：{self.palette_combo.currentData()}")
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

