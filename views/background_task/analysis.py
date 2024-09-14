import sys
from multiprocessing import Queue

from utils.data_analysis import DataAnalysis


class QueueWriter:
    """将子进程的 print 输出重定向到 multiprocessing.Queue 的类。"""
    def __init__(self, queue):
        self.queue = queue

    def write(self, message):
        if message.strip():  # 避免传递空行
            self.queue.put(message)

    def flush(self):
        pass  # 无需缓冲

def analysis_process(file_path, y_var, x_vars, coords, t_var, kernel, fixed, criterion, model, params, queue):
    """
    分析任务进程，实际执行分析并通过队列报告状态。
    queue: 用于传递子进程的状态和 print 输出
    """
    try:
        # 重定向 sys.stdout 到队列
        sys.stdout = QueueWriter(queue)
        print(f"开始 {model} 分析...")
        # 模拟分析任务
        analysis = DataAnalysis(file_path)
        analysis.set_variables(x_vars, [y_var], [t_var], coords)

        if model == 'GTWR':
            bw_min, bw_max, tau_min, tau_max = params['bw_min'], params['bw_max'], params['tau_min'], params['tau_max']
            analysis.gtwr(kernel=kernel, fixed=fixed, criterion=criterion,
                          bw_min=bw_min, bw_max=bw_max, tau_min=tau_min, tau_max=tau_max)
        elif model == 'MGTWR':
            multi_bw_min, multi_bw_max, multi_tau_min, multi_tau_max = params['multi_bw_min'], params['multi_bw_max'], params['multi_tau_min'], params['multi_tau_max']
            analysis.mgtwr(kernel=kernel, fixed=fixed, criterion=criterion,
                           multi_bw_min=[multi_bw_min], multi_bw_max=[multi_bw_max],
                           multi_tau_min=[multi_tau_min], multi_tau_max=[multi_tau_max])

        queue.put(f"{model} 分析完成")
    except Exception as e:
        queue.put(f"分析错误: {e}")
    finally:
        sys.stdout = sys.__stdout__  # 恢复标准输出
