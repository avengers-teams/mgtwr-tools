import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon, FluentWindow, NavigationItemPosition, TransparentPushButton

from views.components.console import TaskConsoleManager
from views.components.fluent_surface import FrostedPanel
from views.pages.MGTWR_analysis import MGRWRAnalysisPage
from views.pages.data_crawling import DirectorySelector
from views.pages.data_preparation import DataGenerationPage
from views.pages.data_validation.index import AdditionalWindows
from views.pages.data_visualization import DataVisualizationPage
from views.pages.significance_analysis import SignificanceAnalysisPage
from views.pages.task_manager import TaskManager
from views.theme import make_scrollable


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.route_widgets = {}
        self._nav_expanded_once = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("多功能数据分析工具")
        screen = QApplication.primaryScreen().availableGeometry()
        window_width = max(1260, min(1680, int(screen.width() * 0.9)))
        window_height = max(820, min(1080, int(screen.height() * 0.9)))
        self.resize(window_width, window_height)
        self.setMinimumSize(1180, 760)
        self.setCustomBackgroundColor("#f3f6fb", "#20242b")
        self.navigationInterface.setExpandWidth(232)
        self.navigationInterface.setMinimumExpandWidth(1100)
        self.navigationInterface.setAcrylicEnabled(True)

        self.console_output = TaskConsoleManager()
        self.task_manager = TaskManager(self.console_output)
        self.data_gen_page = DataGenerationPage(self.console_output)
        self.dir_select_page = DirectorySelector(self.console_output, self.task_manager)
        self.mgrwr_page = MGRWRAnalysisPage(self.console_output, self.task_manager)
        self.data_visualization_page = DataVisualizationPage(self.console_output)
        self.significance_analysis_page = SignificanceAnalysisPage(self.console_output)
        self.additional_page = AdditionalWindows()

        self.build_workspace()
        self.init_navigation()
        self.stackedWidget.currentChanged.connect(self.on_current_page_changed)
        self.navigationInterface.expand(useAni=False)
        self._nav_expanded_once = True

        sys.stdout = self.console_output
        sys.stderr = self.console_output

    def build_workspace(self):
        self.widgetLayout.removeWidget(self.stackedWidget)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 56, 16, 16)
        content_layout.setSpacing(12)

        splitter = QSplitter(Qt.Vertical, content_widget)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.stackedWidget)
        splitter.addWidget(self.build_console_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 280])

        content_layout.addWidget(splitter)
        self.widgetLayout.addWidget(content_widget)

    def build_console_panel(self):
        panel = FrostedPanel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 18)
        layout.setSpacing(12)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title = CaptionLabel("多任务控制台")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        clear_button = TransparentPushButton("清空当前")
        clear_button.setMinimumHeight(30)
        clear_button.clicked.connect(self.console_output.clear)
        save_button = TransparentPushButton("保存当前")
        save_button.setMinimumHeight(30)
        save_button.clicked.connect(self.console_output.save)
        header_layout.addWidget(clear_button)
        header_layout.addWidget(save_button)

        layout.addWidget(header)
        layout.addWidget(self.console_output)
        return panel

    def init_navigation(self):
        self.register_page(self.data_gen_page, "data_generation", "数据生成", FluentIcon.DOCUMENT)
        self.register_page(self.dir_select_page, "data_crawling", "国家数据爬取", FluentIcon.GLOBE)
        self.register_page(self.mgrwr_page, "model_analysis", "模型分析", FluentIcon.ROBOT)
        self.register_page(self.data_visualization_page, "data_visualization", "数据可视化", FluentIcon.PIE_SINGLE)
        self.register_page(self.significance_analysis_page, "significance_analysis", "显著性分析", FluentIcon.FLAG)

        self.navigationInterface.addSeparator()

        self.register_page(
            self.task_manager,
            "task_manager",
            "任务管理",
            FluentIcon.SYNC,
            position=NavigationItemPosition.BOTTOM,
        )
        self.register_page(
            self.additional_page,
            "additional_tools",
            "其他功能",
            FluentIcon.DEVELOPER_TOOLS,
            position=NavigationItemPosition.BOTTOM,
        )

        self.switch_to_route("data_generation")

    def register_page(self, page_widget, route_key, title, icon, position=NavigationItemPosition.TOP):
        page = make_scrollable(page_widget, margins=(20, 20, 20, 20))
        page.setObjectName(route_key)
        self.route_widgets[route_key] = page
        self.addSubInterface(page, icon, title, position=position, isTransparent=True)

    def switch_to_route(self, route_key):
        page = self.route_widgets.get(route_key)
        if page is not None:
            self.switchTo(page)

    def on_current_page_changed(self, index):
        widget = self.stackedWidget.widget(index)
        if widget is None:
            return

        if widget.objectName() == "data_crawling":
            self.dir_select_page.ensure_index_loaded()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._nav_expanded_once:
            self.navigationInterface.expand(useAni=False)
            self._nav_expanded_once = True

    def __del__(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
