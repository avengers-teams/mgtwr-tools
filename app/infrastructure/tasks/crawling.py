from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from app.application.services.reptile import get_data_pre


class CrawlerThread(QThread):
    progress_signal = pyqtSignal(str)  # 任务进度信号
    finished_signal = pyqtSignal(str)  # 任务完成信号
    error_signal = pyqtSignal(str)  # 任务错误信号
    resource_signal = pyqtSignal(dict)  # 任务资源监控信号

    def __init__(self, selected_id, filepath, task_id, proxy_url=None):
        super().__init__()
        self.selected_id = selected_id
        self.filepath = filepath
        self.task_id = task_id  # 任务唯一标识
        self.proxy_url = proxy_url
        self.running = True  # 任务是否正在运行
        self.mutex = QMutex()  # 用于线程安全的互斥锁

    def run(self):
        self.progress_signal.emit(f"开始爬取数据，任务ID: {self.task_id}")
        try:
            if self.is_stopped():
                self.finished_signal.emit(f"任务已终止，任务ID: {self.task_id}")
                return

            get_data_pre(
                self.selected_id,
                self.filepath,
                progress_callback=self.progress_signal.emit,
                stop_callback=self.is_stopped,
                proxy_url=self.proxy_url,
            )

            if self.is_stopped():
                self.finished_signal.emit(f"任务已终止，任务ID: {self.task_id}")
            else:
                self.finished_signal.emit(f"数据爬取成功，任务ID: {self.task_id}")
        except InterruptedError:
            self.finished_signal.emit(f"任务已终止，任务ID: {self.task_id}")
        except Exception as e:
            self.error_signal.emit(f"爬取数据失败: {e}，任务ID: {self.task_id}")

    def stop(self):
        with QMutexLocker(self.mutex):
            self.running = False

    def is_stopped(self):
        with QMutexLocker(self.mutex):
            return not self.running




