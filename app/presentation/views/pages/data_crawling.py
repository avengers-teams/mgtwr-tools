import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.application.services.reptile import make_request, normalize_proxy_url
from app.infrastructure.tasks.crawling import CrawlerThread
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.combobox import ModernComboBox


class DirectorySelector(QWidget):
    def __init__(self, console_output, task_manager):
        super().__init__()
        self.console_output = console_output
        self.task_manager = task_manager
        self.index_history = []
        self.current_zb = None
        self.combo_boxes = []
        self.selected_terminal = None
        self.crawler_threads = {}
        self.filepath = None
        self.proxy_url = normalize_proxy_url("")
        self.root_index_loaded = False
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(14)

        title_label = QLabel("国家数据爬取")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 28px; font-weight: 700; color: #0f172a;")
        main_layout.addWidget(title_label)

        intro_label = QLabel("按层级选择指标后导入 Excel 文件，系统会在后台拉取最近 20 年数据并合并到表格中。")
        intro_label.setWordWrap(True)
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet("color: #64748b;")
        main_layout.addWidget(intro_label)

        selector_group = QGroupBox("指标选择")
        selector_layout = QVBoxLayout(selector_group)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.directory_layout = QVBoxLayout(self.scroll_content)
        self.directory_layout.setSpacing(10)
        self.directory_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setMinimumHeight(340)
        selector_layout.addWidget(self.scroll_area)

        self.selection_path_label = QLabel("当前路径：未选择")
        self.selection_path_label.setWordWrap(True)
        self.selection_path_label.setStyleSheet("color: #64748b;")
        selector_layout.addWidget(self.selection_path_label)
        main_layout.addWidget(selector_group)

        file_group = QGroupBox("文件设置")
        file_layout = QVBoxLayout(file_group)
        self.choose_file_button = ModernButton("选择 Excel 文件")
        self.choose_file_button.clicked.connect(self.open_file)
        file_layout.addWidget(self.choose_file_button)

        self.file_label = QLabel("目标文件：未选择")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(self.file_label)

        proxy_hint = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("HTTP 代理，例如 http://127.0.0.1:7890；留空则使用系统环境变量")
        if proxy_hint:
            self.proxy_input.setText(proxy_hint)
        self.proxy_input.editingFinished.connect(self.update_proxy_state)
        file_layout.addWidget(QLabel("HTTP 代理"))
        file_layout.addWidget(self.proxy_input)

        self.proxy_label = QLabel()
        self.proxy_label.setWordWrap(True)
        file_layout.addWidget(self.proxy_label)
        main_layout.addWidget(file_group)

        action_layout = QHBoxLayout()
        self.back_button = ModernButton('返回上一级')
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)
        action_layout.addWidget(self.back_button)

        self.refresh_button = ModernButton('刷新指标')
        self.refresh_button.clicked.connect(self.reload_index_tree)
        action_layout.addWidget(self.refresh_button)

        self.select_button = ModernButton('开始爬取')
        self.select_button.clicked.connect(self.select_directory)
        action_layout.addWidget(self.select_button)
        action_layout.addStretch(1)
        main_layout.addLayout(action_layout)

        self.result_label = QLabel("状态：等待选择指标")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("""
            background: #ffffff;
            border: 1px solid #d9e2ec;
            border-radius: 12px;
            padding: 12px;
            color: #334155;
        """)
        main_layout.addWidget(self.result_label)

        self.update_proxy_state()

    def ensure_index_loaded(self):
        if self.root_index_loaded:
            return

        self.root_index_loaded = self.get_index_valuecode(None)

    def clear_index_boxes(self):
        while self.combo_boxes:
            combo = self.combo_boxes.pop()
            self.directory_layout.removeWidget(combo._container_card)
            combo._container_card.deleteLater()
            combo.deleteLater()

        self.index_history.clear()
        self.current_zb = None
        self.selected_terminal = None
        self.back_button.setEnabled(False)
        self.update_selection_path()

    def reload_index_tree(self):
        self.update_proxy_state()
        self.clear_index_boxes()
        self.root_index_loaded = False
        self.result_label.setText("状态：正在刷新指标列表")
        self.console_output.append("正在刷新指标列表...")
        self.ensure_index_loaded()

    def open_file(self):
        self.filepath, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel Files (*.xlsx)")
        if not self.filepath:
            self.console_output.append("未选择 Excel 文件")
            return

        self.file_label.setText(f"目标文件：{self.filepath}")
        self.console_output.append(f"选择的文件: {self.filepath}")
        QMessageBox.information(self, "文件加载", "文件加载成功")

    def get_index_valuecode(self, zb, selected_name=None):
        self.update_proxy_state()
        params = {
            'id': zb,
            'dbcode': 'fsnd',
            'wdcode': 'zb',
            'm': 'getTree',
        }
        self.console_output.append(f"正在获取指标数据: {params}")
        data = make_request(params=params, proxy_url=self.proxy_url)

        if data:
            child_items = self.extract_child_items(data, parent_id=zb)
            if child_items:
                self.selected_terminal = None
                self.current_zb = zb
                self.add_combo_box(child_items)
                self.back_button.setEnabled(len(self.index_history) > 0)
                self.console_output.append("获取数据成功，已添加新的下拉菜单")
                return True
            else:
                self.selected_terminal = {"id": zb, "name": selected_name or str(zb)}
                self.result_label.setText(f"状态：已选择最终指标 {self.selected_terminal['name']}")
                self.console_output.append(f"已到最后一级，最终指标: {self.selected_terminal['name']} (ID: {zb})")
                return True
        else:
            self.result_label.setText("状态：获取数据失败，请稍后重试")
            self.console_output.append("获取数据失败")
            return False

        return False

    def extract_child_items(self, data, parent_id=None):
        child_items = []
        seen_ids = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            item_name = item.get("name") or item.get("cname")
            if item_id is None or not item_name:
                continue
            if parent_id is not None and str(item_id) == str(parent_id):
                continue
            if str(item_id) in seen_ids:
                continue
            seen_ids.add(str(item_id))
            child_items.append(item)
        return child_items

    def is_terminal_item(self, item_meta):
        if not isinstance(item_meta, dict):
            return False

        if "isParent" in item_meta:
            value = item_meta.get("isParent")
            if isinstance(value, str):
                value = value.lower() == "true"
            return not bool(value)

        if "hasChild" in item_meta:
            value = item_meta.get("hasChild")
            if isinstance(value, str):
                value = value.lower() == "true"
            return not bool(value)

        for key in ("isLeaf", "leaf", "isleaf"):
            if key in item_meta:
                value = item_meta.get(key)
                if isinstance(value, str):
                    value = value.lower() == "true"
                return bool(value)

        return False

    def add_combo_box(self, items):
        combo = ModernComboBox()
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setMinimumWidth(520)
        combo.addItem("请选择")
        for item in items:
            combo.addItem(item.get("name") or item.get("cname"), userData=item)
        combo.currentIndexChanged.connect(self.on_combo_changed)

        level = len(self.combo_boxes) + 1
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #d7dfd1;
                border-radius: 12px;
                padding: 8px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        level_label = QLabel(f"第 {level} 级指标")
        level_label.setStyleSheet("font-weight: 700; color: #4e6650;")
        card_layout.addWidget(level_label)
        card_layout.addWidget(combo)

        combo._container_card = card
        self.directory_layout.addWidget(card)
        self.combo_boxes.append(combo)
        self.index_history.append((self.current_zb, items))
        self.update_selection_path()

    def on_combo_changed(self, index):
        if index <= 0:
            return

        combo = self.sender()
        if combo not in self.combo_boxes:
            return

        selected_item = combo.itemData(index)
        if not isinstance(selected_item, dict):
            self.result_label.setText("状态：当前指标数据无效，请重新选择")
            self.console_output.append("当前指标缺少有效元数据，已阻止继续下钻")
            return

        selected_id = selected_item.get("id") if isinstance(selected_item, dict) else selected_item
        selected_name = combo.currentText()
        if selected_id in (None, ""):
            self.result_label.setText("状态：当前指标缺少有效 ID，请重新选择")
            self.console_output.append(f"当前指标 {selected_name} 缺少有效 ID")
            return

        combo_index = self.combo_boxes.index(combo)

        for i in range(len(self.combo_boxes) - 1, combo_index, -1):
            self.directory_layout.removeWidget(self.combo_boxes[i]._container_card)
            self.combo_boxes[i]._container_card.deleteLater()
            self.combo_boxes[i].deleteLater()
            self.combo_boxes.pop()
            self.index_history.pop()

        self.update_selection_path()
        if self.is_terminal_item(selected_item):
            self.selected_terminal = {"id": selected_id, "name": selected_name}
            self.result_label.setText(f"状态：已选择最终指标 {selected_name}")
            self.console_output.append(f"已到最后一级，最终指标: {selected_name} (ID: {selected_id})")
            return

        self.get_index_valuecode(selected_id, selected_name=selected_name)

    def go_back(self):
        if not self.index_history or not self.combo_boxes:
            return

        self.index_history.pop()
        combo = self.combo_boxes.pop()
        self.directory_layout.removeWidget(combo._container_card)
        combo._container_card.deleteLater()
        combo.deleteLater()

        if self.index_history:
            previous_zb, _ = self.index_history[-1]
            self.current_zb = previous_zb
        else:
            self.current_zb = None
            self.selected_terminal = None
            self.get_index_valuecode(None)

        self.selected_terminal = None
        self.back_button.setEnabled(len(self.index_history) > 0)
        self.result_label.setText("状态：已返回上一级")
        self.console_output.append("返回上一级")
        self.update_selection_path()

    def update_console_output(self, message):
        self.console_output.append(message)
        self.result_label.setText(f"状态：{message}")

    def update_task_console_output(self, task_id, message):
        self.console_output.append_message(message, task_id=task_id)
        self.result_label.setText(f"状态：{message}")

    def update_selection_path(self):
        selected_names = []
        for combo in self.combo_boxes:
            index = combo.currentIndex()
            if index > 0:
                selected_names.append(combo.currentText())

        if selected_names:
            self.selection_path_label.setText(f"当前路径：{'  >  '.join(selected_names)}")
        else:
            self.selection_path_label.setText("当前路径：未选择")

    def update_proxy_state(self):
        self.proxy_url = normalize_proxy_url(self.proxy_input.text())
        if self.proxy_url:
            self.proxy_label.setText(f"当前代理：{self.proxy_url}")
        else:
            self.proxy_label.setText("当前代理：未显式设置，使用直连或系统环境代理")

    def start_crawler_task(self, selected_id, filepath):
        task_id = self.task_manager.create_task_id()
        crawler_thread = CrawlerThread(selected_id, filepath, task_id, proxy_url=self.proxy_url)
        self.crawler_threads[task_id] = crawler_thread
        self.console_output.add_task_console(task_id, f"爬取 #{task_id}")

        crawler_thread.progress_signal.connect(lambda message, task_id=task_id: self.update_task_console_output(task_id, message))
        crawler_thread.finished_signal.connect(lambda message, task_id=task_id: self.on_crawler_finished(task_id, message))
        crawler_thread.error_signal.connect(lambda message, task_id=task_id: self.on_crawler_error(task_id, message))
        crawler_thread.finished_signal.connect(lambda _message, task_id=task_id: self.cleanup_thread(task_id))
        crawler_thread.error_signal.connect(lambda _message, task_id=task_id: self.cleanup_thread(task_id))

        self.task_manager.add_task(
            task_id,
            crawler_thread,
            '线程',
            name='数据爬取',
            cancel_callback=crawler_thread.stop,
        )
        crawler_thread.start()
        self.console_output.activate_task_console(task_id)

    def cleanup_thread(self, task_id):
        thread = self.crawler_threads.pop(task_id, None)
        if thread is not None:
            thread.wait(500)

    def on_crawler_finished(self, task_id, message):
        self.console_output.append_message(message, task_id=task_id)
        self.result_label.setText(f"状态：{message}")
        status = "已终止" if "终止" in message else "已完成"
        self.task_manager.update_task_status(task_id, status)

    def on_crawler_error(self, task_id, error_message):
        self.console_output.append_message(error_message, task_id=task_id)
        self.result_label.setText(f"状态：{error_message}")
        self.task_manager.update_task_status(task_id, "出错")

    def select_directory(self):
        if not self.filepath:
            QMessageBox.warning(self, "缺少文件", "请先选择需要写入的 Excel 文件")
            self.console_output.append("请先选择 Excel 文件")
            return

        if not self.combo_boxes:
            self.result_label.setText("状态：没有可用的选择")
            self.console_output.append("没有可用的选择")
            return

        last_combo = self.combo_boxes[-1]
        selected_index = last_combo.currentIndex()
        if selected_index <= 0:
            self.result_label.setText("状态：请在最后一个下拉菜单中进行选择")
            self.console_output.append("请在最后一个下拉菜单中进行选择")
            return

        selected_name = last_combo.currentText()
        selected_item = last_combo.itemData(selected_index)
        if not isinstance(selected_item, dict):
            self.result_label.setText("状态：当前指标数据无效，请重新选择")
            self.console_output.append("当前指标缺少有效元数据，无法开始爬取")
            return

        selected_id = selected_item.get("id")
        if selected_id in (None, ""):
            self.result_label.setText("状态：当前指标缺少有效 ID，请重新选择")
            self.console_output.append(f"当前指标 {selected_name} 缺少有效 ID，无法开始爬取")
            return

        self.result_label.setText(f"状态：已选择 {selected_name}，开始爬取")
        self.console_output.append(f"已选择: {selected_name} (ID: {selected_id})")
        self.start_crawler_task(selected_id, self.filepath)

