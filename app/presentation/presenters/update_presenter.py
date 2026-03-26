from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QMessageBox, QWidget

from app.application.dto.update import UpdateCheckResult, UpdateStatus
from app.application.services.update_service import UpdateService


class _UpdateCheckWorker(QObject):
    finished = pyqtSignal(object, bool)

    def __init__(self, update_service: UpdateService, interactive: bool):
        super().__init__()
        self.update_service = update_service
        self.interactive = interactive

    def run(self):
        status = self.update_service.fetch_update_status()
        self.finished.emit(status, self.interactive)


class UpdatePresenter(QObject):
    check_started = pyqtSignal()
    status_updated = pyqtSignal(object)

    def __init__(self, parent: QWidget, update_service: UpdateService):
        super().__init__(parent)
        self.parent_widget = parent
        self.update_service = update_service
        self._thread: QThread | None = None
        self._worker: _UpdateCheckWorker | None = None
        self._interactive = False

    def schedule_check(self, delay_ms: int = 0):
        QTimer.singleShot(max(0, int(delay_ms)), self.start_silent_check)

    def start_silent_check(self):
        self._start_check(interactive=False)

    def start_manual_check(self):
        self._start_check(interactive=True)

    def _start_check(self, interactive: bool):
        if self._thread is not None:
            return

        self._interactive = interactive
        self.check_started.emit()
        self._thread = QThread(self)
        self._worker = _UpdateCheckWorker(self.update_service, interactive=interactive)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._handle_result)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def open_release_page(self, release_url: str | None):
        if release_url:
            QDesktopServices.openUrl(QUrl(release_url))

    def _handle_result(self, status: UpdateStatus, interactive: bool):
        self.status_updated.emit(status)

        if status.update_available and status.latest_version and status.release_url:
            self._ask_to_update(
                UpdateCheckResult(
                    current_version=status.current_version,
                    latest_version=status.latest_version,
                    release_url=status.release_url,
                    title=status.title,
                )
            )
            return

        if interactive:
            if status.error_message:
                QMessageBox.warning(
                    self.parent_widget,
                    "检查更新失败",
                    status.error_message,
                )
            else:
                QMessageBox.information(
                    self.parent_widget,
                    "检查完成",
                    f"当前已是最新版本：{status.current_version}",
                )

    def _ask_to_update(self, result: UpdateCheckResult):
        title_suffix = f"\n发布标题：{result.title}" if result.title else ""
        message = (
            "检测到新版本。\n\n"
            f"当前版本：{result.current_version}\n"
            f"最新版本：{result.latest_version}"
            f"{title_suffix}\n\n"
            "是否前往下载更新？"
        )
        answer = QMessageBox.question(
            self.parent_widget,
            "发现新版本",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.open_release_page(result.release_url)

    def _cleanup(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        self._interactive = False
