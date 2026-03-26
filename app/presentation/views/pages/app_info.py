from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel, TitleLabel, TransparentPushButton

from app.application.dto.update import UpdateStatus
from app.core.config import (
    APP_DESCRIPTION,
    APP_TITLE,
    GITHUB_RELEASES_URL,
    GITHUB_REPOSITORY_URL,
    app_version,
    build_release_tag_url,
)
from app.presentation.presenters.update_presenter import UpdatePresenter
from app.presentation.views.widgets.button import ModernButton
from app.presentation.views.widgets.fluent_surface import FrostedPanel, PageHeader


class InfoCard(FrostedPanel):
    def __init__(self, title: str, value: str = "--", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)

        self.value_label = TitleLabel(value)
        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("color: #5b6b84;")
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class DetailRow(QWidget):
    def __init__(self, label: str, value: str = "--", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel(label)
        title.setMinimumWidth(72)
        title.setStyleSheet("color: #5b6b84;")
        layout.addWidget(title, 0)

        self.value_label = BodyLabel(value)
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.value_label, 1)

    def set_value(self, value: str):
        self.value_label.setText(value)


class AppInfoPage(QWidget):
    def __init__(self, presenter: UpdatePresenter):
        super().__init__()
        self.presenter = presenter
        self.init_ui()
        self.bind_presenter()
        self.refresh_local_version()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "应用信息",
                "查看当前版本、仓库发布信息，并在需要时手动检查更新。",
            )
        )

        overview_panel = FrostedPanel()
        overview_layout = QVBoxLayout(overview_panel)
        overview_layout.setContentsMargins(20, 18, 20, 18)
        overview_layout.setSpacing(10)
        overview_layout.addWidget(TitleLabel(APP_TITLE))

        description = SubtitleLabel(APP_DESCRIPTION)
        description.setWordWrap(True)
        overview_layout.addWidget(description)

        repo_label = BodyLabel(f"仓库：{GITHUB_REPOSITORY_URL}")
        repo_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        repo_label.setWordWrap(True)
        overview_layout.addWidget(repo_label)

        repo_actions = QHBoxLayout()
        repo_actions.setSpacing(10)
        self.open_repo_button = TransparentPushButton("打开仓库")
        self.open_release_button = TransparentPushButton("打开发布页")
        repo_actions.addWidget(self.open_repo_button)
        repo_actions.addWidget(self.open_release_button)
        repo_actions.addStretch(1)
        overview_layout.addLayout(repo_actions)
        layout.addWidget(overview_panel)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.current_version_card = InfoCard("当前版本", app_version())
        self.remote_version_card = InfoCard("远端版本", "未检查")
        self.update_state_card = InfoCard("更新状态", "尚未检查")
        cards_row.addWidget(self.current_version_card)
        cards_row.addWidget(self.remote_version_card)
        cards_row.addWidget(self.update_state_card)
        layout.addLayout(cards_row)

        details_panel = FrostedPanel()
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(20, 18, 20, 18)
        details_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        header_row.addWidget(SubtitleLabel("版本详情"))
        header_row.addStretch(1)
        self.check_update_button = ModernButton("检查更新")
        self.open_latest_button = TransparentPushButton("打开最新发布")
        header_row.addWidget(self.check_update_button)
        header_row.addWidget(self.open_latest_button)
        details_layout.addLayout(header_row)

        self.status_label = BodyLabel("尚未检查远端版本。")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setStyleSheet("color: #5b6b84;")
        details_layout.addWidget(self.status_label)

        self.current_version_value = DetailRow("当前版本", app_version())
        self.remote_version_value = DetailRow("远端版本", "--")
        self.release_title_value = DetailRow("发布标题", "--")
        self.release_url_value = DetailRow("发布地址", build_release_tag_url(None))
        details_layout.addWidget(self.current_version_value)
        details_layout.addWidget(self.remote_version_value)
        details_layout.addWidget(self.release_title_value)
        details_layout.addWidget(self.release_url_value)

        layout.addWidget(details_panel)
        layout.addStretch(1)

    def bind_presenter(self):
        self.check_update_button.clicked.connect(self.presenter.start_manual_check)
        self.open_repo_button.clicked.connect(lambda: self.presenter.open_release_page(GITHUB_REPOSITORY_URL))
        self.open_release_button.clicked.connect(lambda: self.presenter.open_release_page(GITHUB_RELEASES_URL))
        self.open_latest_button.clicked.connect(self.open_latest_release)
        self.presenter.check_started.connect(self.on_check_started)
        self.presenter.status_updated.connect(self.apply_update_status)

    def refresh_local_version(self):
        version = app_version()
        self.current_version_card.set_value(version)
        self.current_version_value.set_value(version)

    def on_check_started(self):
        self.check_update_button.setEnabled(False)
        self.check_update_button.setText("检查中...")
        self.update_state_card.set_value("检查中")
        self.status_label.setText("正在连接远端仓库并获取最新发布信息...")

    def apply_update_status(self, status: UpdateStatus):
        self.refresh_local_version()
        self.check_update_button.setEnabled(True)
        self.check_update_button.setText("检查更新")

        if status.latest_version:
            self.remote_version_card.set_value(status.latest_version)
            self.remote_version_value.set_value(status.latest_version)
        else:
            self.remote_version_card.set_value("获取失败")
            self.remote_version_value.set_value("--")

        self.release_title_value.set_value(status.title or "--")
        self.release_url_value.set_value(status.release_url or build_release_tag_url(status.latest_version))

        if status.error_message:
            self.update_state_card.set_value("检查失败")
            self.status_label.setText(status.error_message)
            return

        if status.update_available:
            self.update_state_card.set_value("可更新")
            self.status_label.setText(
                f"检测到新版本 {status.latest_version}，当前版本为 {status.current_version}。"
            )
            return

        self.update_state_card.set_value("已最新")
        self.status_label.setText(f"当前版本 {status.current_version} 已是最新版本。")

    def open_latest_release(self):
        target_url = self.release_url_value.value_label.text().strip() or build_release_tag_url(None)
        self.presenter.open_release_page(target_url)
