from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NetworkMetricsOptions:
    mode: str = "single"
    compare_npz: str | None = None
    window_root: str | None = None
    out_dir: str | None = None
    matrix_filename: str = "compare_matrix.npz"
    manifest_filename: str = "windows_manifest.csv"
    batch_manifest_filename: str = "network_metrics_manifest.csv"
    metrics_filename: str = "network_metrics.csv"
    summary_filename: str = "network_summary.csv"
    threshold: float = 0.0
    n_sectors: int = 8
    skip_existing: bool = False
    fail_fast: bool = False
    workers: int = 0
    template_tif: str | None = None
    export_tiff: bool = False
    tiff_output_dirname: str = "tiff_metrics"


@dataclass
class NetworkMetricsExecutionResult:
    status: str
    message: str
    output_path: str
    metrics_csv: str | None = None
    summary_csv: str | None = None
    batch_manifest: str | None = None


@dataclass
class NetworkCatalogLoadOptions:
    window_root: str
    metrics_filename: str = "network_metrics.csv"
    summary_filename: str = "network_summary.csv"
    threshold: float = 0.0
    n_sectors: int = 8
    force_metrics: bool = False
