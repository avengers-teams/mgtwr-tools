from __future__ import annotations

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel

from app.application.dto.network_analysis import NetworkCatalogLoadOptions
from app.presentation.renderers import network_map_renderer
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.fluent_surface import FrostedPanel
from app.presentation.views.widgets.input import ModernLineEdit


class NetworkMetricsDisplayPage(QWidget):
    VIEW_MODE_OPTIONS = [
        ("window_pair", "窗口配对地图"),
        ("metric_compare", "同指标比较"),
        ("metric_trend", "指标趋势"),
    ]

    def __init__(self, console_output, network_analysis_service):
        super().__init__()
        self.console_output = console_output
        self.network_analysis_service = network_analysis_service
        self.catalog = None
        self.extent = None
        self.boundary_gdf = None
        self.inner_boundary_gdf = None
        self.label_points = None
        self.label_layer_map = {}
        self.canvas = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        header = FrostedPanel(hero=True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(12)
        header_layout.addWidget(TitleLabel("网络分析 / 指标展示"))
        desc = SubtitleLabel("加载窗口指标结果后，可预览 Strength / Distance / Direction 配对地图，并批量导出。")
        desc.setWordWrap(True)
        header_layout.addWidget(desc)
        layout.addWidget(header)

        load_panel = FrostedPanel()
        load_layout = QGridLayout(load_panel)
        load_layout.setContentsMargins(20, 18, 20, 18)
        load_layout.setHorizontalSpacing(14)
        load_layout.setVerticalSpacing(12)

        load_layout.addWidget(QLabel("窗口根目录"), 0, 0)
        self.window_root_input = ModernLineEdit()
        self.window_root_input.setPlaceholderText("选择滑动窗口根目录")
        load_layout.addWidget(self.window_root_input, 0, 1, 1, 2)
        window_root_button = ModernButton("选择目录")
        window_root_button.clicked.connect(self.select_window_root)
        load_layout.addWidget(window_root_button, 0, 3)

        load_layout.addWidget(QLabel("外边界"), 1, 0)
        self.boundary_input = ModernLineEdit()
        self.boundary_input.setPlaceholderText("可选 shp / geojson")
        load_layout.addWidget(self.boundary_input, 1, 1, 1, 2)
        boundary_button = ModernButton("选择文件")
        boundary_button.clicked.connect(lambda: self.select_file(self.boundary_input, "选择外边界"))
        load_layout.addWidget(boundary_button, 1, 3)

        load_layout.addWidget(QLabel("内边界"), 2, 0)
        self.inner_boundary_input = ModernLineEdit()
        self.inner_boundary_input.setPlaceholderText("可选 shp / geojson")
        load_layout.addWidget(self.inner_boundary_input, 2, 1, 1, 2)
        inner_boundary_button = ModernButton("选择文件")
        inner_boundary_button.clicked.connect(lambda: self.select_file(self.inner_boundary_input, "选择内边界"))
        load_layout.addWidget(inner_boundary_button, 2, 3)

        load_layout.addWidget(QLabel("标签图层"), 3, 0)
        self.label_layer_combo = ModernComboBox()
        self.label_layer_combo.currentIndexChanged.connect(self.on_label_source_changed)
        load_layout.addWidget(self.label_layer_combo, 3, 1)

        load_layout.addWidget(QLabel("标签字段"), 3, 2)
        self.label_field_combo = ModernComboBox()
        self.label_field_combo.currentIndexChanged.connect(self.on_label_source_changed)
        load_layout.addWidget(self.label_field_combo, 3, 3)

        self.force_metrics_checkbox = QCheckBox("加载时强制重算指标")
        load_layout.addWidget(self.force_metrics_checkbox, 4, 0, 1, 2)

        load_layout.addWidget(QLabel("扇区数"), 4, 2)
        self.n_sectors_spin = QSpinBox()
        self.n_sectors_spin.setRange(4, 64)
        self.n_sectors_spin.setValue(8)
        load_layout.addWidget(self.n_sectors_spin, 4, 3)

        load_button_row = QHBoxLayout()
        load_button = ModernButton("加载窗口指标")
        load_button.clicked.connect(self.load_catalog)
        load_button_row.addWidget(load_button)
        load_button_row.addStretch(1)
        load_layout.addLayout(load_button_row, 5, 0, 1, 4)
        layout.addWidget(load_panel)

        control_panel = FrostedPanel()
        control_layout = QGridLayout(control_panel)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setHorizontalSpacing(14)
        control_layout.setVerticalSpacing(12)

        control_layout.addWidget(QLabel("窗口"), 0, 0)
        self.view_mode_combo = ModernComboBox()
        for value, label in self.VIEW_MODE_OPTIONS:
            self.view_mode_combo.addItem(label, userData=value)
        self.view_mode_combo.currentIndexChanged.connect(self.on_view_mode_changed)
        control_layout.addWidget(QLabel("视图"), 0, 0)
        control_layout.addWidget(self.view_mode_combo, 0, 1)

        control_layout.addWidget(QLabel("窗口"), 0, 2)
        self.window_combo = ModernComboBox()
        self.window_combo.currentIndexChanged.connect(self.render_current_figure)
        control_layout.addWidget(self.window_combo, 0, 3)

        control_layout.addWidget(QLabel("指标对"), 1, 0)
        self.pair_combo = ModernComboBox()
        for pair_id, label in network_map_renderer.available_metric_pairs():
            self.pair_combo.addItem(label, userData=pair_id)
        self.pair_combo.currentIndexChanged.connect(self.render_current_figure)
        control_layout.addWidget(self.pair_combo, 1, 1)

        control_layout.addWidget(QLabel("指标"), 1, 2)
        self.metric_combo = ModernComboBox()
        for metric, label in network_map_renderer.available_metrics():
            self.metric_combo.addItem(label, userData=metric)
        self.metric_combo.currentIndexChanged.connect(self.render_current_figure)
        control_layout.addWidget(self.metric_combo, 1, 3)

        control_layout.addWidget(QLabel("导出格式"), 2, 0)
        self.formats_input = ModernLineEdit()
        self.formats_input.setText("png,pdf")
        control_layout.addWidget(self.formats_input, 2, 1)

        control_layout.addWidget(QLabel("DPI"), 2, 2)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        control_layout.addWidget(self.dpi_spin, 2, 3)

        self.export_all_pairs_checkbox = QCheckBox("批量导出时包含全部指标对")
        self.export_all_pairs_checkbox.setChecked(True)
        control_layout.addWidget(self.export_all_pairs_checkbox, 3, 0, 1, 2)

        action_row = QHBoxLayout()
        export_current_button = ModernButton("导出当前图")
        export_current_button.clicked.connect(self.export_current_figure)
        export_batch_button = ModernButton("批量导出")
        export_batch_button.clicked.connect(self.export_batch_figures)
        action_row.addWidget(export_current_button)
        action_row.addWidget(export_batch_button)
        action_row.addStretch(1)
        control_layout.addLayout(action_row, 3, 2, 1, 2)

        self.info_label = BodyLabel("请先加载窗口指标。")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #5b6b84;")
        control_layout.addWidget(self.info_label, 4, 0, 1, 4)
        layout.addWidget(control_panel)

        chart_panel = FrostedPanel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(18, 18, 18, 18)
        chart_layout.setSpacing(10)
        chart_layout.addWidget(SubtitleLabel("图形预览"))
        self.canvas_container = QWidget()
        self.canvas_container_layout = QVBoxLayout(self.canvas_container)
        self.canvas_container_layout.setContentsMargins(0, 0, 0, 0)
        placeholder = QLabel("加载网络指标后将在此处显示地图")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setMinimumHeight(480)
        placeholder.setStyleSheet("color: #6b7280;")
        self.canvas_container_layout.addWidget(placeholder)
        chart_layout.addWidget(self.canvas_container)
        layout.addWidget(chart_panel, 1)
        self.update_view_mode_state()

    def select_window_root(self):
        directory = QFileDialog.getExistingDirectory(self, "选择滑动窗口根目录")
        if directory:
            self.window_root_input.setText(directory)

    def select_file(self, target_input, title: str):
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", "矢量/表格 (*.shp *.geojson *.json *.csv)")
        if file_path:
            target_input.setText(file_path)

    def load_catalog(self):
        window_root = self.window_root_input.text().strip()
        if not window_root:
            QMessageBox.warning(self, "缺少目录", "请先选择滑动窗口根目录。")
            return

        try:
            options = NetworkCatalogLoadOptions(
                window_root=window_root,
                n_sectors=int(self.n_sectors_spin.value()),
                force_metrics=self.force_metrics_checkbox.isChecked(),
            )
            self.catalog = self.network_analysis_service.load_catalog(options, progress_callback=self.console_output.append)
            self.boundary_gdf = self.network_analysis_service.load_vector_layer(self.boundary_input.text().strip() or None)
            self.inner_boundary_gdf = self.network_analysis_service.load_vector_layer(self.inner_boundary_input.text().strip() or None)
            self.populate_label_combos()
            self.extent = network_map_renderer.compute_catalog_extent(self.catalog)
            self.populate_window_combo()
            self.refresh_label_points()
            self.info_label.setText(f"已加载 {len(self.catalog)} 个窗口。")
            self.console_output.append(f"已加载网络指标目录: {window_root}")
            self.render_current_figure()
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", str(exc))
            self.console_output.append(f"网络指标加载失败: {exc}")

    def populate_window_combo(self):
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        if self.catalog is not None:
            for _, row in self.catalog.iterrows():
                text = str(row["window_label"])
                if "window_start" in row and "window_end" in row and pd.notna(row["window_start"]) and pd.notna(row["window_end"]):
                    try:
                        text = f"{row['window_label']} ({row['window_start']:%Y-%m-%d} ~ {row['window_end']:%Y-%m-%d})"
                    except Exception:
                        pass
                self.window_combo.addItem(text, userData=int(row.name))
        self.window_combo.blockSignals(False)
        if self.window_combo.count() > 0:
            self.window_combo.setCurrentIndex(0)

    def current_pair_config(self):
        return network_map_renderer.resolve_metric_pair(self.pair_combo.currentData() or "strength")

    def current_metric(self):
        return self.metric_combo.currentData() or "in_degree"

    def populate_label_combos(self):
        self.label_layer_map = {
            "外边界": self.boundary_gdf,
            "内边界": self.inner_boundary_gdf,
        }
        self.label_layer_combo.blockSignals(True)
        self.label_field_combo.blockSignals(True)
        self.label_layer_combo.clear()
        self.label_field_combo.clear()
        self.label_layer_combo.addItem("不显示标签", userData=None)

        for layer_name, gdf in self.label_layer_map.items():
            if gdf is not None and not gdf.empty:
                self.label_layer_combo.addItem(layer_name, userData=layer_name)

        self.label_layer_combo.setCurrentIndex(0)
        self.populate_label_field_combo()
        self.label_field_combo.blockSignals(False)
        self.label_layer_combo.blockSignals(False)

    def populate_label_field_combo(self):
        self.label_field_combo.blockSignals(True)
        self.label_field_combo.clear()
        self.label_field_combo.addItem("不显示标签", userData=None)

        layer_key = self.label_layer_combo.currentData()
        gdf = self.label_layer_map.get(layer_key)
        if gdf is not None and not gdf.empty:
            for column in gdf.columns:
                if str(column).lower() == "geometry":
                    continue
                self.label_field_combo.addItem(str(column), userData=str(column))

            preferred_keywords = ("name", "label", "region", "city", "county", "district", "乡", "镇", "村", "名称", "地区", "区域")
            for index in range(1, self.label_field_combo.count()):
                text = str(self.label_field_combo.itemData(index)).lower()
                if any(keyword in text for keyword in preferred_keywords):
                    self.label_field_combo.setCurrentIndex(index)
                    break

        self.label_field_combo.blockSignals(False)

    def refresh_label_points(self):
        layer_key = self.label_layer_combo.currentData()
        label_column = self.label_field_combo.currentData()
        gdf = self.label_layer_map.get(layer_key)
        self.label_points = self.network_analysis_service.build_label_points_from_vector(gdf, label_column)

    def on_label_source_changed(self):
        if self.sender() is self.label_layer_combo:
            self.populate_label_field_combo()
        self.refresh_label_points()
        self.render_current_figure()

    def on_view_mode_changed(self):
        self.update_view_mode_state()
        self.render_current_figure()

    def update_view_mode_state(self):
        mode = self.view_mode_combo.currentData() or "window_pair"
        is_pair = mode == "window_pair"
        self.window_combo.setEnabled(is_pair)
        self.pair_combo.setEnabled(is_pair)
        self.metric_combo.setEnabled(mode in {"metric_compare", "metric_trend"})
        self.export_all_pairs_checkbox.setEnabled(is_pair)

    def current_row(self):
        if self.catalog is None or self.window_combo.currentIndex() < 0:
            return None
        return self.catalog.iloc[self.window_combo.currentData()]

    def render_current_figure(self):
        if self.catalog is None or self.extent is None:
            return
        mode = self.view_mode_combo.currentData() or "window_pair"

        try:
            if mode == "window_pair":
                row = self.current_row()
                if row is None:
                    return
                figure = network_map_renderer.create_window_metric_pair_figure(
                    row=row,
                    pair_cfg=self.current_pair_config(),
                    extent=self.extent,
                    boundary_gdf=self.boundary_gdf,
                    inner_boundary_gdf=self.inner_boundary_gdf,
                    label_points=self.label_points,
                )
                info_text = (
                    f"当前窗口：{row['window_name']}，指标对：{self.pair_combo.currentText()}，"
                    f"可导出格式：{self.formats_input.text().strip() or 'png,pdf'}"
                )
            elif mode == "metric_compare":
                figure = network_map_renderer.create_metric_comparison_figure(
                    catalog=self.catalog,
                    metric=self.current_metric(),
                    boundary_gdf=self.boundary_gdf,
                    inner_boundary_gdf=self.inner_boundary_gdf,
                    label_points=self.label_points,
                )
                info_text = (
                    f"当前视图：同指标比较，指标：{self.metric_combo.currentText()}，"
                    f"窗口数：{len(self.catalog)}"
                )
            else:
                figure = network_map_renderer.create_metric_trend_figure(
                    catalog=self.catalog,
                    metric=self.current_metric(),
                )
                info_text = (
                    f"当前视图：指标趋势，指标：{self.metric_combo.currentText()}，"
                    f"窗口数：{len(self.catalog)}"
                )
        except Exception as exc:
            self.info_label.setText(f"图形渲染失败：{exc}")
            self.console_output.append(f"网络图渲染失败: {exc}")
            return

        self.info_label.setText(info_text)
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

    def export_current_figure(self):
        if self.canvas is None:
            QMessageBox.information(self, "暂无图表", "请先加载并生成图表。")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出当前图", "", "PNG 图片 (*.png);;PDF 文档 (*.pdf);;SVG 图片 (*.svg)")
        if not file_path:
            return

        try:
            self.canvas.figure.savefig(file_path, dpi=self.dpi_spin.value(), bbox_inches="tight")
            self.console_output.append(f"当前网络图已导出至 {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            self.console_output.append(f"当前网络图导出失败: {exc}")

    def export_batch_figures(self):
        if self.catalog is None:
            QMessageBox.information(self, "暂无数据", "请先加载窗口指标。")
            return
        if (self.view_mode_combo.currentData() or "window_pair") != "window_pair":
            QMessageBox.information(self, "当前视图不支持", "批量导出目前仅支持“窗口配对地图”视图。")
            return

        directory = QFileDialog.getExistingDirectory(self, "选择批量导出目录")
        if not directory:
            return

        formats = [item.strip() for item in self.formats_input.text().split(",") if item.strip()]
        if not formats:
            QMessageBox.warning(self, "格式错误", "请至少提供一个导出格式，例如 png,pdf。")
            return

        pair_ids = [pair_id for pair_id, _ in network_map_renderer.available_metric_pairs()] if self.export_all_pairs_checkbox.isChecked() else [self.pair_combo.currentData()]
        pair_configs = [network_map_renderer.resolve_metric_pair(pair_id) for pair_id in pair_ids]

        try:
            out_dir = network_map_renderer.export_window_pairs(
                catalog=self.catalog,
                pair_configs=pair_configs,
                out_dir=directory,
                formats=formats,
                dpi=int(self.dpi_spin.value()),
                boundary_gdf=self.boundary_gdf,
                inner_boundary_gdf=self.inner_boundary_gdf,
                label_points=self.label_points,
            )
            self.console_output.append(f"网络图批量导出完成: {out_dir}")
            QMessageBox.information(self, "导出完成", f"已导出到：{out_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            self.console_output.append(f"网络图批量导出失败: {exc}")
