from dataclasses import dataclass

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
from app.presentation.views.widgets.fluent_surface import FrostedPanel, SectionHeader
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


@dataclass(frozen=True)
class ChartControlPolicy:
    visible_fields: tuple[str, ...]

    def includes(self, field_key):
        return field_key in self.visible_fields


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
        self.location_field_columns = []
        self.location_options = []
        self.palette_names = sorted(colormaps)
        self.control_sections = {}
        self.control_section_bodies = {}
        self.control_rows = {}
        self.control_field_sections = {}
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
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setSpacing(12)

        self.chart_combo = ModernComboBox()
        self.chart_combo.currentIndexChanged.connect(self.on_chart_changed)
        self.beta_combo = ModernComboBox()
        self.beta_combo.currentIndexChanged.connect(self.render_current_chart)
        self.title_input = ModernLineEdit()
        self.title_input.setPlaceholderText("留空则使用默认标题")
        self.title_input.textChanged.connect(self.render_current_chart)
        self.legend_input = ModernLineEdit()
        self.legend_input.setPlaceholderText("留空则使用默认图例名称")
        self.legend_input.textChanged.connect(self.render_current_chart)
        self.font_combo = ModernComboBox()
        self.font_combo.currentIndexChanged.connect(self.on_font_changed)
        self.palette_combo = PalettePreviewComboBox()
        self.palette_combo.setIconSize(QSize(176, 24))
        self.palette_combo.setMinimumWidth(220)
        self.palette_combo.setMinimumHeight(44)
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)

        vector_button = ModernButton("选择 shp/geojson")
        vector_button.clicked.connect(self.select_vector_file)
        raster_button = ModernButton("选择栅格")
        raster_button.clicked.connect(self.select_raster_file)
        clear_raster_button = TransparentPushButton("清空栅格")
        clear_raster_button.clicked.connect(self.clear_raster_file)
        self.vector_action_row = self.create_action_row(vector_button, raster_button, clear_raster_button)

        self.vector_label = BodyLabel("边界文件：未选择")
        self.vector_label.setWordWrap(True)

        self.raster_label = BodyLabel("栅格文件：未选择")
        self.raster_label.setWordWrap(True)

        self.coordinate_type_combo = ModernComboBox()
        for value, label in self.COORDINATE_TYPE_OPTIONS:
            self.coordinate_type_combo.addItem(label, userData=value)
        self.coordinate_type_combo.currentIndexChanged.connect(self.on_coordinate_type_changed)

        self.longitude_label = QLabel("经度列")
        self.longitude_combo = ModernComboBox()
        self.longitude_combo.currentIndexChanged.connect(self.on_coordinate_selection_changed)

        self.latitude_label = QLabel("纬度列")
        self.latitude_combo = ModernComboBox()
        self.latitude_combo.currentIndexChanged.connect(self.on_coordinate_selection_changed)

        self.time_column_combo = ModernComboBox()
        self.time_column_combo.currentIndexChanged.connect(self.on_time_column_changed)

        self.time_value_combo = ModernComboBox()
        self.time_value_combo.currentIndexChanged.connect(self.render_current_chart)

        self.category_combo = ModernComboBox()
        self.category_combo.currentIndexChanged.connect(self.render_current_chart)

        self.decimal_spin = SpinBox()
        self.decimal_spin.setRange(0, 8)
        self.decimal_spin.setValue(4)
        self.decimal_spin.valueChanged.connect(self.on_decimal_changed)

        self.time_slot_width_spin = SpinBox()
        self.time_slot_width_spin.setRange(1, 20)
        self.time_slot_width_spin.setValue(2)
        self.time_slot_width_spin.valueChanged.connect(self.render_current_chart)

        self.category_slot_width_spin = SpinBox()
        self.category_slot_width_spin.setRange(1, 20)
        self.category_slot_width_spin.setValue(2)
        self.category_slot_width_spin.valueChanged.connect(self.render_current_chart)

        self.figure_width_input = ModernLineEdit()
        self.figure_width_input.setText("8")
        self.figure_width_input.setPlaceholderText("例如 15")
        self.figure_width_input.textChanged.connect(self.render_current_chart)

        self.figure_height_input = ModernLineEdit()
        self.figure_height_input.setText("5")
        self.figure_height_input.setPlaceholderText("例如 10")
        self.figure_height_input.textChanged.connect(self.render_current_chart)

        self.x_box_aspect_input = ModernLineEdit()
        self.x_box_aspect_input.setText("1")
        self.x_box_aspect_input.setPlaceholderText("例如 1")
        self.x_box_aspect_input.textChanged.connect(self.render_current_chart)

        self.y_box_aspect_input = ModernLineEdit()
        self.y_box_aspect_input.setText("3")
        self.y_box_aspect_input.setPlaceholderText("例如 3.5")
        self.y_box_aspect_input.textChanged.connect(self.render_current_chart)

        self.z_box_aspect_input = ModernLineEdit()
        self.z_box_aspect_input.setText("1")
        self.z_box_aspect_input.setPlaceholderText("例如 1")
        self.z_box_aspect_input.textChanged.connect(self.render_current_chart)

        self.class_count_spin = SpinBox()
        self.class_count_spin.setRange(2, 9)
        self.class_count_spin.setValue(5)
        self.class_count_spin.valueChanged.connect(self.render_current_chart)

        self.stretch_combo = ModernComboBox()
        for value, label in self.STRETCH_METHODS:
            self.stretch_combo.addItem(label, userData=value)
        self.stretch_combo.currentIndexChanged.connect(self.render_current_chart)

        self.projection_combo = ModernComboBox()
        for value, label in self.PROJECTION_PRESETS:
            self.projection_combo.addItem(label, userData=value)
        self.projection_combo.currentIndexChanged.connect(self.on_projection_changed)

        self.custom_projection_input = ModernLineEdit()
        self.custom_projection_input.setPlaceholderText("输入 EPSG:xxxx 或 proj 字符串")
        self.custom_projection_input.textChanged.connect(self.render_current_chart)

        self.spatial_mode_combo = ModernComboBox()
        for value, label in self.SPATIAL_DISPLAY_OPTIONS:
            self.spatial_mode_combo.addItem(label, userData=value)
        self.spatial_mode_combo.currentIndexChanged.connect(self.on_display_mode_changed)

        self.temporal_mode_combo = ModernComboBox()
        for value, label in self.TEMPORAL_DISPLAY_OPTIONS:
            self.temporal_mode_combo.addItem(label, userData=value)
        self.temporal_mode_combo.currentIndexChanged.connect(self.on_display_mode_changed)

        self.location_combo = ModernComboBox()
        self.location_combo.currentIndexChanged.connect(self.render_current_chart)
        self.location_field_combo = ModernComboBox()
        self.location_field_combo.currentIndexChanged.connect(self.on_location_field_changed)

        self.create_control_section(
            control_layout,
            "general",
            "基础设置",
            "先选图表，再补充标题、图例和精度等通用参数。",
        )
        self.add_control_field("general", "chart", "图表", self.chart_combo)
        self.add_control_field("general", "beta", "统计量", self.beta_combo)
        self.add_control_field("general", "title", "标题", self.title_input)
        self.add_control_field("general", "legend", "图例名称", self.legend_input)
        self.add_control_field("general", "font", "字体", self.font_combo)
        self.add_control_field("general", "decimal", "小数位", self.decimal_spin)
        self.add_control_field("general", "palette", "配色", self.palette_combo)

        self.create_control_section(
            control_layout,
            "filters",
            "筛选条件",
            "只在当前图表需要时间切片或分类时展示对应筛选项。",
        )
        self.add_control_field("filters", "time_column", "时间列", self.time_column_combo)
        self.add_control_field("filters", "time_value", "时间点", self.time_value_combo)
        self.add_control_field("filters", "category", "分类列", self.category_combo)

        self.create_control_section(
            control_layout,
            "spatial",
            "空间与展示模式",
            "空间图使用坐标字段，时空模型可切换按时间切片、汇总或单地点展示。",
        )
        self.add_control_field("spatial", "coordinate_type", "坐标类型", self.coordinate_type_combo)
        self.add_control_field("spatial", "longitude", self.longitude_label.text(), self.longitude_combo, label_widget=self.longitude_label)
        self.add_control_field("spatial", "latitude", self.latitude_label.text(), self.latitude_combo, label_widget=self.latitude_label)
        self.add_control_field("spatial", "spatial_mode", "空间展示", self.spatial_mode_combo)
        self.add_control_field("spatial", "temporal_mode", "时间展示", self.temporal_mode_combo)
        self.add_control_field("spatial", "location_field", "地点字段", self.location_field_combo)
        self.add_control_field("spatial", "location", "地点", self.location_combo)

        self.create_control_section(
            control_layout,
            "regional",
            "区域着色与底图",
            "只有区域着色图需要边界文件、投影和分级参数。",
        )
        self.add_custom_control("regional", "vector_actions", self.vector_action_row)
        self.add_custom_control("regional", "vector_label", self.vector_label)
        self.add_custom_control("regional", "raster_label", self.raster_label)
        self.add_control_field("regional", "stretch", "拉伸方式", self.stretch_combo)
        self.add_control_field("regional", "class_count", "分级数", self.class_count_spin)
        self.add_control_field("regional", "projection", "投影", self.projection_combo)
        self.add_control_field("regional", "custom_projection", "自定义投影", self.custom_projection_input)

        self.create_control_section(
            control_layout,
            "three_d",
            "3D 图设置",
            "仅在时间-分类 3D 图中展示布局和三轴比例参数。",
        )
        self.add_control_field("three_d", "time_slot_width", "时间占位宽度", self.time_slot_width_spin)
        self.add_control_field("three_d", "category_slot_width", "分类占位宽度", self.category_slot_width_spin)
        self.add_control_field("three_d", "figure_width", "图宽", self.figure_width_input)
        self.add_control_field("three_d", "figure_height", "图高", self.figure_height_input)
        self.add_control_field("three_d", "x_box_aspect", "X 轴比例", self.x_box_aspect_input)
        self.add_control_field("three_d", "y_box_aspect", "Y 轴比例", self.y_box_aspect_input)
        self.add_control_field("three_d", "z_box_aspect", "Z 轴比例", self.z_box_aspect_input)

        self.chart_hint_label = BodyLabel("请先加载包含 summary / coefficients 的结果文件。")
        self.chart_hint_label.setWordWrap(True)
        self.chart_hint_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.chart_hint_label)
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

    @staticmethod
    def create_action_row(*widgets):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
        return row

    def create_control_section(self, parent_layout, section_key, title, description):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader(title, description))
        self.control_sections[section_key] = section
        self.control_section_bodies[section_key] = layout
        parent_layout.addWidget(section)
        return section

    def add_control_field(self, section_key, field_key, label_text, widget, label_widget=None):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        label = label_widget or QLabel(label_text)
        label.setMinimumWidth(92)
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        self.control_section_bodies[section_key].addWidget(row)
        self.control_rows[field_key] = row
        self.control_field_sections[field_key] = section_key
        return row

    def add_custom_control(self, section_key, field_key, widget):
        self.control_section_bodies[section_key].addWidget(widget)
        self.control_rows[field_key] = widget
        self.control_field_sections[field_key] = section_key
        return widget

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
        self.chart_combo.blockSignals(True)
        self.chart_combo.clear()
        for spec in self.chart_specs:
            self.chart_combo.addItem(spec.label, userData=spec)
        self.chart_combo.blockSignals(False)

        self.beta_combo.blockSignals(True)
        self.beta_combo.clear()
        for column, display_name in self.dataset.get_metric_display_names():
            self.beta_combo.addItem(display_name, userData=column)
        self.beta_combo.blockSignals(False)

        self.coordinate_columns = self.dataset.spatial_candidate_columns()
        self.time_columns = self.dataset.temporal_candidate_columns()
        self.category_columns = self.dataset.category_candidate_columns()
        self.location_field_columns = self.dataset.location_candidate_columns()
        self.populate_coordinate_combos()
        self.populate_location_field_combo()
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
        self.longitude_combo.blockSignals(True)
        self.latitude_combo.blockSignals(True)
        self.coordinate_type_combo.blockSignals(True)
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
        if self.dataset is None:
            self.location_combo.blockSignals(False)
            return
        self.location_combo.addItem("请选择地点", userData=None)
        location_column = self.location_field_combo.currentData()
        x_col = self.longitude_combo.currentData()
        y_col = self.latitude_combo.currentData()
        self.location_options = self.dataset.location_value_options(location_column=location_column, x_column=x_col, y_column=y_col)
        for label, value in self.location_options:
            self.location_combo.addItem(label, userData=value)
        self.location_combo.setCurrentIndex(0)
        self.location_combo.blockSignals(False)

    def populate_location_field_combo(self):
        self.location_field_combo.blockSignals(True)
        self.location_field_combo.clear()
        if self.dataset is None:
            self.location_field_combo.blockSignals(False)
            self.populate_location_combo()
            return
        self.location_field_combo.addItem("使用坐标组合", userData=None)
        for column in self.location_field_columns:
            self.location_field_combo.addItem(str(column), userData=column)

        preferred = next((column for column in self.location_field_columns if str(column).startswith("Original_")), None)
        preferred = preferred or next(
            (
                column for column in self.location_field_columns
                if any(keyword in str(column).lower() for keyword in ("name", "region", "city", "county", "district", "地点", "地区", "区域"))
            ),
            None,
        )
        if preferred is not None:
            index = self.location_field_combo.findData(preferred)
            if index >= 0:
                self.location_field_combo.setCurrentIndex(index)
        self.location_field_combo.blockSignals(False)
        self.populate_location_combo()

    def populate_time_combos(self):
        self.time_column_combo.blockSignals(True)
        self.time_column_combo.clear()
        for column in self.time_columns:
            self.time_column_combo.addItem(str(column), userData=column)

        if self.dataset is not None and self.dataset.time_column:
            time_index = self.time_column_combo.findData(self.dataset.time_column)
            if time_index >= 0:
                self.time_column_combo.setCurrentIndex(time_index)
        elif self.time_columns:
            self.time_column_combo.setCurrentIndex(0)

        self.time_column_combo.blockSignals(False)
        self.refresh_time_value_options()

    def populate_category_combo(self):
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        for column in self.category_columns:
            self.category_combo.addItem(str(column), userData=column)
        if self.category_columns:
            self.category_combo.setCurrentIndex(0)
        self.category_combo.blockSignals(False)

    def refresh_time_value_options(self):
        self.time_value_combo.blockSignals(True)
        self.time_value_combo.clear()
        time_column = self.time_column_combo.currentData()
        if not self.dataset or not time_column:
            self.time_value_combo.blockSignals(False)
            return
        self.time_value_combo.addItem("全部时间", userData=None)
        for label, value in self.dataset.time_value_options(time_column):
            self.time_value_combo.addItem(label, userData=value)
        self.time_value_combo.setCurrentIndex(0)
        self.time_value_combo.blockSignals(False)

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
        spec = self.current_chart_spec()
        spatial_mode = self.spatial_mode_combo.currentData() if spec and ChartFactory.chart_uses_spatial_coordinates(spec.key) else "time_slice"
        temporal_mode = self.temporal_mode_combo.currentData() if spec and spec.key == "coefficient_temporal" else "aggregate_space"
        location_column = self.location_field_combo.currentData() if temporal_mode == "single_location" else None
        location_value = self.location_combo.currentData() if temporal_mode == "single_location" else None
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
            spatial_mode=spatial_mode or "time_slice",
            temporal_mode=temporal_mode or "aggregate_space",
            location_column=location_column,
            location_value=location_value,
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

    def build_control_policy(self, spec):
        visible_fields = {"chart", "title", "legend", "font", "decimal"}
        if spec is None:
            return ChartControlPolicy(tuple(visible_fields))

        uses_temporal_dataset = bool(self.dataset is not None and self.dataset.has_temporal())
        single_location_mode = bool(spec.key == "coefficient_temporal" and self.temporal_mode_combo.currentData() == "single_location")
        uses_location_coordinates = bool(single_location_mode and self.location_field_combo.currentData() is None)

        if spec.requires_beta:
            visible_fields.add("beta")

        if ChartFactory.chart_uses_colormap(spec.key):
            visible_fields.add("palette")

        if ChartFactory.chart_uses_time_column(spec.key) and self.time_columns:
            visible_fields.add("time_column")

        if ChartFactory.chart_uses_time_slice(spec.key) and self.time_columns:
            visible_fields.add("time_value")

        if ChartFactory.chart_uses_category_column(spec.key) and self.category_columns:
            visible_fields.add("category")

        if ChartFactory.chart_uses_spatial_coordinates(spec.key) and len(self.coordinate_columns) >= 2:
            visible_fields.update({"coordinate_type", "longitude", "latitude"})
        elif uses_location_coordinates and len(self.coordinate_columns) >= 2:
            visible_fields.update({"coordinate_type", "longitude", "latitude"})

        if uses_temporal_dataset and ChartFactory.chart_uses_spatial_coordinates(spec.key):
            visible_fields.add("spatial_mode")
            if self.spatial_mode_combo.currentData() == "aggregate_time":
                visible_fields.discard("time_value")

        if uses_temporal_dataset and spec.key == "coefficient_temporal":
            visible_fields.add("temporal_mode")
            if self.temporal_mode_combo.currentData() == "single_location":
                visible_fields.add("location_field")
                visible_fields.add("location")

        if spec.key == "coefficient_3d":
            visible_fields.update(
                {
                    "time_slot_width",
                    "category_slot_width",
                    "figure_width",
                    "figure_height",
                    "x_box_aspect",
                    "y_box_aspect",
                    "z_box_aspect",
                }
            )

        if ChartFactory.chart_requires_spatial_options(spec.key):
            visible_fields.update(
                {
                    "vector_actions",
                    "vector_label",
                    "raster_label",
                    "stretch",
                    "class_count",
                    "projection",
                }
            )
            if self.projection_combo.currentData() == "custom":
                visible_fields.add("custom_projection")

        return ChartControlPolicy(tuple(sorted(visible_fields)))

    def apply_control_policy(self, policy):
        for field_key, row in self.control_rows.items():
            row.setVisible(policy.includes(field_key))

        for section_key, section in self.control_sections.items():
            has_visible_field = any(
                policy.includes(field_key) for field_key, owner in self.control_field_sections.items() if owner == section_key
            )
            section.setVisible(has_visible_field)

    def update_control_enabled_state(self, spec):
        uses_coordinates = bool(spec and ChartFactory.chart_uses_spatial_coordinates(spec.key))
        uses_time_column = bool(spec and ChartFactory.chart_uses_time_column(spec.key))
        uses_time_slice = bool(spec and ChartFactory.chart_uses_time_slice(spec.key))
        uses_category = bool(spec and ChartFactory.chart_uses_category_column(spec.key))
        uses_time_slot_width = bool(spec and spec.key == "coefficient_3d")
        uses_temporal_dataset = bool(self.dataset is not None and self.dataset.has_temporal())
        uses_temporal_chart = bool(spec and spec.key == "coefficient_temporal")
        single_location_mode = bool(uses_temporal_chart and self.temporal_mode_combo.currentData() == "single_location")
        has_coordinate_candidates = len(self.coordinate_columns) >= 2
        has_time_candidates = bool(self.time_columns)
        has_category_candidates = bool(self.category_columns)
        uses_location_coordinates = bool(single_location_mode and self.location_field_combo.currentData() is None)

        self.coordinate_type_combo.setEnabled(has_coordinate_candidates and (uses_coordinates or uses_location_coordinates))
        self.longitude_combo.setEnabled(has_coordinate_candidates and (uses_coordinates or uses_location_coordinates))
        self.latitude_combo.setEnabled(has_coordinate_candidates and (uses_coordinates or uses_location_coordinates))
        self.time_column_combo.setEnabled(has_time_candidates and uses_time_column)
        self.time_value_combo.setEnabled(
            has_time_candidates
            and uses_time_slice
            and (not uses_temporal_dataset or self.spatial_mode_combo.currentData() != "aggregate_time")
        )
        self.category_combo.setEnabled(has_category_candidates and uses_category)
        self.spatial_mode_combo.setEnabled(has_coordinate_candidates and uses_coordinates and uses_temporal_dataset)
        self.temporal_mode_combo.setEnabled(uses_temporal_chart and uses_temporal_dataset)
        self.location_field_combo.setEnabled(single_location_mode and bool(self.location_field_columns))
        self.location_combo.setEnabled(single_location_mode)
        self.time_slot_width_spin.setEnabled(uses_time_slot_width)
        self.category_slot_width_spin.setEnabled(uses_time_slot_width)
        self.figure_width_input.setEnabled(uses_time_slot_width)
        self.figure_height_input.setEnabled(uses_time_slot_width)
        self.x_box_aspect_input.setEnabled(uses_time_slot_width)
        self.y_box_aspect_input.setEnabled(uses_time_slot_width)
        self.z_box_aspect_input.setEnabled(uses_time_slot_width)
        self.palette_combo.setEnabled(bool(spec and ChartFactory.chart_uses_colormap(spec.key)))

        requires_spatial = bool(spec and ChartFactory.chart_requires_spatial_options(spec.key))
        self.stretch_combo.setEnabled(requires_spatial)
        self.class_count_spin.setEnabled(requires_spatial)
        self.projection_combo.setEnabled(requires_spatial)
        self.custom_projection_input.setEnabled(requires_spatial and self.projection_combo.currentData() == "custom")

    def on_chart_changed(self):
        self.update_spatial_control_state()
        self.render_current_chart()

    def on_coordinate_selection_changed(self):
        self.populate_location_combo()
        self.render_current_chart()

    def on_time_column_changed(self):
        self.refresh_time_value_options()
        self.render_current_chart()

    def on_display_mode_changed(self):
        self.update_spatial_control_state()
        self.render_current_chart()

    def on_location_field_changed(self):
        self.populate_location_combo()
        self.update_spatial_control_state()
        self.render_current_chart()

    def on_decimal_changed(self):
        self.update_metrics()
        self.render_current_chart()

    def on_projection_changed(self):
        if self.projection_combo.currentData() != "custom":
            self.custom_projection_input.clear()
        self.update_spatial_control_state()
        self.render_current_chart()

    def update_spatial_control_state(self):
        spec = self.current_chart_spec()
        self.apply_control_policy(self.build_control_policy(spec))
        self.update_control_enabled_state(spec)
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
        if ChartFactory.chart_uses_time_slice(spec.key) and render_options.time_value is not None:
            parts.append(f"时间点：{render_options.time_value}")
        if self.dataset is not None and self.dataset.has_temporal():
            if ChartFactory.chart_uses_spatial_coordinates(spec.key):
                parts.append(f"空间展示：{self.spatial_mode_combo.currentText()}")
            if spec.key == "coefficient_temporal":
                parts.append(f"时间展示：{self.temporal_mode_combo.currentText()}")
                if render_options.location_column:
                    parts.append(f"地点字段：{render_options.location_column}")
                if render_options.location_value is not None:
                    parts.append(f"地点：{self.location_combo.currentText()}")
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

