import sys
import warnings

from utils.data_analysis import DataAnalysis


class QueueWriter:
    """将子进程的 print 输出重定向到 multiprocessing.Queue 的类。"""

    def __init__(self, queue, task_id):
        self.queue = queue
        self.task_id = task_id

    def write(self, message):
        if message:
            self.queue.put({"task_id": self.task_id, "kind": "log", "message": message})

    def flush(self):
        """flush 方法可以留空或传递，因为 queue 本身是无缓冲的。"""
        pass


class QueueWarningDispatcher:
    def __init__(self, queue, task_id):
        self.queue = queue
        self.task_id = task_id

    def __call__(self, message, category, filename, lineno, file=None, line=None):
        warning_text = warnings.formatwarning(message, category, filename, lineno, line).rstrip()
        self.queue.put({"task_id": self.task_id, "kind": "warning", "message": warning_text})


def analysis_process(task_id, file_path, output_path, y_var, x_vars, coords, t_var, kernel, fixed, criterion, model,
                     params, queue):
    """
    分析任务进程，实际执行分析并通过队列报告状态。
    queue: 用于传递子进程的状态和 print 输出
    """
    try:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_showwarning = warnings.showwarning

        # 重定向 sys.stdout / sys.stderr 到队列
        sys.stdout = QueueWriter(queue, task_id)
        sys.stderr = QueueWriter(queue, task_id)
        warnings.showwarning = QueueWarningDispatcher(queue, task_id)
        warnings.simplefilter("always")

        queue.put({"task_id": task_id, "status": "运行中", "message": f"任务 {task_id} 开始执行 {model} 分析"})
        print(f"开始 {model} 分析...")
        analysis = DataAnalysis(file_path, output_path)
        time_columns = [t_var] if t_var else []
        analysis.set_variables(
            x_vars,
            [y_var],
            time_columns,
            coords,
            missing_strategy=params.get("missing_strategy", "drop"),
            missing_fill_value=params.get("missing_fill_value"),
        )
        analysis.run_model(model=model, kernel=kernel, fixed=fixed, criterion=criterion, params=params)

        print(f"{model} 分析完成")
        queue.put({"task_id": task_id, "status": "已完成", "message": f"任务 {task_id} 已完成"})
    except Exception as e:
        queue.put({"task_id": task_id, "status": "出错", "message": f"任务 {task_id} 执行失败: {e}"})
        print(f"分析错误: {e}")
        raise
    finally:
        warnings.showwarning = original_showwarning
        sys.stdout = original_stdout
        sys.stderr = original_stderr
