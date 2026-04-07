from __future__ import annotations

import os

from PyQt5.QtCore import QMimeData, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QCloseEvent, QDrag, QIcon
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
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel, TransparentPushButton
from rasterio.crs import CRS

from app.application.services.tif_workflow_tools import (
    ClipStepConfig,
    ReclassifyStepConfig,
    ReprojectStepConfig,
    ResampleStepConfig,
    TifBatchProcessResult,
    TifBatchWorkflowOptions,
    TifWorkflowToolsService,
)
from app.core.urltools import get_resource_path
from app.infrastructure.tasks.tif_workflow_processing import TifWorkflowBatchThread
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox
from app.presentation.views.widgets.input import ModernCheckBox, ModernLineEdit
from app.presentation.views.widgets.list_widget import ModernListWidget


class WorkflowTemplateListWidget(ModernListWidget):
    MIME_TYPE = "application/x-cdata-tif-workflow-step"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return

        mime = QMimeData()
        mime.setData(self.MIME_TYPE, str(item.data(Qt.UserRole)).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class WorkflowPipelineListWidget(ModernListWidget):
    step_dropped = pyqtSignal(str, int)
    sequence_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dragEnterEvent(self, event):
        if event.source() is self or event.mimeData().hasFormat(WorkflowTemplateListWidget.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() is self or event.mimeData().hasFormat(WorkflowTemplateListWidget.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.source() is self:
            super().dropEvent(event)
            self.sequence_changed.emit()
            return

        if event.mimeData().hasFormat(WorkflowTemplateListWidget.MIME_TYPE):
            key = bytes(event.mimeData().data(WorkflowTemplateListWidget.MIME_TYPE)).decode("utf-8")
            row = self.indexAt(event.pos()).row()
            if row < 0:
                row = self.count()
            self.step_dropped.emit(key, row)
            event.acceptProposedAction()
            return

        super().dropEvent(event)


class TifWorkflowToolsWindow(QMainWindow):
    STEP_LIBRARY = [
        ("clip", "裁切 / 掩膜", "shp 或参考 tif 掩膜，可按有效数据范围裁剪"),
        ("resample", "重采样", "按参考 tif 对齐，或手动输入目标分辨率"),
        ("reproject", "重投影", "识别输入投影并输出到库支持的 CRS"),
        ("reclassify", "重分类", "支持区间映射和一对一映射"),
    ]
    STEP_TITLES = {key: title for key, title, _desc in STEP_LIBRARY}

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TIF 批处理流程工具")
        self.resize(1080, 860)
        self.setMinimumSize(860, 700)
        self.setWindowIcon(QIcon(get_resource_path("favicon.ico")))

        self.worker_thread: TifWorkflowBatchThread | None = None
        self.form_widgets: list[QWidget] = []
        self.sample_info: dict[str, object] | None = None
        self._syncing_step_widgets = False
        self.reclass_rule_rows: list[dict[str, QWidget]] = []

        self.init_ui()
        self.refresh_input_metadata()
        self.update_clip_state()
        self.update_resample_state()
        self.update_reproject_state()
        self.update_reclassify_state()
        self.refresh_pipeline_items()

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
        header_layout.addWidget(TitleLabel("TIF 批处理流程"))
        subtitle = SubtitleLabel("支持批量 tif 裁切、重采样、重投影、重分类，并通过拖拽组织处理顺序。")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        file_group = QGroupBox("输入输出")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(10)

        self.input_path_edit = ModernLineEdit()
        self.input_path_edit.setPlaceholderText("选择单个 tif/tiff，或选择包含多个 tif 的目录")
        self.input_path_edit.editingFinished.connect(self.refresh_input_metadata)
        self.input_file_button = ModernButton("选择 tif 文件")
        self.input_file_button.clicked.connect(self.select_input_file)
        self.input_dir_button = ModernButton("选择目录")
        self.input_dir_button.clicked.connect(self.select_input_dir)
        file_layout.addWidget(self._field_label("输入路径"))
        file_layout.addWidget(self.input_path_edit)
        input_button_row = QHBoxLayout()
        input_button_row.addWidget(self.input_file_button)
        input_button_row.addWidget(self.input_dir_button)
        input_button_row.addStretch(1)
        file_layout.addLayout(input_button_row)

        self.output_dir_edit = ModernLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录")
        self.output_dir_button = ModernButton("选择输出目录")
        self.output_dir_button.clicked.connect(self.select_output_dir)
        file_layout.addWidget(self._field_label("输出目录"))
        file_layout.addWidget(self.output_dir_edit)
        output_button_row = QHBoxLayout()
        output_button_row.addWidget(self.output_dir_button)
        output_button_row.addStretch(1)
        file_layout.addLayout(output_button_row)

        source_row = QHBoxLayout()
        self.source_crs_override_edit = QTextEdit()
        self.source_crs_override_edit.setAcceptRichText(False)
        self.source_crs_override_edit.setMinimumHeight(72)
        self.source_crs_override_edit.setPlaceholderText("源 tif 缺少投影时可手动填写，支持 EPSG / PROJ / WKT")
        self.source_crs_override_edit.textChanged.connect(self.refresh_detected_crs_hint)
        self.output_suffix_edit = ModernLineEdit()
        self.output_suffix_edit.setText("workflow")
        self.output_suffix_edit.setPlaceholderText("输出文件后缀")
        source_row.addWidget(self._field_block("源 CRS 覆写", self.source_crs_override_edit), 1)
        source_row.addWidget(self._field_block("输出后缀", self.output_suffix_edit), 1)
        file_layout.addLayout(source_row)

        self.recursive_check = ModernCheckBox("目录输入时递归搜索子目录")
        self.recursive_check.clicked.connect(self.refresh_input_metadata)
        file_layout.addWidget(self.recursive_check)

        self.sample_info_label = BodyLabel("输入样本：未选择")
        self.sample_info_label.setWordWrap(True)
        file_layout.addWidget(self.sample_info_label)
        layout.addWidget(file_group)

        workflow_group = QGroupBox("流程编排")
        workflow_layout = QHBoxLayout(workflow_group)
        workflow_layout.setSpacing(12)

        template_panel = QWidget()
        template_layout = QVBoxLayout(template_panel)
        template_layout.setContentsMargins(0, 0, 0, 0)
        template_layout.setSpacing(8)
        template_layout.addWidget(self._field_label("可用步骤"))
        self.template_list = WorkflowTemplateListWidget()
        self.template_list.setMinimumWidth(260)
        self.template_list.setMinimumHeight(220)
        self.template_list.itemDoubleClicked.connect(self.on_template_double_clicked)
        for key, title, desc in self.STEP_LIBRARY:
            item = QListWidgetItem(f"{title}\n{desc}")
            item.setData(Qt.UserRole, key)
            item.setToolTip(desc)
            item.setSizeHint(QSize(0, 54))
            self.template_list.addItem(item)
        template_layout.addWidget(self.template_list)
        template_hint = BodyLabel("从这里拖到右侧流程区，或双击加入流程。")
        template_hint.setWordWrap(True)
        template_layout.addWidget(template_hint)
        workflow_layout.addWidget(template_panel, 1)

        pipeline_panel = QWidget()
        pipeline_layout = QVBoxLayout(pipeline_panel)
        pipeline_layout.setContentsMargins(0, 0, 0, 0)
        pipeline_layout.setSpacing(8)
        pipeline_layout.addWidget(self._field_label("批处理流程"))

        self.pipeline_list = WorkflowPipelineListWidget()
        self.pipeline_list.setMinimumHeight(220)
        self.pipeline_list.step_dropped.connect(self.add_step_by_key)
        self.pipeline_list.sequence_changed.connect(self.refresh_pipeline_items)
        self.pipeline_list.currentItemChanged.connect(self.on_current_step_changed)
        pipeline_layout.addWidget(self.pipeline_list)

        pipeline_button_row = QHBoxLayout()
        self.remove_step_button = TransparentPushButton("移除选中步骤")
        self.remove_step_button.clicked.connect(self.remove_selected_step)
        self.clear_steps_button = TransparentPushButton("清空流程")
        self.clear_steps_button.clicked.connect(self.clear_pipeline)
        pipeline_button_row.addWidget(self.remove_step_button)
        pipeline_button_row.addWidget(self.clear_steps_button)
        pipeline_button_row.addStretch(1)
        pipeline_layout.addLayout(pipeline_button_row)

        self.pipeline_hint_label = BodyLabel("拖拽可调整顺序。执行时会严格按这里的先后顺序运行。")
        self.pipeline_hint_label.setWordWrap(True)
        pipeline_layout.addWidget(self.pipeline_hint_label)

        config_group = QGroupBox("当前步骤参数")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(10)
        self.current_step_label = BodyLabel("当前步骤：未选择")
        config_layout.addWidget(self.current_step_label)

        self.step_stack = QStackedWidget()
        self.empty_step_page = self._build_empty_step_page()
        self.clip_page = self._build_clip_page()
        self.resample_page = self._build_resample_page()
        self.reproject_page = self._build_reproject_page()
        self.reclassify_page = self._build_reclassify_page()
        self.step_stack.addWidget(self.empty_step_page)
        self.step_stack.addWidget(self.clip_page)
        self.step_stack.addWidget(self.resample_page)
        self.step_stack.addWidget(self.reproject_page)
        self.step_stack.addWidget(self.reclassify_page)
        config_layout.addWidget(self.step_stack)
        pipeline_layout.addWidget(config_group)

        workflow_layout.addWidget(pipeline_panel, 2)
        layout.addWidget(workflow_group)

        hint_group = QGroupBox("说明")
        hint_layout = QVBoxLayout(hint_group)
        hint_layout.setSpacing(6)
        for text in (
            "裁切步骤支持两种方式：shp/geojson/gpkg 掩膜，或参考 tif 网格掩膜。",
            "参考 tif 裁切和参考 tif 重采样都会把输出对齐到参考网格；如果坐标系不同，会自动做一次对齐转换。",
            "重投影会优先识别输入 tif 的 CRS；若输入文件没有投影，可在输入区填写“源 CRS 覆写”。",
            "流程区允许自由拖拽排序，实际执行顺序与右侧列表完全一致。",
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
        self.clear_log_button = TransparentPushButton("清空日志")
        self.clear_log_button.clicked.connect(lambda: self.log_output.clear())
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.clear_log_button)
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
            self.source_crs_override_edit,
            self.output_suffix_edit,
            self.recursive_check,
            self.input_file_button,
            self.input_dir_button,
            self.output_dir_button,
            self.template_list,
            self.pipeline_list,
            self.remove_step_button,
            self.clear_steps_button,
            self.clip_mode_combo,
            self.clip_mask_path_edit,
            self.clip_select_button,
            self.clip_clear_button,
            self.clip_use_reference_nodata_check,
            self.clip_trim_nodata_check,
            self.clip_all_touched_check,
            self.clip_resampling_combo,
            self.resample_mode_combo,
            self.resample_reference_edit,
            self.resample_reference_button,
            self.resample_reference_clear_button,
            self.resample_resolution_x_edit,
            self.resample_resolution_y_edit,
            self.resample_method_combo,
            self.reproject_target_combo,
            self.reproject_custom_edit,
            self.reproject_use_input_crs_button,
            self.reproject_method_combo,
            self.reclass_mode_combo,
            self.reclass_add_rule_button,
            self.reclass_keep_unmatched_check,
            self.reclass_output_nodata_edit,
        ]

    def _build_empty_step_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = BodyLabel("先把步骤拖到流程区，再在这里编辑参数。")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _build_clip_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.clip_mode_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.clip_mode_items():
            self.clip_mode_combo.addItem(label, userData=value)
        self.clip_mode_combo.currentIndexChanged.connect(self.update_clip_state)
        self.clip_mode_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("裁切模式", self.clip_mode_combo))

        self.clip_mask_path_edit = ModernLineEdit()
        self.clip_mask_path_edit.setPlaceholderText("选择 shp/geojson/gpkg 或参考 tif")
        self.clip_mask_path_edit.editingFinished.connect(self.on_step_config_changed)
        self.clip_select_button = ModernButton("选择掩膜文件")
        self.clip_select_button.clicked.connect(self.select_clip_mask_file)
        self.clip_clear_button = TransparentPushButton("清空")
        self.clip_clear_button.clicked.connect(self.clear_clip_mask_path)
        layout.addWidget(self._field_block("掩膜路径", self.clip_mask_path_edit))
        button_row = QHBoxLayout()
        button_row.addWidget(self.clip_select_button)
        button_row.addWidget(self.clip_clear_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.clip_use_reference_nodata_check = ModernCheckBox("按参考 tif 的 NoData 做掩膜")
        self.clip_use_reference_nodata_check.setChecked(True)
        self.clip_use_reference_nodata_check.stateChanged.connect(self.on_step_config_changed)
        self.clip_trim_nodata_check = ModernCheckBox("按有效数据范围裁剪（去除外圈 NoData）")
        self.clip_trim_nodata_check.stateChanged.connect(self.on_step_config_changed)
        self.clip_all_touched_check = ModernCheckBox("矢量裁切时启用 all touched")
        self.clip_all_touched_check.stateChanged.connect(self.on_step_config_changed)
        layout.addWidget(self.clip_use_reference_nodata_check)
        layout.addWidget(self.clip_trim_nodata_check)
        layout.addWidget(self.clip_all_touched_check)

        self.clip_resampling_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.resampling_items():
            self.clip_resampling_combo.addItem(label, userData=value)
        self.clip_resampling_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("参考对齐重采样", self.clip_resampling_combo))

        self.clip_hint_label = BodyLabel("")
        self.clip_hint_label.setWordWrap(True)
        layout.addWidget(self.clip_hint_label)
        layout.addStretch(1)
        return page

    def _build_resample_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.resample_mode_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.resample_mode_items():
            self.resample_mode_combo.addItem(label, userData=value)
        self.resample_mode_combo.currentIndexChanged.connect(self.update_resample_state)
        self.resample_mode_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("重采样模式", self.resample_mode_combo))

        self.resample_reference_edit = ModernLineEdit()
        self.resample_reference_edit.setPlaceholderText("参考 tif")
        self.resample_reference_edit.editingFinished.connect(self.on_step_config_changed)
        self.resample_reference_button = ModernButton("选择参考 tif")
        self.resample_reference_button.clicked.connect(self.select_resample_reference_file)
        self.resample_reference_clear_button = TransparentPushButton("清空")
        self.resample_reference_clear_button.clicked.connect(self.clear_resample_reference_path)
        layout.addWidget(self._field_block("参考栅格", self.resample_reference_edit))
        button_row = QHBoxLayout()
        button_row.addWidget(self.resample_reference_button)
        button_row.addWidget(self.resample_reference_clear_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        resolution_row = QHBoxLayout()
        self.resample_resolution_x_edit = ModernLineEdit()
        self.resample_resolution_x_edit.setPlaceholderText("X 分辨率")
        self.resample_resolution_x_edit.editingFinished.connect(self.on_step_config_changed)
        self.resample_resolution_y_edit = ModernLineEdit()
        self.resample_resolution_y_edit.setPlaceholderText("Y 分辨率")
        self.resample_resolution_y_edit.editingFinished.connect(self.on_step_config_changed)
        resolution_row.addWidget(self._field_block("X 分辨率", self.resample_resolution_x_edit), 1)
        resolution_row.addWidget(self._field_block("Y 分辨率", self.resample_resolution_y_edit), 1)
        layout.addLayout(resolution_row)

        self.resample_method_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.resampling_items():
            self.resample_method_combo.addItem(label, userData=value)
        self.resample_method_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("重采样方法", self.resample_method_combo))

        self.resample_hint_label = BodyLabel("")
        self.resample_hint_label.setWordWrap(True)
        layout.addWidget(self.resample_hint_label)
        layout.addStretch(1)
        return page

    def _build_reproject_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.reproject_detected_crs_label = BodyLabel("输入投影：待识别")
        self.reproject_detected_crs_label.setWordWrap(True)
        layout.addWidget(self.reproject_detected_crs_label)

        self.reproject_target_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.projection_preset_items():
            self.reproject_target_combo.addItem(label, userData=value)
        default_index = self.reproject_target_combo.findData("EPSG:4326")
        self.reproject_target_combo.setCurrentIndex(default_index if default_index >= 0 else 0)
        self.reproject_target_combo.currentIndexChanged.connect(self.update_reproject_state)
        self.reproject_target_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("目标投影", self.reproject_target_combo))

        self.reproject_custom_edit = QTextEdit()
        self.reproject_custom_edit.setAcceptRichText(False)
        self.reproject_custom_edit.setMinimumHeight(88)
        self.reproject_custom_edit.setPlaceholderText("输入自定义 CRS，支持 EPSG / PROJ / WKT")
        self.reproject_custom_edit.textChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("自定义投影", self.reproject_custom_edit))

        self.reproject_use_input_crs_button = TransparentPushButton("使用输入影像投影")
        self.reproject_use_input_crs_button.clicked.connect(self.apply_detected_crs_to_custom_target)
        layout.addWidget(self.reproject_use_input_crs_button)

        self.reproject_method_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.resampling_items():
            self.reproject_method_combo.addItem(label, userData=value)
        self.reproject_method_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("重投影重采样", self.reproject_method_combo))

        self.reproject_hint_label = BodyLabel("")
        self.reproject_hint_label.setWordWrap(True)
        layout.addWidget(self.reproject_hint_label)
        layout.addStretch(1)
        return page

    def _build_reclassify_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.reclass_mode_combo = ModernComboBox()
        for value, label in TifWorkflowToolsService.reclass_mode_items():
            self.reclass_mode_combo.addItem(label, userData=value)
        self.reclass_mode_combo.currentIndexChanged.connect(self.update_reclassify_state)
        self.reclass_mode_combo.currentIndexChanged.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("重分类模式", self.reclass_mode_combo))

        rules_group = QGroupBox("分类规则")
        rules_layout = QVBoxLayout(rules_group)
        rules_layout.setContentsMargins(10, 10, 10, 10)
        rules_layout.setSpacing(8)

        self.reclass_rules_header = BodyLabel("")
        self.reclass_rules_header.setWordWrap(True)
        rules_layout.addWidget(self.reclass_rules_header)

        self.reclass_rules_container = QWidget()
        self.reclass_rules_layout = QVBoxLayout(self.reclass_rules_container)
        self.reclass_rules_layout.setContentsMargins(0, 0, 0, 0)
        self.reclass_rules_layout.setSpacing(8)
        rules_layout.addWidget(self.reclass_rules_container)

        self.reclass_add_rule_button = TransparentPushButton("添加类别")
        self.reclass_add_rule_button.clicked.connect(self.add_reclass_rule_row)
        rules_layout.addWidget(self.reclass_add_rule_button)
        layout.addWidget(rules_group)

        self.reclass_keep_unmatched_check = ModernCheckBox("未命中规则时保留原值")
        self.reclass_keep_unmatched_check.setChecked(True)
        self.reclass_keep_unmatched_check.stateChanged.connect(self.on_step_config_changed)
        layout.addWidget(self.reclass_keep_unmatched_check)

        self.reclass_output_nodata_edit = ModernLineEdit()
        self.reclass_output_nodata_edit.setPlaceholderText("可选：重分类输出 NoData")
        self.reclass_output_nodata_edit.editingFinished.connect(self.on_step_config_changed)
        layout.addWidget(self._field_block("输出 NoData", self.reclass_output_nodata_edit))

        self.reclass_hint_label = BodyLabel("")
        self.reclass_hint_label.setWordWrap(True)
        layout.addWidget(self.reclass_hint_label)
        layout.addStretch(1)
        return page

    def select_input_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 tif 文件", "", "栅格文件 (*.tif *.tiff)")
        if path:
            self.input_path_edit.setText(path)
            self.refresh_input_metadata()

    def select_input_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择 tif 目录")
        if path:
            self.input_path_edit.setText(path)
            self.refresh_input_metadata()

    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_dir_edit.setText(path)

    def select_clip_mask_file(self):
        if self.clip_mode_combo.currentData() == "reference":
            path, _ = QFileDialog.getOpenFileName(self, "选择参考 tif", "", "栅格文件 (*.tif *.tiff)")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择裁切矢量",
                "",
                "矢量文件 (*.shp *.geojson *.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson);;GeoPackage (*.gpkg)",
            )
        if path:
            self.clip_mask_path_edit.setText(path)
            self.on_step_config_changed()

    def select_resample_reference_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择参考 tif", "", "栅格文件 (*.tif *.tiff)")
        if path:
            self.resample_reference_edit.setText(path)
            self.on_step_config_changed()

    def clear_clip_mask_path(self):
        self._clear_line_edit(self.clip_mask_path_edit)
        self.on_step_config_changed()

    def clear_resample_reference_path(self):
        self._clear_line_edit(self.resample_reference_edit)
        self.on_step_config_changed()

    def refresh_input_metadata(self):
        input_path = self.input_path_edit.text().strip()
        self.sample_info = None
        if not input_path:
            self.sample_info_label.setText("输入样本：未选择")
            self.refresh_detected_crs_hint()
            return

        try:
            self.sample_info = TifWorkflowToolsService.inspect_input_source(input_path, self.recursive_check.isChecked())
        except Exception as exc:
            self.sample_info_label.setText(f"输入样本读取失败：{exc}")
            self.refresh_detected_crs_hint()
            return

        if self.sample_info is None:
            self.sample_info_label.setText("输入样本：没有找到 tif/tiff 文件")
            self.refresh_detected_crs_hint()
            return

        resolution = self.sample_info.get("resolution") or ("?", "?")
        path_text = self.sample_info.get("path", "")
        crs_text = self.sample_info.get("crs_display") or self.sample_info.get("crs") or "未识别"
        nodata_text = self.sample_info.get("nodata")
        self.sample_info_label.setText(
            "输入样本："
            f"{path_text}\n"
            f"投影={crs_text}，分辨率={resolution[0]} x {resolution[1]}，"
            f"尺寸={self.sample_info.get('width')} x {self.sample_info.get('height')}，"
            f"波段={self.sample_info.get('bands')}，dtype={self.sample_info.get('dtype')}，nodata={nodata_text}"
        )
        self.refresh_detected_crs_hint()

    def refresh_detected_crs_hint(self):
        sample_crs = ""
        sample_input = ""
        if self.sample_info:
            sample_crs = str(self.sample_info.get("crs_display") or self.sample_info.get("crs") or "").strip()
            sample_input = str(self.sample_info.get("crs_input") or "").strip()
        override_crs = self.source_crs_override_edit.toPlainText().strip()
        if sample_crs:
            self.reproject_detected_crs_label.setText(f"输入投影：已识别为 {sample_crs}")
        elif override_crs:
            preview = override_crs.replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:117] + "..."
            self.reproject_detected_crs_label.setText(f"输入投影：文件未识别，将使用手动覆写 {preview}")
        else:
            self.reproject_detected_crs_label.setText("输入投影：未识别；如需重投影或参考对齐，请先填写源 CRS 覆写")
        self.reproject_use_input_crs_button.setEnabled(bool(sample_input))
        self.update_reproject_state()

    def apply_detected_crs_to_custom_target(self):
        if not self.sample_info:
            return
        crs_input = str(self.sample_info.get("crs_input") or "").strip()
        if not crs_input:
            QMessageBox.information(self, "无法填入", "当前输入影像没有可用的投影定义")
            return
        custom_index = self.reproject_target_combo.findData("custom")
        if custom_index >= 0:
            self.reproject_target_combo.setCurrentIndex(custom_index)
        self.reproject_custom_edit.setPlainText(crs_input)
        self.on_step_config_changed()

    def on_template_double_clicked(self, item: QListWidgetItem):
        self.add_step_by_key(str(item.data(Qt.UserRole)), self.pipeline_list.count())

    def add_step_by_key(self, step_key: str, row: int):
        existing_item = self.find_pipeline_item(step_key)
        if existing_item is not None:
            self.pipeline_list.setCurrentItem(existing_item)
            return

        row = max(0, min(row, self.pipeline_list.count()))
        item = QListWidgetItem()
        item.setData(Qt.UserRole, step_key)
        item.setSizeHint(QSize(0, 54))
        self.pipeline_list.insertItem(row, item)
        self.refresh_pipeline_items()
        self.pipeline_list.setCurrentItem(item)

    def remove_selected_step(self):
        row = self.pipeline_list.currentRow()
        if row < 0:
            return
        item = self.pipeline_list.takeItem(row)
        del item
        self.refresh_pipeline_items()
        if self.pipeline_list.count():
            self.pipeline_list.setCurrentRow(min(row, self.pipeline_list.count() - 1))
        else:
            self.on_current_step_changed(None, None)

    def clear_pipeline(self):
        self.pipeline_list.clear()
        self.refresh_pipeline_items()
        self.on_current_step_changed(None, None)

    def find_pipeline_item(self, step_key: str) -> QListWidgetItem | None:
        for index in range(self.pipeline_list.count()):
            item = self.pipeline_list.item(index)
            if item is not None and item.data(Qt.UserRole) == step_key:
                return item
        return None

    def on_current_step_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None):
        _ = previous
        if current is None:
            self.current_step_label.setText("当前步骤：未选择")
            self.step_stack.setCurrentWidget(self.empty_step_page)
            return

        step_key = str(current.data(Qt.UserRole))
        self.current_step_label.setText(f"当前步骤：{self.STEP_TITLES.get(step_key, step_key)}")
        page_mapping = {
            "clip": self.clip_page,
            "resample": self.resample_page,
            "reproject": self.reproject_page,
            "reclassify": self.reclassify_page,
        }
        self.step_stack.setCurrentWidget(page_mapping.get(step_key, self.empty_step_page))

    def refresh_pipeline_items(self):
        for index in range(self.pipeline_list.count()):
            item = self.pipeline_list.item(index)
            if item is None:
                continue
            step_key = str(item.data(Qt.UserRole))
            title = self.STEP_TITLES.get(step_key, step_key)
            summary = self.step_summary(step_key)
            item.setText(f"{index + 1}. {title}\n{summary}")
        if self.pipeline_list.currentItem() is None and self.pipeline_list.count():
            self.pipeline_list.setCurrentRow(0)

    def step_summary(self, step_key: str) -> str:
        if step_key == "clip":
            mode = self.clip_mode_combo.currentData()
            path = os.path.basename(self.clip_mask_path_edit.text().strip()) or "未设置"
            if mode == "reference":
                nodata_text = "按参考 NoData 掩膜" if self.clip_use_reference_nodata_check.isChecked() else "只对齐参考网格"
                trim_text = "，按有效数据范围裁剪" if self.clip_trim_nodata_check.isChecked() else ""
                return f"参考 tif：{path}，{nodata_text}{trim_text}"
            trim_text = "，按有效数据范围裁剪" if self.clip_trim_nodata_check.isChecked() else ""
            return f"矢量：{path}{trim_text}"

        if step_key == "resample":
            mode = self.resample_mode_combo.currentData()
            if mode == "reference":
                path = os.path.basename(self.resample_reference_edit.text().strip()) or "未设置"
                return f"参考 tif：{path}，{self.resample_method_combo.currentText()}"
            x_text = self.resample_resolution_x_edit.text().strip() or "?"
            y_text = self.resample_resolution_y_edit.text().strip() or "?"
            return f"手动分辨率：{x_text} x {y_text}，{self.resample_method_combo.currentText()}"

        if step_key == "reproject":
            target = self._compact_crs_text(self.current_reproject_target_text()) or "未设置"
            return f"目标投影：{target}，{self.reproject_method_combo.currentText()}"

        if step_key == "reclassify":
            rules_count = len(self.reclass_rule_rows)
            mode_text = self.reclass_mode_combo.currentText()
            fallback = "保留原值" if self.reclass_keep_unmatched_check.isChecked() else "未命中写 NoData"
            return f"{mode_text}，规则 {rules_count} 条，{fallback}"

        return ""

    def update_clip_state(self):
        is_reference = self.clip_mode_combo.currentData() == "reference"
        self.clip_use_reference_nodata_check.setEnabled(is_reference)
        self.clip_resampling_combo.setEnabled(is_reference)
        self.clip_all_touched_check.setEnabled(not is_reference)
        if is_reference:
            self.clip_hint_label.setText("参考 tif 模式会把输出对齐到参考网格，并可选按参考 NoData 掩膜。")
        else:
            self.clip_hint_label.setText("矢量模式会按 shp/geojson/gpkg 范围裁切，可选 all touched 和按有效数据范围裁剪。")
        self.on_step_config_changed()

    def update_resample_state(self):
        is_reference = self.resample_mode_combo.currentData() == "reference"
        self.resample_reference_edit.setEnabled(is_reference)
        self.resample_reference_button.setEnabled(is_reference)
        self.resample_reference_clear_button.setEnabled(is_reference)
        self.resample_resolution_x_edit.setEnabled(not is_reference)
        self.resample_resolution_y_edit.setEnabled(not is_reference)
        if is_reference:
            self.resample_hint_label.setText("参考 tif 模式会输出到参考栅格的尺寸、分辨率和投影。")
        else:
            self.resample_hint_label.setText("手动模式只改变当前坐标系下的分辨率，不主动切换投影。")
        self.on_step_config_changed()

    def update_reproject_state(self):
        is_custom = self.reproject_target_combo.currentData() == "custom"
        self.reproject_custom_edit.setEnabled(is_custom)
        self.reproject_use_input_crs_button.setEnabled(bool(self.sample_info and self.sample_info.get("crs_input")))
        target_text = self._compact_crs_text(self.current_reproject_target_text()) or "未设置"
        self.reproject_hint_label.setText(f"将把输入栅格重投影到 {target_text}。自定义模式支持 EPSG/PROJ/WKT。")
        self.on_step_config_changed()

    def update_reclassify_state(self):
        self._reset_reclass_rule_rows()
        if self.reclass_mode_combo.currentData() == "interval":
            self.reclass_rules_header.setText("每一类填写最小值、最大值和输出值。支持 -inf / inf。")
            self.reclass_hint_label.setText("区间格式为左闭右开 [min, max)。最后一类可把最大值设为 inf。")
        else:
            self.reclass_rules_header.setText("每一类填写原值和新值。")
            self.reclass_hint_label.setText("一对一映射会把命中的像元值替换为新值。")
        self.add_reclass_rule_row()
        self.on_step_config_changed()

    def add_reclass_rule_row(self):
        row_widgets = self._create_reclass_rule_row()
        self.reclass_rule_rows.append(row_widgets)
        self.reclass_rules_layout.addWidget(row_widgets["container"])
        self.on_step_config_changed()

    def remove_reclass_rule_row(self, row_widgets: dict[str, QWidget]):
        if row_widgets not in self.reclass_rule_rows:
            return
        if len(self.reclass_rule_rows) == 1:
            QMessageBox.information(self, "无法删除", "至少保留一条分类规则")
            return
        self.reclass_rule_rows.remove(row_widgets)
        container = row_widgets["container"]
        self.reclass_rules_layout.removeWidget(container)
        container.deleteLater()
        self.on_step_config_changed()

    def _reset_reclass_rule_rows(self):
        while self.reclass_rule_rows:
            row_widgets = self.reclass_rule_rows.pop()
            container = row_widgets["container"]
            self.reclass_rules_layout.removeWidget(container)
            container.deleteLater()

    def _create_reclass_rule_row(self) -> dict[str, QWidget]:
        row_container = QWidget()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        fields: dict[str, QWidget] = {"container": row_container}
        mode = self.reclass_mode_combo.currentData()
        if mode == "interval":
            field_specs = [
                ("min", "最小值", "如 -inf"),
                ("max", "最大值", "如 100 或 inf"),
                ("target", "输出值", "类别值"),
            ]
        else:
            field_specs = [
                ("source", "原值", "原像元值"),
                ("target", "新值", "输出类别值"),
            ]

        for key, title, placeholder in field_specs:
            edit = ModernLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.editingFinished.connect(self.on_step_config_changed)
            row_layout.addWidget(self._field_block(title, edit), 1)
            fields[key] = edit

        remove_button = TransparentPushButton("删除该类")
        remove_button.clicked.connect(lambda _checked=False, row=fields: self.remove_reclass_rule_row(row))
        row_layout.addWidget(remove_button)
        fields["remove"] = remove_button
        return fields

    def _build_reclass_rules_text(self) -> str:
        mode = self.reclass_mode_combo.currentData()
        lines: list[str] = []
        for index, row_widgets in enumerate(self.reclass_rule_rows, start=1):
            if mode == "interval":
                minimum = row_widgets["min"].text().strip()
                maximum = row_widgets["max"].text().strip()
                target = row_widgets["target"].text().strip()
                if not minimum or not maximum or not target:
                    raise ValueError(f"第 {index} 类的最小值、最大值、输出值必须填写完整")
                lines.append(f"{minimum},{maximum},{target}")
            else:
                source = row_widgets["source"].text().strip()
                target = row_widgets["target"].text().strip()
                if not source or not target:
                    raise ValueError(f"第 {index} 类的原值、新值必须填写完整")
                lines.append(f"{source},{target}")
        return "\n".join(lines)

    def _set_reclass_rule_rows_enabled(self, enabled: bool):
        for row_widgets in self.reclass_rule_rows:
            for widget in row_widgets.values():
                widget.setEnabled(enabled)

    @staticmethod
    def _compact_crs_text(text: str, limit: int = 80) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."

    def on_step_config_changed(self):
        if self._syncing_step_widgets:
            return
        self.refresh_pipeline_items()

    def current_reproject_target_text(self) -> str:
        target = self.reproject_target_combo.currentData()
        if target == "custom":
            return self.reproject_custom_edit.toPlainText().strip()
        return str(target or "").strip()

    def build_options(self) -> TifBatchWorkflowOptions:
        input_path = self.input_path_edit.text().strip()
        output_dir = self.output_dir_edit.text().strip()
        if not input_path:
            raise ValueError("请选择输入 tif 文件或目录")
        if not output_dir:
            raise ValueError("请选择输出目录")
        if self.pipeline_list.count() == 0:
            raise ValueError("请先把至少一个步骤拖到流程区")

        source_crs_override = self.source_crs_override_edit.toPlainText().strip() or None
        if source_crs_override:
            CRS.from_user_input(source_crs_override)

        steps = []
        for index in range(self.pipeline_list.count()):
            item = self.pipeline_list.item(index)
            if item is None:
                continue
            step_key = str(item.data(Qt.UserRole))
            if step_key == "clip":
                steps.append(self.build_clip_step())
            elif step_key == "resample":
                steps.append(self.build_resample_step())
            elif step_key == "reproject":
                steps.append(self.build_reproject_step())
            elif step_key == "reclassify":
                steps.append(self.build_reclassify_step())

        return TifBatchWorkflowOptions(
            input_path=input_path,
            output_dir=output_dir,
            recursive=self.recursive_check.isChecked(),
            source_crs_override=source_crs_override,
            output_suffix=self.output_suffix_edit.text().strip() or "workflow",
            steps=tuple(steps),
        )

    def build_clip_step(self) -> ClipStepConfig:
        mode = self.clip_mode_combo.currentData()
        mask_path = self.clip_mask_path_edit.text().strip()
        if not mask_path:
            raise ValueError("裁切步骤必须指定掩膜文件")
        if mode == "reference" and not mask_path.lower().endswith((".tif", ".tiff")):
            raise ValueError("参考掩膜必须是 tif/tiff")
        if mode == "shp" and not mask_path.lower().endswith((".shp", ".geojson", ".gpkg")):
            raise ValueError("矢量裁切仅支持 shp/geojson/gpkg")
        return ClipStepConfig(
            mode=mode,
            mask_path=mask_path,
            apply_reference_nodata=self.clip_use_reference_nodata_check.isChecked(),
            trim_nodata_border=self.clip_trim_nodata_check.isChecked(),
            all_touched=self.clip_all_touched_check.isChecked(),
            resampling=self.clip_resampling_combo.currentData(),
        )

    def build_resample_step(self) -> ResampleStepConfig:
        mode = self.resample_mode_combo.currentData()
        if mode == "reference":
            reference_path = self.resample_reference_edit.text().strip()
            if not reference_path:
                raise ValueError("参考重采样必须选择参考 tif")
            if not reference_path.lower().endswith((".tif", ".tiff")):
                raise ValueError("重采样参考文件必须是 tif/tiff")
            return ResampleStepConfig(
                mode=mode,
                reference_path=reference_path,
                resolution=None,
                resampling=self.resample_method_combo.currentData(),
            )

        res_x = TifWorkflowToolsService.parse_optional_float(self.resample_resolution_x_edit.text())
        res_y = TifWorkflowToolsService.parse_optional_float(self.resample_resolution_y_edit.text())
        if res_x is None or res_y is None:
            raise ValueError("手动重采样必须同时填写 X/Y 分辨率")
        if res_x <= 0 or res_y <= 0:
            raise ValueError("手动重采样分辨率必须大于 0")
        return ResampleStepConfig(
            mode=mode,
            reference_path=None,
            resolution=(res_x, res_y),
            resampling=self.resample_method_combo.currentData(),
        )

    def build_reproject_step(self) -> ReprojectStepConfig:
        target_crs = self.current_reproject_target_text()
        if not target_crs:
            raise ValueError("重投影步骤必须选择目标投影")
        CRS.from_user_input(target_crs)
        return ReprojectStepConfig(
            target_crs=target_crs,
            resampling=self.reproject_method_combo.currentData(),
        )

    def build_reclassify_step(self) -> ReclassifyStepConfig:
        rules_text = self._build_reclass_rules_text()
        if not rules_text.strip():
            raise ValueError("重分类步骤必须填写映射规则")
        output_nodata = TifWorkflowToolsService.parse_optional_float(self.reclass_output_nodata_edit.text())
        TifWorkflowToolsService._parse_reclass_rules(self.reclass_mode_combo.currentData(), rules_text)
        return ReclassifyStepConfig(
            mode=self.reclass_mode_combo.currentData(),
            rules_text=rules_text,
            keep_unmatched=self.reclass_keep_unmatched_check.isChecked(),
            output_nodata=output_nodata,
        )

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
        self.append_log("开始创建 TIF 批处理任务")
        self.set_form_enabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("状态：处理中")

        self.worker_thread = TifWorkflowBatchThread(options)
        self.worker_thread.progress_signal.connect(self.append_log)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()

    def cancel_processing(self):
        if self.worker_thread is None or not self.worker_thread.isRunning():
            return
        self.worker_thread.stop()
        self.append_log("已发送终止请求，等待当前文件完成")
        self.status_label.setText("状态：终止中")

    def append_log(self, message: str):
        self.log_output.append(str(message))

    def on_finished(self, result: TifBatchProcessResult):
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
        self._set_reclass_rule_rows_enabled(enabled)
        self.start_button.setEnabled(enabled)
        if enabled:
            self.update_clip_state()
            self.update_resample_state()
            self.update_reproject_state()

    @staticmethod
    def _clear_line_edit(widget: ModernLineEdit):
        widget.clear()

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

    def closeEvent(self, event: QCloseEvent):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait(2000)
        super().closeEvent(event)
