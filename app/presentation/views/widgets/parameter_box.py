import os

from PyQt5.QtWidgets import QFormLayout, QGroupBox

from app.presentation.views.widgets.input import ModernCheckBox, ModernLineEdit, ModernSpinBox


def _create_line_edit(tooltip="", placeholder="", text=""):
    input_box = ModernLineEdit()
    if tooltip:
        input_box.setToolTip(tooltip)
    if placeholder:
        input_box.setPlaceholderText(placeholder)
    if text:
        input_box.setText(text)
    return input_box


def _create_spin_box(minimum=0, maximum=999999, value=0, tooltip=""):
    input_box = ModernSpinBox()
    input_box.setRange(minimum, maximum)
    input_box.setValue(value)
    if tooltip:
        input_box.setToolTip(tooltip)
    return input_box


def _create_check_box(text="", checked=False, tooltip=""):
    input_box = ModernCheckBox(text)
    input_box.setChecked(checked)
    if tooltip:
        input_box.setToolTip(tooltip)
    return input_box


def _add_form_group(param_layout, title, rows):
    group = QGroupBox(title)
    form = QFormLayout(group)
    for label, widget in rows:
        form.addRow(label, widget)
    param_layout.addWidget(group)


def create_model_param_box(model, param_layout):
    widgets = {}
    cpu_count = max(1, os.cpu_count() or 1)

    widgets["thread"] = _create_spin_box(
        minimum=1,
        maximum=max(64, cpu_count),
        value=min(4, cpu_count),
        tooltip="并行线程数，过大不一定更快，通常建议 1 到 CPU 核心数之间",
    )
    widgets["constant"] = _create_check_box("包含截距项", checked=True, tooltip="对应模型中的 constant 参数")
    widgets["convert"] = _create_check_box(
        "将经纬度转换为平面坐标",
        checked=False,
        tooltip="当坐标列是真实经纬度时可启用，对应 convert 参数",
    )
    widgets["verbose"] = _create_check_box("输出搜索过程", checked=True, tooltip="对应 search 中的 verbose 参数")
    widgets["time_cost"] = _create_check_box("输出耗时", checked=True, tooltip="对应 search 中的 time_cost 参数")

    _add_form_group(
        param_layout,
        "通用设置",
        [
            ("线程数", widgets["thread"]),
            ("", widgets["constant"]),
            ("", widgets["convert"]),
            ("", widgets["verbose"]),
            ("", widgets["time_cost"]),
        ],
    )

    if model == "GWR":
        _build_gwr_fields(param_layout, widgets)
    elif model == "MGWR":
        _build_mgwr_fields(param_layout, widgets)
    elif model == "GTWR":
        _build_gtwr_fields(param_layout, widgets)
    elif model == "MGTWR":
        _build_mgtwr_fields(param_layout, widgets)

    return widgets


def _build_gwr_fields(param_layout, widgets):
    widgets["tol"] = _create_line_edit(text="1.0e-6", tooltip="搜索收敛公差")
    widgets["max_iter"] = _create_spin_box(minimum=1, maximum=100000, value=200, tooltip="最大迭代次数")
    widgets["bw_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="带宽小数位数")
    _add_form_group(
        param_layout,
        "搜索控制",
        [
            ("收敛公差", widgets["tol"]),
            ("最大迭代次数", widgets["max_iter"]),
            ("带宽精度", widgets["bw_decimal"]),
        ],
    )

    widgets["bw_min"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最小值")
    widgets["bw_max"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最大值")
    _add_form_group(
        param_layout,
        "带宽范围",
        [
            ("带宽最小值", widgets["bw_min"]),
            ("带宽最大值", widgets["bw_max"]),
        ],
    )


def _build_mgwr_fields(param_layout, widgets):
    widgets["tol"] = _create_line_edit(text="1.0e-6", tooltip="带宽搜索收敛公差")
    widgets["tol_multi"] = _create_line_edit(text="1.0e-5", tooltip="多带宽回归收敛公差")
    widgets["bw_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="带宽小数位数")
    widgets["bws_same_times"] = _create_spin_box(
        minimum=1,
        maximum=100,
        value=5,
        tooltip="带宽连续多少次不变后停止回代",
    )
    widgets["rss_score"] = _create_check_box("使用 RSS 作为回代评分", checked=False)
    _add_form_group(
        param_layout,
        "搜索控制",
        [
            ("收敛公差", widgets["tol"]),
            ("多带宽收敛公差", widgets["tol_multi"]),
            ("带宽精度", widgets["bw_decimal"]),
            ("稳定次数阈值", widgets["bws_same_times"]),
            ("", widgets["rss_score"]),
        ],
    )

    widgets["bw_min"] = _create_line_edit(placeholder="可留空", tooltip="全局搜索带宽最小值")
    widgets["bw_max"] = _create_line_edit(placeholder="可留空", tooltip="全局搜索带宽最大值")
    widgets["init_bw"] = _create_line_edit(placeholder="可留空", tooltip="初始化带宽，为空则先从 GWR 派生")
    widgets["multi_bw_min"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最小带宽")
    widgets["multi_bw_max"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最大带宽")
    _add_form_group(
        param_layout,
        "带宽设置",
        [
            ("带宽最小值", widgets["bw_min"]),
            ("带宽最大值", widgets["bw_max"]),
            ("初始带宽", widgets["init_bw"]),
            ("多带宽最小值", widgets["multi_bw_min"]),
            ("多带宽最大值", widgets["multi_bw_max"]),
        ],
    )

    widgets["n_chunks"] = _create_spin_box(minimum=1, maximum=256, value=1, tooltip="推断阶段分块数，越大越省内存")
    widgets["skip_calculate"] = _create_check_box(
        "跳过 CCT/ENP 等推断计算",
        checked=False,
        tooltip="更省时间和内存，但会少部分统计量",
    )
    _add_form_group(
        param_layout,
        "拟合阶段",
        [
            ("分块数", widgets["n_chunks"]),
            ("", widgets["skip_calculate"]),
        ],
    )


def _build_gtwr_fields(param_layout, widgets):
    widgets["tol"] = _create_line_edit(text="1.0e-6", tooltip="搜索收敛公差")
    widgets["max_iter"] = _create_spin_box(minimum=1, maximum=100000, value=200, tooltip="最大迭代次数")
    widgets["bw_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="带宽小数位数")
    widgets["tau_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="时空尺度小数位数")
    _add_form_group(
        param_layout,
        "搜索控制",
        [
            ("收敛公差", widgets["tol"]),
            ("最大迭代次数", widgets["max_iter"]),
            ("带宽精度", widgets["bw_decimal"]),
            ("时空尺度精度", widgets["tau_decimal"]),
        ],
    )

    widgets["bw_min"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最小值")
    widgets["bw_max"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最大值")
    widgets["tau_min"] = _create_line_edit(placeholder="可留空", tooltip="时空尺度搜索最小值")
    widgets["tau_max"] = _create_line_edit(placeholder="可留空", tooltip="时空尺度搜索最大值")
    _add_form_group(
        param_layout,
        "时空范围",
        [
            ("带宽最小值", widgets["bw_min"]),
            ("带宽最大值", widgets["bw_max"]),
            ("时空尺度最小值", widgets["tau_min"]),
            ("时空尺度最大值", widgets["tau_max"]),
        ],
    )


def _build_mgtwr_fields(param_layout, widgets):
    widgets["tol"] = _create_line_edit(text="1.0e-6", tooltip="带宽与时空尺度搜索收敛公差")
    widgets["tol_multi"] = _create_line_edit(text="1.0e-5", tooltip="多带宽回代收敛公差")
    widgets["bw_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="带宽小数位数")
    widgets["tau_decimal"] = _create_spin_box(minimum=0, maximum=10, value=1, tooltip="时空尺度小数位数")
    widgets["rss_score"] = _create_check_box("使用 RSS 作为回代评分", checked=False)
    _add_form_group(
        param_layout,
        "搜索控制",
        [
            ("收敛公差", widgets["tol"]),
            ("多带宽收敛公差", widgets["tol_multi"]),
            ("带宽精度", widgets["bw_decimal"]),
            ("时空尺度精度", widgets["tau_decimal"]),
            ("", widgets["rss_score"]),
        ],
    )

    widgets["bw_min"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最小值")
    widgets["bw_max"] = _create_line_edit(placeholder="可留空", tooltip="带宽搜索最大值")
    widgets["tau_min"] = _create_line_edit(placeholder="可留空", tooltip="时空尺度搜索最小值")
    widgets["tau_max"] = _create_line_edit(placeholder="可留空", tooltip="时空尺度搜索最大值")
    widgets["init_bw"] = _create_line_edit(placeholder="可留空", tooltip="初始带宽，为空则从 GTWR 派生")
    widgets["init_tau"] = _create_line_edit(placeholder="可留空", tooltip="初始时空尺度，为空则从 GTWR 派生")
    _add_form_group(
        param_layout,
        "单一搜索范围",
        [
            ("带宽最小值", widgets["bw_min"]),
            ("带宽最大值", widgets["bw_max"]),
            ("时空尺度最小值", widgets["tau_min"]),
            ("时空尺度最大值", widgets["tau_max"]),
            ("初始带宽", widgets["init_bw"]),
            ("初始时空尺度", widgets["init_tau"]),
        ],
    )

    widgets["multi_bw_min"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最小带宽")
    widgets["multi_bw_max"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最大带宽")
    widgets["multi_tau_min"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最小时空尺度")
    widgets["multi_tau_max"] = _create_line_edit(placeholder="单个值或逗号分隔多个值", tooltip="每个变量的最大时空尺度")
    _add_form_group(
        param_layout,
        "多尺度范围",
        [
            ("多带宽最小值", widgets["multi_bw_min"]),
            ("多带宽最大值", widgets["multi_bw_max"]),
            ("多时空尺度最小值", widgets["multi_tau_min"]),
            ("多时空尺度最大值", widgets["multi_tau_max"]),
        ],
    )

    widgets["n_chunks"] = _create_spin_box(minimum=1, maximum=256, value=1, tooltip="推断阶段分块数，越大越省内存")
    widgets["skip_calculate"] = _create_check_box(
        "跳过 CCT/ENP 等推断计算",
        checked=False,
        tooltip="更省时间和内存，但会少部分统计量",
    )
    _add_form_group(
        param_layout,
        "拟合阶段",
        [
            ("分块数", widgets["n_chunks"]),
            ("", widgets["skip_calculate"]),
        ],
    )

