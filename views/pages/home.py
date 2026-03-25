from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, HyperlinkButton

from views.components.button import ModernButton
from views.components.fluent_surface import ActionPanel, FrostedPanel, PageHeader, StatPill


class HomePage(QWidget):
    def __init__(self, navigate_callback, parent=None):
        super().__init__(parent)
        self.navigate_callback = navigate_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        hero = FrostedPanel(hero=True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(26, 24, 26, 24)
        hero_layout.setSpacing(18)

        hero_layout.addWidget(PageHeader(
            "数据工作台",
            "以 Microsoft Fluent Design 重新组织的数据生成、抓取、分析与任务协同界面。",
            badge_text="Fluent Workspace",
        ))

        pill_row = QGridLayout()
        pill_row.setHorizontalSpacing(12)
        pill_row.setVerticalSpacing(12)
        pill_row.addWidget(StatPill("数据准备", "01"), 0, 0)
        pill_row.addWidget(StatPill("指标抓取", "02"), 0, 1)
        pill_row.addWidget(StatPill("模型分析", "03"), 0, 2)
        pill_row.addWidget(StatPill("任务控制台", "04"), 0, 3)
        hero_layout.addLayout(pill_row)

        quick_row = QGridLayout()
        quick_row.setHorizontalSpacing(14)
        quick_row.setVerticalSpacing(14)

        quick_row.addWidget(self.create_action_panel(
            "生成基础数据",
            "从模板或自定义底表快速生成多年份省级样本，作为后续流程的起点。",
            "打开数据生成",
            "data_generation",
            "rgba(228, 239, 255, 0.78)",
        ), 0, 0)

        quick_row.addWidget(self.create_action_panel(
            "抓取国家指标",
            "以多级指标树挑选统计局指标，后台任务独立执行并把日志写入专属控制台。",
            "打开国家数据爬取",
            "data_crawling",
            "rgba(232, 245, 239, 0.78)",
        ), 0, 1)

        quick_row.addWidget(self.create_action_panel(
            "配置模型分析",
            "支持 GWR、MGWR、GTWR、MGTWR，全参数配置并支持线程数与结果导出。",
            "打开模型分析",
            "model_analysis",
            "rgba(239, 241, 255, 0.78)",
        ), 1, 0)

        quick_row.addWidget(self.create_action_panel(
            "查看任务控制台",
            "任务状态与多任务控制台解耦，日志不会抢焦点，关闭后也能从任务管理重新打开。",
            "打开控制台",
            "console_workspace",
            "rgba(242, 238, 255, 0.78)",
        ), 1, 1)

        layout.addWidget(hero)
        layout.addLayout(quick_row)

        note = FrostedPanel()
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(20, 18, 20, 18)
        note_layout.setSpacing(10)
        note_layout.addWidget(PageHeader("设计说明", "当前界面重点模拟 Windows 11 / Microsoft Store 风格的分层、毛玻璃与卡片节奏。"))

        tips = BodyLabel("如果你要继续推进，我下一步可以把数据生成、国家数据爬取、模型分析三页也进一步改成更完整的官方示例式布局。")
        tips.setWordWrap(True)
        note_layout.addWidget(tips)

        docs = HyperlinkButton("https://qfluentwidgets.com", "Fluent Widgets")
        docs.setIcon(FluentIcon.LINK)
        note_layout.addWidget(docs, 0)
        layout.addWidget(note)
        layout.addStretch(1)

    def create_action_panel(self, title, description, button_text, route_key, accent):
        panel = ActionPanel(title, description, accent=accent)
        open_button = ModernButton(button_text)
        open_button.clicked.connect(lambda: self.navigate_callback(route_key))
        panel.body_layout.addWidget(open_button)
        return panel
