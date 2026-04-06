from __future__ import annotations

from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel, TransparentPushButton

from app.application.services.nc_raster_tools import BatchProcessResult, NCRasterBatchOptions, NCRasterToolsService
from app.core.urltools import get_resource_path
from app.infrastructure.tasks.nc_raster_processing import NCRasterBatchThread
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.input import ModernCheckBox, ModernLineEdit
from app.presentation.views.widgets.list_widget import ModernListWidget


class NCRasterToolsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NC 重采样 / 裁切 / 重投影")
        self.resize(920, 760)
        self.setMinimumSize(720, 620)
        self.setWindowIcon(QIcon(get_resource_path("favicon.ico")))

        self.worker_thread: NCRasterBatchThread | None = None
        self.form_widgets: list[QWidget] = []
        self.init_ui()

    def init_ui(self):
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(14)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        header_layout.addWidget(TitleLabel("NC 栅格处理工具"))
        subtitle = SubtitleLabel("基于 netCDF4 读取 nc，支持批量重采样、裁切、重投影，并可对齐参考 tif/nc 或按额外维度拆分导出 tif。")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        file_group = QGroupBox("输入输出")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(10)

        self.input_path_edit = ModernLineEdit()
        self.input_path_edit.setPlaceholderText("选择单个 nc 文件，或选择包含多个 nc 的目录")
        self.input_path_edit.editingFinished.connect(self.on_input_path_changed)
        input_file_button = ModernButton("选择 nc 文件")
        input_file_button.clicked.connect(self.select_input_file)
        input_dir_button = ModernButton("选择目录")
        input_dir_button.clicked.connect(self.select_input_dir)
        file_layout.addWidget(self._field_label("输入路径"))
        file_layout.addWidget(self.input_path_edit)
        input_button_row = QHBoxLayout()
        input_button_row.addWidget(input_file_button)
        input_button_row.addWidget(input_dir_button)
        input_button_row.addStretch(1)
        file_layout.addLayout(input_button_row)

        self.output_dir_edit = ModernLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录")
        output_button = ModernButton("选择输出目录")
        output_button.clicked.connect(self.select_output_dir)
        file_layout.addWidget(self._field_label("输出目录"))
        file_layout.addWidget(self.output_dir_edit)
        output_button_row = QHBoxLayout()
        output_button_row.addWidget(output_button)
        output_button_row.addStretch(1)
        file_layout.addLayout(output_button_row)

        self.reference_path_edit = ModernLineEdit()
        self.reference_path_edit.setPlaceholderText("可选：上传参考 tif / nc，用于空间对齐与投影转换")
        self.reference_path_edit.editingFinished.connect(self.on_reference_path_changed)
        reference_button = ModernButton("选择参考文件")
        reference_button.clicked.connect(self.select_reference_file)
        clear_reference_button = TransparentPushButton("清空参考")
        clear_reference_button.clicked.connect(self.clear_reference_file)
        file_layout.addWidget(self._field_label("参考栅格"))
        file_layout.addWidget(self.reference_path_edit)
        reference_button_row = QHBoxLayout()
        reference_button_row.addWidget(reference_button)
        reference_button_row.addWidget(clear_reference_button)
        reference_button_row.addStretch(1)
        file_layout.addLayout(reference_button_row)

        self.reference_nodata_edit = ModernLineEdit()
        self.reference_nodata_edit.setPlaceholderText("参考 tif 的 nodata；选 tif 后会自动识别，也可手动修改")
        self.reference_nodata_hint = BodyLabel("参考 tif nodata：未识别")
        self.mask_by_reference_check = ModernCheckBox("按参考 tif nodata 掩膜输出")
        file_layout.addWidget(self._field_block("参考 NoData", self.reference_nodata_edit))
        file_layout.addWidget(self.reference_nodata_hint)
        file_layout.addWidget(self.mask_by_reference_check)

        self.clip_vector_path_edit = ModernLineEdit()
        self.clip_vector_path_edit.setPlaceholderText("可选：选择 shp/geojson/gpkg 作为裁切范围")
        clip_button = ModernButton("选择裁切矢量")
        clip_button.clicked.connect(self.select_clip_vector)
        clear_clip_button = TransparentPushButton("清空裁切矢量")
        clear_clip_button.clicked.connect(lambda: self.clip_vector_path_edit.clear())
        file_layout.addWidget(self._field_label("裁切矢量"))
        file_layout.addWidget(self.clip_vector_path_edit)
        clip_button_row = QHBoxLayout()
        clip_button_row.addWidget(clip_button)
        clip_button_row.addWidget(clear_clip_button)
        clip_button_row.addStretch(1)
        file_layout.addLayout(clip_button_row)

        self.recursive_check = ModernCheckBox("目录输入时深层遍历子目录")
        self.recursive_check.clicked.connect(self.reload_split_dimensions)
        file_layout.addWidget(self.recursive_check)
        layout.addWidget(file_group)

        option_group = QGroupBox("处理参数")
        option_layout = QVBoxLayout(option_group)
        option_layout.setSpacing(10)

        self.output_format_combo = ModernComboBox()
        for value, label in NCRasterToolsService.output_format_items():
            self.output_format_combo.addItem(label, userData=value)

        self.resampling_combo = ModernComboBox()
        for value, label in NCRasterToolsService.resampling_items():
            self.resampling_combo.addItem(label, userData=value)

        self.target_crs_edit = ModernLineEdit()
        self.target_crs_edit.setPlaceholderText("例如 EPSG:4326；留空则保持原坐标系或使用参考文件")

        self.resolution_x_edit = ModernLineEdit()
        self.resolution_x_edit.setPlaceholderText("X 分辨率")
        self.resolution_y_edit = ModernLineEdit()
        self.resolution_y_edit.setPlaceholderText("Y 分辨率")

        self.bounds_edit = ModernLineEdit()
        self.bounds_edit.setPlaceholderText("xmin,ymin,xmax,ymax；按输出坐标系解释")

        self.nodata_edit = ModernLineEdit()
        self.nodata_edit.setPlaceholderText("留空则尽量沿用源值")

        self.suffix_edit = ModernLineEdit()
        self.suffix_edit.setText("aligned")
        self.suffix_edit.setPlaceholderText("输出文件后缀")

        self.variables_edit = ModernLineEdit()
        self.variables_edit.setPlaceholderText("可选：变量名逗号分隔；留空表示处理全部空间变量")

        self.tif_split_dims_list = ModernListWidget()
        self.tif_split_dims_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.tif_split_dims_list.setMinimumHeight(120)
        self.tif_split_dims_hint = BodyLabel("TIFF 拆分维度：等待读取输入 nc")

        format_row = QHBoxLayout()
        format_row.addWidget(self._field_block("输出格式", self.output_format_combo), 1)
        format_row.addWidget(self._field_block("重采样方法", self.resampling_combo), 1)
        option_layout.addLayout(format_row)
        option_layout.addWidget(self._field_block("目标投影", self.target_crs_edit))

        resolution_row = QHBoxLayout()
        resolution_row.addWidget(self._field_block("X 分辨率", self.resolution_x_edit), 1)
        resolution_row.addWidget(self._field_block("Y 分辨率", self.resolution_y_edit), 1)
        option_layout.addLayout(resolution_row)

        option_layout.addWidget(self._field_block("裁切范围", self.bounds_edit))

        nodata_row = QHBoxLayout()
        nodata_row.addWidget(self._field_block("NoData", self.nodata_edit), 1)
        nodata_row.addWidget(self._field_block("输出后缀", self.suffix_edit), 1)
        option_layout.addLayout(nodata_row)

        option_layout.addWidget(self._field_block("变量过滤", self.variables_edit))
        option_layout.addWidget(self._field_block("TIFF 拆分维度", self.tif_split_dims_list))
        option_layout.addWidget(self.tif_split_dims_hint)
        layout.addWidget(option_group)

        hint_group = QGroupBox("说明")
        hint_layout = QVBoxLayout(hint_group)
        hint_layout.setSpacing(6)
        for text in (
            "参考文件优先级最高。提供 tif 或 nc 后，会按参考网格统一分辨率、范围和投影。",
            "未提供参考文件时，可用目标投影、分辨率和裁切范围单独控制输出网格。",
            "TIFF 拆分维度会从输入 nc 自动读取。未选择任何维度时，会按全部非空间维度完全拆分。",
            "没有被选中拆分的额外维度会写成同一个 TIFF 的多个波段，例如只选 time 不选 band，则每个时间输出一个多波段 tif。",
            "选择 shp/geojson/gpkg 后，会按矢量范围裁切，并在输出时按多边形外部做掩膜。",
            "当前工具仅支持规则 1 维经纬度/投影坐标网格，不支持曲线网格或非等间距坐标。",
        ):
            label = BodyLabel(text)
            label.setWordWrap(True)
            hint_layout.addWidget(label)
        layout.addWidget(hint_group)

        action_row = QHBoxLayout()
        self.start_button = ModernButton("开始处理")
        self.start_button.clicked.connect(self.start_processing)
        self.cancel_button = ModernButton("终止任务")
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setEnabled(False)
        clear_log_button = TransparentPushButton("清空日志")
        clear_log_button.clicked.connect(lambda: self.log_output.clear())
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(clear_log_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.status_label = BodyLabel("状态：等待开始")
        layout.addWidget(self.status_label)

        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_group)
        layout.addStretch(1)

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)
        self.setCentralWidget(container)

        self.form_widgets = [
            self.input_path_edit,
            self.output_dir_edit,
            self.reference_path_edit,
            self.reference_nodata_edit,
            self.mask_by_reference_check,
            self.clip_vector_path_edit,
            self.recursive_check,
            self.output_format_combo,
            self.resampling_combo,
            self.target_crs_edit,
            self.resolution_x_edit,
            self.resolution_y_edit,
            self.bounds_edit,
            self.nodata_edit,
            self.suffix_edit,
            self.variables_edit,
            self.tif_split_dims_list,
        ]

    def select_input_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 nc 文件", "", "NetCDF 文件 (*.nc)")
        if path:
            self.input_path_edit.setText(path)
            self.reload_split_dimensions()

    def select_input_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择 nc 目录")
        if path:
            self.input_path_edit.setText(path)
            self.reload_split_dimensions()

    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_dir_edit.setText(path)

    def select_reference_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择参考文件", "", "栅格文件 (*.tif *.tiff *.nc)")
        if path:
            self.reference_path_edit.setText(path)
            self.update_reference_metadata(path)

    def select_clip_vector(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择裁切矢量",
            "",
            "矢量文件 (*.shp *.geojson *.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson);;GeoPackage (*.gpkg)",
        )
        if path:
            self.clip_vector_path_edit.setText(path)

    def on_input_path_changed(self):
        if self.input_path_edit.text().strip():
            self.reload_split_dimensions()
        else:
            self.clear_split_dimensions()

    def on_reference_path_changed(self):
        path = self.reference_path_edit.text().strip()
        if path:
            self.update_reference_metadata(path)
        else:
            self.clear_reference_file()

    def clear_reference_file(self):
        self.reference_path_edit.clear()
        self.reference_nodata_edit.clear()
        self.reference_nodata_hint.setText("参考 tif nodata：未识别")
        self.mask_by_reference_check.setChecked(False)

    def clear_split_dimensions(self):
        self.tif_split_dims_list.clear()
        self.tif_split_dims_hint.setText("TIFF 拆分维度：等待读取输入 nc")

    def reload_split_dimensions(self):
        input_path = self.input_path_edit.text().strip()
        if not input_path:
            self.clear_split_dimensions()
            return
        try:
            dimensions, sample_file = NCRasterToolsService.inspect_tif_split_dimensions(
                input_path,
                recursive=self.recursive_check.isChecked(),
            )
        except Exception as exc:
            self.clear_split_dimensions()
            self.tif_split_dims_hint.setText(f"TIFF 拆分维度读取失败：{exc}")
            return

        self.tif_split_dims_list.clear()
        for dim_name in dimensions:
            self.tif_split_dims_list.addItem(QListWidgetItem(dim_name))

        if dimensions:
            sample_text = f"；样例文件：{sample_file}" if sample_file else ""
            self.tif_split_dims_hint.setText(f"已读取到可拆分维度：{', '.join(dimensions)}{sample_text}")
        else:
            self.tif_split_dims_hint.setText("未读取到可拆分的非空间维度，输出 TIFF 时将写为单波段")

    def update_reference_metadata(self, path: str):
        suffix = path.lower()
        if suffix.endswith((".tif", ".tiff")):
            try:
                info = NCRasterToolsService.inspect_reference_tif(path)
            except Exception as exc:
                self.reference_nodata_hint.setText(f"参考 tif nodata：读取失败（{exc}）")
                return
            nodata = info.get("nodata")
            if nodata is None:
                self.reference_nodata_edit.clear()
                self.reference_nodata_hint.setText("参考 tif nodata：未检测到，可手动填写")
            else:
                self.reference_nodata_edit.setText(str(nodata))
                self.reference_nodata_hint.setText(f"参考 tif nodata：已自动识别为 {nodata}")
            return

        self.reference_nodata_edit.clear()
        self.reference_nodata_hint.setText("当前参考文件不是 tif，nodata 自动识别不可用")
        self.mask_by_reference_check.setChecked(False)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 600; color: #334155;")
        return label

    def _field_block(self, title: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._field_label(title))
        layout.addWidget(widget)
        return container

    def start_processing(self):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.information(self, "任务进行中", "当前已有任务在运行")
            return

        try:
            options = self.build_options()
        except Exception as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return

        self.log_output.clear()
        self.append_log("开始创建批处理任务")
        self.set_form_enabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("状态：处理中")

        self.worker_thread = NCRasterBatchThread(options)
        self.worker_thread.progress_signal.connect(self.append_log)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()

    def build_options(self) -> NCRasterBatchOptions:
        input_path = self.input_path_edit.text().strip()
        output_dir = self.output_dir_edit.text().strip()
        if not input_path:
            raise ValueError("请选择输入 nc 文件或目录")
        if not output_dir:
            raise ValueError("请选择输出目录")

        reference_path = self.reference_path_edit.text().strip() or None
        reference_nodata = NCRasterToolsService.parse_optional_float(self.reference_nodata_edit.text())
        clip_vector_path = self.clip_vector_path_edit.text().strip() or None
        target_crs = self.target_crs_edit.text().strip() or None
        res_x = NCRasterToolsService.parse_optional_float(self.resolution_x_edit.text())
        res_y = NCRasterToolsService.parse_optional_float(self.resolution_y_edit.text())
        resolution = None
        if (res_x is None) ^ (res_y is None):
            raise ValueError("X/Y 分辨率需要同时填写")
        if res_x is not None and res_y is not None:
            if res_x <= 0 or res_y <= 0:
                raise ValueError("分辨率必须大于 0")
            resolution = (res_x, res_y)

        nodata = NCRasterToolsService.parse_optional_float(self.nodata_edit.text())
        crop_bounds = NCRasterToolsService.parse_bounds_text(self.bounds_edit.text())
        variables = NCRasterToolsService.parse_variable_text(self.variables_edit.text())
        tif_split_dims = tuple(item.text() for item in self.tif_split_dims_list.selectedItems())
        suffix = self.suffix_edit.text().strip() or "aligned"

        if self.mask_by_reference_check.isChecked():
            if not reference_path:
                raise ValueError("开启参考掩膜时必须选择参考 tif")
            if not reference_path.lower().endswith((".tif", ".tiff")):
                raise ValueError("参考掩膜当前仅支持 tif/tiff")

        return NCRasterBatchOptions(
            input_path=input_path,
            output_dir=output_dir,
            output_format=self.output_format_combo.currentData(),
            recursive=self.recursive_check.isChecked(),
            reference_path=reference_path,
            reference_nodata=reference_nodata,
            mask_by_reference=self.mask_by_reference_check.isChecked(),
            clip_vector_path=clip_vector_path,
            target_crs=target_crs,
            crop_bounds=crop_bounds,
            resolution=resolution,
            nodata=nodata,
            resampling=self.resampling_combo.currentData(),
            suffix=suffix,
            variables=variables,
            tif_split_dims=tif_split_dims,
        )

    def cancel_processing(self):
        if self.worker_thread is None or not self.worker_thread.isRunning():
            return
        self.worker_thread.stop()
        self.append_log("已发送终止请求，等待当前切片完成")
        self.status_label.setText("状态：终止中")

    def append_log(self, message: str):
        self.log_output.append(str(message))

    def on_finished(self, result: BatchProcessResult):
        if self.worker_thread is not None:
            self.worker_thread.wait(500)
            self.worker_thread = None

        self.set_form_enabled(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        self.append_log("")
        self.append_log(f"完成文件数: {result.processed_files}")
        self.append_log(f"失败文件数: {result.failed_files}")
        self.append_log(f"生成输出数: {len(result.generated_outputs)}")
        for failure in result.failures:
            self.append_log(f"失败详情: {failure}")

        if result.failed_files:
            self.status_label.setText("状态：已完成，存在失败项")
        else:
            self.status_label.setText("状态：处理完成")

    def on_error(self, message: str):
        if self.worker_thread is not None:
            self.worker_thread.wait(500)
            self.worker_thread = None

        self.set_form_enabled(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("状态：执行失败")
        self.append_log(f"执行失败: {message}")
        QMessageBox.critical(self, "处理失败", message)

    def set_form_enabled(self, enabled: bool):
        for widget in self.form_widgets:
            widget.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait(2000)
        super().closeEvent(event)
