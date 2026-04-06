from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

try:
    import geopandas as gpd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_es_matrix_dataframe(npz_path: Union[str, Path]) -> pd.DataFrame:
    npz_path = Path(npz_path)
    data = np.load(npz_path, allow_pickle=True)

    if "data" in data:
        matrix = data["data"].astype(np.float32, copy=False)
    elif "matrix" in data:
        matrix = data["matrix"].astype(np.float32, copy=False)
    else:
        raise KeyError(f"{npz_path} 中未找到 'data' 或 'matrix' 键。")

    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"{npz_path} 中的矩阵必须是方阵，当前形状为 {matrix.shape}。")

    if "columns" in data:
        node_names = list(data["columns"])
    elif "node_names" in data:
        node_names = list(data["node_names"])
    else:
        node_names = [f"node_{i}" for i in range(matrix.shape[0])]

    if len(node_names) != matrix.shape[0]:
        raise ValueError(
            f"{npz_path} 的节点数与矩阵维度不一致: len(columns)={len(node_names)}, matrix.shape={matrix.shape}。"
        )

    return pd.DataFrame(matrix, index=node_names, columns=node_names)


def discover_window_dirs(window_root: Union[str, Path], manifest_filename: str = "windows_manifest.csv") -> list[Path]:
    window_root = Path(window_root)
    manifest_path = window_root / manifest_filename
    window_dirs: list[Path] = []

    if manifest_path.exists():
        with manifest_path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                raw_dir = row.get("window_dir", "").strip()
                if not raw_dir:
                    continue
                window_dir = Path(raw_dir)
                if not window_dir.is_absolute():
                    parts = window_dir.parts
                    if parts and parts[0] == window_root.name:
                        stripped_dir = Path(*parts[1:]) if len(parts) > 1 else Path()
                    else:
                        stripped_dir = window_dir

                    candidates = [
                        manifest_path.parent / window_dir,
                        window_root / window_dir,
                        window_root.parent / window_dir,
                    ]

                    if stripped_dir != window_dir:
                        candidates.extend(
                            [
                                manifest_path.parent / stripped_dir,
                                window_root / stripped_dir,
                                window_root.parent / stripped_dir,
                            ]
                        )

                    for candidate in candidates:
                        if candidate.exists():
                            window_dir = candidate
                            break
                window_dirs.append(window_dir)
    else:
        window_dirs = sorted(path for path in window_root.glob("window_*") if path.is_dir())

    if not window_dirs:
        raise ValueError(f"在 {window_root} 下未找到任何窗口目录。")

    return window_dirs


def write_metrics_outputs(
    target_dir: Union[str, Path],
    metrics_df: pd.DataFrame,
    summary: dict,
    metrics_filename: str = "network_metrics.csv",
    summary_filename: str = "network_summary.csv",
) -> tuple[Path, Path]:
    target_dir = Path(target_dir)
    ensure_dir(target_dir)
    metrics_path = target_dir / metrics_filename
    summary_path = target_dir / summary_filename
    metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    pd.DataFrame([summary]).to_csv(summary_path, index=False, encoding="utf-8-sig")
    return metrics_path, summary_path


def parse_window_label(window_dir: Path) -> str:
    name = window_dir.name
    if not name.startswith("window_"):
        return name
    parts = name.split("_")
    if len(parts) < 3:
        return name
    return f"{parts[1]}-{parts[2]}"


def load_window_catalog(
    window_root: Union[str, Path],
    metrics_filename: str,
    summary_filename: str,
) -> pd.DataFrame:
    window_root = Path(window_root)
    manifest_path = window_root / "windows_manifest.csv"
    window_dirs = discover_window_dirs(window_root)
    manifest_df = pd.read_csv(manifest_path, encoding="utf-8-sig") if manifest_path.exists() else None

    records = []
    for idx, window_dir in enumerate(window_dirs, start=1):
        metrics_path = window_dir / metrics_filename
        summary_path = window_dir / summary_filename
        metrics_df = pd.read_csv(metrics_path, encoding="utf-8-sig")
        summary_df = pd.read_csv(summary_path, encoding="utf-8-sig")
        row = {
            "window_id": idx,
            "window_dir": str(window_dir.resolve()),
            "window_name": window_dir.name,
            "window_label": parse_window_label(window_dir),
            "metrics_path": str(metrics_path.resolve()),
            "summary_path": str(summary_path.resolve()),
            "metrics_df": metrics_df,
            "summary_df": summary_df,
        }

        if manifest_df is not None and "window_dir" in manifest_df.columns:
            matches = manifest_df[manifest_df["window_dir"].astype(str).str.endswith(window_dir.name)]
            if not matches.empty:
                match = matches.iloc[0]
                row["window_id"] = int(match.get("window_id", idx))
                row["window_start"] = pd.to_datetime(match.get("window_start"))
                row["window_end"] = pd.to_datetime(match.get("window_end"))
                n_timestamps = match.get("n_timestamps", np.nan)
                row["n_timestamps"] = int(n_timestamps) if pd.notna(n_timestamps) else np.nan

        if "window_start" not in row:
            parts = window_dir.name.split("_")
            if len(parts) >= 3:
                row["window_start"] = pd.to_datetime(parts[1], format="%Y%m%d", errors="coerce")
                row["window_end"] = pd.to_datetime(parts[2], format="%Y%m%d", errors="coerce")
            else:
                row["window_start"] = pd.NaT
                row["window_end"] = pd.NaT

        start = row["window_start"]
        end = row["window_end"]
        row["window_center"] = start + (end - start) / 2 if pd.notna(start) and pd.notna(end) else pd.NaT
        row.update(summary_df.iloc[0].to_dict())
        records.append(row)

    return pd.DataFrame(records).sort_values(["window_start", "window_id"]).reset_index(drop=True)


def load_label_points(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None

    labels = pd.read_csv(path, encoding="utf-8-sig")
    required = {"name", "longitude", "latitude"}
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"标注 CSV 缺少必需列: {sorted(missing)}")
    return labels.copy()


def load_vector_layer(path: Optional[str]) -> Optional["gpd.GeoDataFrame"]:
    if not path:
        return None
    if not HAS_GEOPANDAS:
        raise ImportError("边界绘制需要 geopandas。")

    gdf = gpd.read_file(path)
    if gdf.empty:
        return None
    if gdf.crs is not None and str(gdf.crs) != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def build_label_points_from_vector(
    gdf: Optional["gpd.GeoDataFrame"],
    label_column: Optional[str],
) -> Optional[pd.DataFrame]:
    if gdf is None or gdf.empty or not label_column:
        return None
    if label_column not in gdf.columns:
        raise ValueError(f"矢量图层中不存在标签字段: {label_column}")

    label_frame = gdf[[label_column, "geometry"]].copy()
    label_frame = label_frame[label_frame.geometry.notna()]
    if label_frame.empty:
        return None

    points = label_frame.geometry.representative_point()
    result = pd.DataFrame(
        {
            "name": label_frame[label_column].astype(str),
            "longitude": points.x.astype(float),
            "latitude": points.y.astype(float),
        }
    )
    result = result.replace([np.inf, -np.inf], np.nan).dropna(subset=["longitude", "latitude"])
    return result if not result.empty else None
