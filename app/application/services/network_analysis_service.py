from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from app.application.dto.network_analysis import (
    NetworkCatalogLoadOptions,
    NetworkMetricsExecutionResult,
    NetworkMetricsOptions,
)
from app.domain.network_analysis.metrics import ESNetwork, build_network_summary, build_node_metrics_dataframe
from app.infrastructure.repositories.network_analysis_repository import (
    build_label_points_from_vector,
    discover_window_dirs,
    ensure_dir,
    load_es_matrix_dataframe,
    load_label_points,
    load_vector_layer,
    load_window_catalog,
    write_metrics_outputs,
)


ProgressCallback = Callable[[str], None] | None


def _emit(progress_callback: ProgressCallback, message: str) -> None:
    if callable(progress_callback):
        progress_callback(message)


def _run_single_metrics_job(job: dict) -> dict:
    compare_npz = Path(job["compare_npz"])
    target_dir = compare_npz.parent if not job.get("out_dir") else Path(job["out_dir"])
    ensure_dir(target_dir)

    metrics_path = target_dir / job["metrics_filename"]
    summary_path = target_dir / job["summary_filename"]
    tiff_dir = target_dir / job["tiff_output_dirname"]
    tiff_ready = (not job["export_tiff"]) or tiff_dir.exists()
    if job["skip_existing"] and metrics_path.exists() and summary_path.exists() and tiff_ready:
        return {
            "status": "skipped",
            "window_dir": str(target_dir.resolve()),
            "compare_npz": str(compare_npz.resolve()),
            "metrics_csv": str(metrics_path.resolve()),
            "summary_csv": str(summary_path.resolve()),
            "tiff_dir": str(tiff_dir.resolve()) if job["export_tiff"] else "",
        }

    es_df = load_es_matrix_dataframe(compare_npz)
    network = ESNetwork(es_df, threshold=job["threshold"])
    metrics_df = build_node_metrics_dataframe(network=network, n_sectors=job["n_sectors"])
    summary = build_network_summary(network=network, compare_npz=str(compare_npz.resolve()), metrics_df=metrics_df)
    try:
        written_metrics_path, written_summary_path = write_metrics_outputs(
            target_dir=target_dir,
            metrics_df=metrics_df,
            summary=summary,
            metrics_filename=job["metrics_filename"],
            summary_filename=job["summary_filename"],
        )
    except PermissionError:
        if metrics_path.exists() and summary_path.exists():
            written_metrics_path = metrics_path
            written_summary_path = summary_path
        else:
            raise

    if job["export_tiff"]:
        template_tif = job.get("template_tif")
        if not template_tif:
            raise ValueError("export_tiff=True 时必须提供 template_tif。")
        network.all_extended_metrics_to_tiff(
            template_path=str(template_tif),
            output_dir=str(tiff_dir),
            n_sectors=job["n_sectors"],
        )

    return {
        "status": "done",
        "window_dir": str(target_dir.resolve()),
        "compare_npz": str(compare_npz.resolve()),
        "metrics_csv": str(written_metrics_path.resolve()),
        "summary_csv": str(written_summary_path.resolve()),
        "tiff_dir": str(tiff_dir.resolve()) if job["export_tiff"] else "",
    }


class NetworkAnalysisService:
    def run_metrics(
        self,
        options: NetworkMetricsOptions,
        progress_callback: ProgressCallback = None,
    ) -> NetworkMetricsExecutionResult:
        if options.mode == "single":
            result = self.compute_single_metrics(options=options, progress_callback=progress_callback)
            return NetworkMetricsExecutionResult(
                status=result["status"],
                message=f"网络指标已输出到 {result['window_dir']}",
                output_path=result["window_dir"],
                metrics_csv=result["metrics_csv"],
                summary_csv=result["summary_csv"],
            )

        batch_manifest = self.compute_window_root_metrics(options=options, progress_callback=progress_callback)
        return NetworkMetricsExecutionResult(
            status="done",
            message=f"批处理完成，清单已保存到 {batch_manifest}",
            output_path=str(batch_manifest),
            batch_manifest=str(batch_manifest),
        )

    def compute_single_metrics(
        self,
        options: NetworkMetricsOptions,
        progress_callback: ProgressCallback = None,
    ) -> dict:
        if not options.compare_npz:
            raise ValueError("单窗口模式必须提供 compare_matrix.npz。")

        _emit(progress_callback, f"开始分析单窗口矩阵: {options.compare_npz}")
        result = _run_single_metrics_job(
            {
                "compare_npz": options.compare_npz,
                "out_dir": options.out_dir,
                "threshold": options.threshold,
                "n_sectors": options.n_sectors,
                "metrics_filename": options.metrics_filename,
                "summary_filename": options.summary_filename,
                "skip_existing": options.skip_existing,
                "template_tif": options.template_tif,
                "export_tiff": options.export_tiff,
                "tiff_output_dirname": options.tiff_output_dirname,
            }
        )
        _emit(progress_callback, f"完成: {result['metrics_csv']}")
        return result

    def compute_window_root_metrics(
        self,
        options: NetworkMetricsOptions,
        progress_callback: ProgressCallback = None,
    ) -> Path:
        if not options.window_root:
            raise ValueError("批量模式必须提供滑动窗口根目录。")

        window_root = Path(options.window_root)
        ensure_dir(window_root)
        window_dirs = discover_window_dirs(window_root, manifest_filename=options.manifest_filename)

        manifest_rows = []
        pending_jobs = []
        for idx, window_dir in enumerate(window_dirs, start=1):
            compare_npz = window_dir / options.matrix_filename
            if not compare_npz.exists():
                manifest_rows.append(
                    {
                        "window_id": idx,
                        "window_dir": str(window_dir.resolve()),
                        "status": "missing_compare_npz",
                        "compare_npz": str(compare_npz.resolve()),
                        "metrics_csv": "",
                        "summary_csv": "",
                        "tiff_dir": "",
                        "error": f"missing {options.matrix_filename}",
                    }
                )
                _emit(progress_callback, f"[skip {idx}/{len(window_dirs)}] 缺少 {compare_npz}")
                if options.fail_fast:
                    raise FileNotFoundError(compare_npz)
                continue

            pending_jobs.append(
                (
                    idx,
                    window_dir,
                    {
                        "compare_npz": str(compare_npz),
                        "out_dir": str(window_dir),
                        "threshold": options.threshold,
                        "n_sectors": options.n_sectors,
                        "metrics_filename": options.metrics_filename,
                        "summary_filename": options.summary_filename,
                        "skip_existing": options.skip_existing,
                        "template_tif": options.template_tif,
                        "export_tiff": options.export_tiff,
                        "tiff_output_dirname": options.tiff_output_dirname,
                    },
                )
            )

        if options.workers and options.workers > 0 and len(pending_jobs) > 1:
            with ProcessPoolExecutor(max_workers=options.workers) as executor:
                future_map = {
                    executor.submit(_run_single_metrics_job, job): (idx, window_dir)
                    for idx, window_dir, job in pending_jobs
                }
                for future in as_completed(future_map):
                    idx, window_dir = future_map[future]
                    try:
                        result = future.result()
                        manifest_rows.append(
                            {
                                "window_id": idx,
                                "window_dir": result["window_dir"],
                                "status": result["status"],
                                "compare_npz": result["compare_npz"],
                                "metrics_csv": result["metrics_csv"],
                                "summary_csv": result["summary_csv"],
                                "tiff_dir": result.get("tiff_dir", ""),
                                "error": "",
                            }
                        )
                        _emit(progress_callback, f"[done {idx}/{len(window_dirs)}] {window_dir}")
                    except Exception as exc:
                        manifest_rows.append(
                            {
                                "window_id": idx,
                                "window_dir": str(window_dir.resolve()),
                                "status": "error",
                                "compare_npz": str((window_dir / options.matrix_filename).resolve()),
                                "metrics_csv": "",
                                "summary_csv": "",
                                "tiff_dir": "",
                                "error": str(exc),
                            }
                        )
                        _emit(progress_callback, f"[error {idx}/{len(window_dirs)}] {window_dir}: {exc}")
                        if options.fail_fast:
                            raise
        else:
            for idx, window_dir, job in pending_jobs:
                try:
                    result = _run_single_metrics_job(job)
                    manifest_rows.append(
                        {
                            "window_id": idx,
                            "window_dir": result["window_dir"],
                            "status": result["status"],
                            "compare_npz": result["compare_npz"],
                            "metrics_csv": result["metrics_csv"],
                            "summary_csv": result["summary_csv"],
                            "tiff_dir": result.get("tiff_dir", ""),
                            "error": "",
                        }
                    )
                    _emit(progress_callback, f"[done {idx}/{len(window_dirs)}] {window_dir}")
                except Exception as exc:
                    manifest_rows.append(
                        {
                            "window_id": idx,
                            "window_dir": str(window_dir.resolve()),
                            "status": "error",
                            "compare_npz": str((window_dir / options.matrix_filename).resolve()),
                            "metrics_csv": "",
                            "summary_csv": "",
                            "tiff_dir": "",
                            "error": str(exc),
                        }
                    )
                    _emit(progress_callback, f"[error {idx}/{len(window_dirs)}] {window_dir}: {exc}")
                    if options.fail_fast:
                        raise

        batch_manifest_path = window_root / options.batch_manifest_filename
        manifest_df = pd.DataFrame(manifest_rows).sort_values("window_id")
        try:
            manifest_df.to_csv(batch_manifest_path, index=False, encoding="utf-8-sig")
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback_manifest_path = batch_manifest_path.with_name(
                f"{batch_manifest_path.stem}_{timestamp}{batch_manifest_path.suffix}"
            )
            manifest_df.to_csv(fallback_manifest_path, index=False, encoding="utf-8-sig")
            batch_manifest_path = fallback_manifest_path
            _emit(progress_callback, f"默认清单文件被占用，已改存为: {batch_manifest_path}")
        _emit(progress_callback, f"批处理清单已保存: {batch_manifest_path}")
        return batch_manifest_path

    def load_catalog(
        self,
        options: NetworkCatalogLoadOptions,
        progress_callback: ProgressCallback = None,
    ) -> pd.DataFrame:
        window_root = Path(options.window_root)
        window_dirs = discover_window_dirs(window_root)

        for index, window_dir in enumerate(window_dirs, start=1):
            metrics_path = window_dir / options.metrics_filename
            summary_path = window_dir / options.summary_filename
            if options.force_metrics or not metrics_path.exists() or not summary_path.exists():
                compare_npz = window_dir / "compare_matrix.npz"
                if not compare_npz.exists():
                    raise FileNotFoundError(f"窗口目录缺少 compare_matrix.npz: {compare_npz}")

                _emit(progress_callback, f"[prepare {index}/{len(window_dirs)}] 生成 {window_dir.name} 的网络指标")
                _run_single_metrics_job(
                    {
                        "compare_npz": str(compare_npz),
                        "out_dir": str(window_dir),
                        "threshold": options.threshold,
                        "n_sectors": options.n_sectors,
                        "metrics_filename": options.metrics_filename,
                        "summary_filename": options.summary_filename,
                        "skip_existing": False,
                        "template_tif": None,
                        "export_tiff": False,
                        "tiff_output_dirname": "tiff_metrics",
                    }
                )

        catalog = load_window_catalog(
            window_root=window_root,
            metrics_filename=options.metrics_filename,
            summary_filename=options.summary_filename,
        )
        _emit(progress_callback, f"已加载 {len(catalog)} 个窗口的网络指标。")
        return catalog

    @staticmethod
    def load_vector_layer(path: str | None):
        return load_vector_layer(path)

    @staticmethod
    def load_label_points(path: str | None):
        return load_label_points(path)

    @staticmethod
    def build_label_points_from_vector(gdf, label_column: str | None):
        return build_label_points_from_vector(gdf, label_column)
