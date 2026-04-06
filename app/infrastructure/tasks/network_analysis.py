from __future__ import annotations

import sys
import traceback
import warnings


class QueueWriter:
    def __init__(self, queue, task_id):
        self.queue = queue
        self.task_id = task_id

    def write(self, message):
        if message:
            self.queue.put({"task_id": self.task_id, "kind": "log", "message": str(message)})

    def flush(self):
        pass


class QueueWarningDispatcher:
    def __init__(self, queue, task_id):
        self.queue = queue
        self.task_id = task_id

    def __call__(self, message, category, filename, lineno, file=None, line=None):
        warning_text = warnings.formatwarning(message, category, filename, lineno, line).rstrip()
        self.queue.put({"task_id": self.task_id, "kind": "warning", "message": warning_text})


class QueueProgressReporter:
    def __init__(self, queue, task_id):
        self.queue = queue
        self.task_id = task_id

    def emit(self, message: str):
        self.queue.put({"task_id": self.task_id, "kind": "progress", "message": str(message)})

    def __call__(self, message: str):
        self.emit(message)


def network_metrics_process(task_id, options, queue):
    from app.application.services.network_analysis_service import NetworkAnalysisService

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    original_showwarning = warnings.showwarning

    try:
        sys.stdout = QueueWriter(queue, task_id)
        sys.stderr = QueueWriter(queue, task_id)
        warnings.showwarning = QueueWarningDispatcher(queue, task_id)
        warnings.simplefilter("always")

        queue.put({"task_id": task_id, "status": "运行中", "message": f"任务 {task_id} 开始执行网络指标计算"})
        service = NetworkAnalysisService()
        reporter = QueueProgressReporter(queue, task_id)
        result = service.run_metrics(options, progress_callback=reporter.emit)
        queue.put(
            {
                "task_id": task_id,
                "status": "已完成",
                "message": result.message,
                "kind": "result",
                "result": {
                    "status": result.status,
                    "message": result.message,
                    "output_path": result.output_path,
                    "metrics_csv": result.metrics_csv,
                    "summary_csv": result.summary_csv,
                    "batch_manifest": result.batch_manifest,
                },
            }
        )
    except Exception as exc:
        queue.put({"task_id": task_id, "status": "出错", "message": str(exc)})
        traceback.print_exc()
        raise
    finally:
        warnings.showwarning = original_showwarning
        sys.stdout = original_stdout
        sys.stderr = original_stderr
