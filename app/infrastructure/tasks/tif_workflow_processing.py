from __future__ import annotations

from PyQt5.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from app.application.services.tif_workflow_tools import (
    TifBatchProcessResult,
    TifBatchWorkflowOptions,
    TifWorkflowToolsService,
)


class TifWorkflowBatchThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, options: TifBatchWorkflowOptions):
        super().__init__()
        self.options = options
        self._running = True
        self._mutex = QMutex()

    def run(self):
        try:
            result = TifWorkflowToolsService.process_batch(
                self.options,
                progress_callback=self.progress_signal.emit,
                stop_callback=self.is_stopped,
            )
            if self.is_stopped():
                self.progress_signal.emit("任务已终止")
            self.finished_signal.emit(result)
        except InterruptedError:
            self.progress_signal.emit("任务已终止")
            self.finished_signal.emit(
                TifBatchProcessResult(
                    processed_files=0,
                    failed_files=0,
                    generated_outputs=[],
                    failures=[],
                )
            )
        except Exception as exc:
            self.error_signal.emit(str(exc))

    def stop(self):
        with QMutexLocker(self._mutex):
            self._running = False

    def is_stopped(self) -> bool:
        with QMutexLocker(self._mutex):
            return not self._running
