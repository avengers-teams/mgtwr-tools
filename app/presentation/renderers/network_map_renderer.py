from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Dict, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap, Normalize, TwoSlopeNorm
from matplotlib.patches import Circle, Polygon
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.axes_grid1 import make_axes_locatable

try:
    import seaborn as sns
except ImportError:
    sns = None


DISTANCE_CMAP = LinearSegmentedColormap.from_list(
    "distance_custom",
    ["#6a5ad8", "#6f86e4", "#67b8eb", "#9fd5c7", "#d6cfa0", "#f0b468", "#ff7b45", "#ff2e1f"],
)
STRENGTH_CMAP = LinearSegmentedColormap.from_list(
    "strength_custom",
    ["#fff200", "#ffc300", "#ff9800", "#ff6d00", "#ff3d00", "#ff1200", "#e60000"],
)

METRIC_CONFIG = {
    "in_degree": {"label": "In-Strength", "cmap": STRENGTH_CMAP, "center": None, "kind": "continuous"},
    "out_degree": {"label": "Out-Strength", "cmap": STRENGTH_CMAP, "center": None, "kind": "continuous"},
    "degree_diff": {"label": "In-Out Strength Difference", "cmap": "RdBu_r", "center": 0.0, "kind": "continuous"},
    "strength_in": {"label": "Weighted In-Strength", "cmap": STRENGTH_CMAP, "center": None, "kind": "continuous"},
    "strength_out": {"label": "Weighted Out-Strength", "cmap": STRENGTH_CMAP, "center": None, "kind": "continuous"},
    "propagation_distance_in_km": {
        "label": "Inbound Propagation Distance (km)",
        "cmap": DISTANCE_CMAP,
        "center": None,
        "kind": "continuous",
    },
    "propagation_distance_out_km": {
        "label": "Outbound Propagation Distance (km)",
        "cmap": DISTANCE_CMAP,
        "center": None,
        "kind": "continuous",
    },
    "dominant_in_direction": {"label": "Dominant Inbound Direction", "kind": "direction"},
    "dominant_out_direction": {"label": "Dominant Outbound Direction", "kind": "direction"},
    "dominant_diff_direction": {"label": "Dominant In-Out Difference Direction", "kind": "direction"},
}
METRIC_PAIR_CONFIG = {
    "strength": {"title": "Strength", "metrics": ("in_degree", "out_degree")},
    "distance": {"title": "Propagation Distance", "metrics": ("propagation_distance_in_km", "propagation_distance_out_km")},
    "direction": {"title": "Dominant Direction", "metrics": ("dominant_in_direction", "dominant_out_direction")},
}
DIRECTION_LABELS = ["ENE", "NNE", "NNW", "WNW", "WSW", "SSW", "SSE", "ESE"]
DIRECTION_COLORS = ["#fee8b6", "#d5ff62", "#d9d9d9", "#8dd164", "#f2a900", "#f47679", "#fff79a", "#92b6d5"]


def resolve_preferred_font_family() -> list[str]:
    preferred_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "PingFang SC",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected_fonts = [font for font in preferred_fonts if font in available_fonts]
    return selected_fonts or ["DejaVu Sans"]


def configure_style() -> None:
    font_families = resolve_preferred_font_family()
    if sns is not None:
        sns.set_theme(
            style="white",
            context="paper",
            rc={
                "font.family": "sans-serif",
                "font.sans-serif": font_families,
                "axes.unicode_minus": False,
            },
        )
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "figure.facecolor": "white",
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
            "font.family": "sans-serif",
            "font.sans-serif": font_families,
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "axes.facecolor": "white",
            "axes.linewidth": 0.8,
            "axes.labelsize": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "semibold",
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "grid.linewidth": 0.45,
            "grid.alpha": 0.65,
            "legend.fontsize": 10,
        }
    )


def available_metric_pairs() -> list[tuple[str, str]]:
    return [(pair_id, config["title"]) for pair_id, config in METRIC_PAIR_CONFIG.items()]


def available_metrics() -> list[tuple[str, str]]:
    return [(metric, metric_label(metric)) for metric in METRIC_CONFIG]


def resolve_metric_pair(pair_id: str) -> Dict[str, object]:
    if pair_id not in METRIC_PAIR_CONFIG:
        raise ValueError(f"未知指标对: {pair_id}")
    config = METRIC_PAIR_CONFIG[pair_id]
    return {"pair_id": pair_id, "title": config["title"], "metrics": config["metrics"]}


def sanitize_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in text)


def coordinate_edges(coords: np.ndarray) -> np.ndarray:
    coords = np.asarray(coords, dtype=float)
    if coords.size == 1:
        return np.array([coords[0] - 0.5, coords[0] + 0.5], dtype=float)
    diffs = np.diff(coords)
    midpoints = coords[:-1] + diffs / 2.0
    return np.concatenate(([coords[0] - diffs[0] / 2.0], midpoints, [coords[-1] + diffs[-1] / 2.0]))


def infer_grid(frame: pd.DataFrame, metric: str):
    clean = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["longitude", "latitude", metric]).copy()
    clean["longitude"] = pd.to_numeric(clean["longitude"], errors="coerce")
    clean["latitude"] = pd.to_numeric(clean["latitude"], errors="coerce")
    clean[metric] = pd.to_numeric(clean[metric], errors="coerce")
    clean = clean.dropna(subset=["longitude", "latitude", metric])
    if clean.empty:
        raise ValueError(f"{metric} 没有可绘制的有效经纬度数据。")

    longitudes = np.sort(clean["longitude"].unique().astype(float))
    latitudes = np.sort(clean["latitude"].unique().astype(float))
    grid = (
        clean.pivot_table(index="latitude", columns="longitude", values=metric, aggfunc="mean")
        .reindex(index=latitudes, columns=longitudes)
        .to_numpy(dtype=float)
    )
    return longitudes, latitudes, coordinate_edges(longitudes), coordinate_edges(latitudes), grid


def compute_catalog_extent(catalog: pd.DataFrame, pad_ratio: float = 0.035) -> tuple[float, float, float, float]:
    lon_min, lon_max = np.inf, -np.inf
    lat_min, lat_max = np.inf, -np.inf
    for _, row in catalog.iterrows():
        frame = row["metrics_df"]
        if not {"longitude", "latitude"}.issubset(frame.columns):
            continue
        lons = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(dtype=float)
        lats = pd.to_numeric(frame["latitude"], errors="coerce").to_numpy(dtype=float)
        lons = lons[np.isfinite(lons)]
        lats = lats[np.isfinite(lats)]
        if lons.size == 0 or lats.size == 0:
            continue
        lon_min = min(lon_min, float(lons.min()))
        lon_max = max(lon_max, float(lons.max()))
        lat_min = min(lat_min, float(lats.min()))
        lat_max = max(lat_max, float(lats.max()))

    if not np.isfinite([lon_min, lon_max, lat_min, lat_max]).all():
        raise ValueError("无法从 network_metrics.csv 推断地图范围。")

    lon_pad = max((lon_max - lon_min) * pad_ratio, 0.05)
    lat_pad = max((lat_max - lat_min) * pad_ratio, 0.05)
    return lon_min - lon_pad, lon_max + lon_pad, lat_min - lat_pad, lat_max + lat_pad


def metric_label(metric: str) -> str:
    return METRIC_CONFIG.get(metric, {}).get("label", metric.replace("_", " ").title())


def metric_kind(metric: str) -> str:
    return METRIC_CONFIG.get(metric, {}).get("kind", "continuous")


def build_norm(metric: str, frames: Sequence[pd.DataFrame]):
    values = []
    for frame in frames:
        if metric in frame.columns:
            values.append(pd.to_numeric(frame[metric], errors="coerce").to_numpy(dtype=float))

    cleaned = [array[np.isfinite(array)] for array in values if array.size > 0]
    if not cleaned:
        return Normalize(vmin=0.0, vmax=1.0)

    stacked = np.concatenate(cleaned)
    if stacked.size == 0:
        return Normalize(vmin=0.0, vmax=1.0)

    center = METRIC_CONFIG.get(metric, {}).get("center")
    vmin = float(np.nanmin(stacked))
    vmax = float(np.nanmax(stacked))
    if np.isclose(vmin, vmax):
        vmax = vmin + 1e-9
    if center is not None and vmin < center < vmax:
        return TwoSlopeNorm(vmin=vmin, vcenter=center, vmax=vmax)
    return Normalize(vmin=vmin, vmax=vmax)


def format_degree_label(value: float, is_lon: bool) -> str:
    suffix = ("E" if value >= 0 else "W") if is_lon else ("N" if value >= 0 else "S")
    abs_value = abs(value)
    degrees = int(abs_value)
    minutes = int(round((abs_value - degrees) * 60))
    if minutes == 60:
        degrees += 1
        minutes = 0
    return f"{degrees}°{suffix}" if minutes == 0 else f"{degrees}°{minutes:02d}'{suffix}"


def configure_map_axes(ax: plt.Axes, extent: tuple[float, float, float, float]) -> None:
    xmin, xmax, ymin, ymax = extent
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_facecolor("white")
    ax.grid(True, color="black", linewidth=0.45, alpha=0.55, zorder=8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: format_degree_label(value, is_lon=True)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: format_degree_label(value, is_lon=False)))
    ax.tick_params(top=True, labeltop=True, right=True, labelright=True, direction="out", pad=2)
    mid_lat = (ymin + ymax) / 2.0
    ax.set_aspect(1.0 / max(np.cos(np.deg2rad(mid_lat)), 1e-6))
    for label in ax.get_yticklabels():
        label.set_rotation(90)
        label.set_va("center")
        label.set_ha("center")


def overlay_vector_boundaries(ax: plt.Axes, boundary_gdf, inner_boundary_gdf) -> None:
    if boundary_gdf is not None:
        boundary_gdf.boundary.plot(ax=ax, color="black", linewidth=0.8, zorder=5)
    if inner_boundary_gdf is not None:
        inner_boundary_gdf.boundary.plot(ax=ax, color="black", linewidth=0.35, alpha=0.9, zorder=6)


def overlay_label_points(ax: plt.Axes, label_points: Optional[pd.DataFrame], fontsize: float = 9.5) -> None:
    if label_points is None or label_points.empty:
        return
    for _, row in label_points.iterrows():
        ax.text(
            float(row["longitude"]),
            float(row["latitude"]),
            str(row["name"]),
            fontsize=fontsize,
            ha="center",
            va="center",
            color="#2d2418",
            alpha=0.95,
            zorder=8,
        )


def add_north_arrow(ax: plt.Axes, x: float = 0.945, y: float = 0.87, size: float = 0.09) -> None:
    ax.text(x, y + size * 0.9, "N", transform=ax.transAxes, ha="center", va="bottom", fontsize=18, fontweight="semibold", zorder=9)
    outer = Polygon(
        [(x, y + size * 0.54), (x - size * 0.14, y - size * 0.23), (x, y - size * 0.08), (x + size * 0.14, y - size * 0.23)],
        closed=True,
        transform=ax.transAxes,
        facecolor="black",
        edgecolor="black",
        linewidth=0.8,
        zorder=9,
    )
    notch = Polygon(
        [(x, y - size * 0.03), (x - size * 0.055, y - size * 0.22), (x + size * 0.055, y - size * 0.22)],
        closed=True,
        transform=ax.transAxes,
        facecolor="white",
        edgecolor="white",
        linewidth=0.0,
        zorder=10,
    )
    ax.add_patch(outer)
    ax.add_patch(notch)


def add_direction_compass(ax: plt.Axes) -> None:
    inset = ax.inset_axes([0.025, 0.03, 0.19, 0.19], projection="polar")
    inset.set_theta_zero_location("E")
    inset.set_theta_direction(1)
    inset.set_ylim(0, 1.0)
    inset.set_rticks([])
    inset.set_xticks(np.deg2rad(np.arange(0, 360, 45)))
    inset.set_xticklabels(["0", "45", "90", "135", "180", "225", "270", "315"])
    inset.tick_params(labelsize=6, pad=-2)
    for angle in np.deg2rad(np.arange(0, 360, 45)):
        inset.plot([angle, angle], [0, 1], color="black", linewidth=0.55)
    for label, angle in zip(DIRECTION_LABELS, np.deg2rad(np.arange(22.5, 360, 45))):
        inset.text(angle, 1.18, label, ha="center", va="center", fontsize=5.5, clip_on=False)

    inset.add_patch(Circle((0.71, 0.73), radius=0.035, transform=inset.transAxes, facecolor="#f4a261", edgecolor="white", linewidth=0.7, zorder=7))
    inset.annotate("", xy=(0.705, 0.722), xytext=(0.515, 0.515), xycoords=inset.transAxes, textcoords=inset.transAxes, arrowprops=dict(arrowstyle="->", color="#29b6f6", lw=1.2, shrinkA=0, shrinkB=1.5), zorder=6)
    inset.annotate("", xy=(0.535, 0.485), xytext=(0.725, 0.692), xycoords=inset.transAxes, textcoords=inset.transAxes, arrowprops=dict(arrowstyle="->", color="#d62828", lw=1.35, shrinkA=1.5, shrinkB=0), zorder=6)
    inset.grid(False)
    inset.set_facecolor("white")
    inset.patch.set_alpha(1.0)


def annotate_panel(ax: plt.Axes, panel_index: int, title: str) -> None:
    ax.text(0.04, 0.96, f"({chr(ord('a') + panel_index)})", transform=ax.transAxes, ha="left", va="top", fontsize=17)
    ax.set_title(title, pad=10)


def maybe_outline_valid_mask(ax: plt.Axes, longitudes: np.ndarray, latitudes: np.ndarray, grid: np.ndarray) -> None:
    valid_mask = np.isfinite(grid).astype(float)
    if valid_mask.shape[0] < 2 or valid_mask.shape[1] < 2 or valid_mask.max() == 0:
        return
    ax.contour(longitudes, latitudes, valid_mask, levels=[0.5], colors="black", linewidths=0.7, zorder=4)


def get_direction_style() -> tuple[ListedColormap, BoundaryNorm]:
    cmap = ListedColormap(DIRECTION_COLORS)
    cmap.set_bad("white")
    norm = BoundaryNorm(np.arange(-0.5, len(DIRECTION_LABELS) + 0.5, 1), cmap.N)
    return cmap, norm


def add_continuous_colorbar(ax: plt.Axes, mappable, metric: str) -> None:
    cax = make_axes_locatable(ax).append_axes("right", size="3.5%", pad=0.12)
    cbar = plt.colorbar(mappable, cax=cax)
    cbar.set_label(metric_label(metric))


def add_direction_colorbar(ax: plt.Axes, cmap: ListedColormap, norm: BoundaryNorm, metric: str) -> None:
    cax = make_axes_locatable(ax).append_axes("right", size="4.8%", pad=0.10)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=cax, ticks=np.arange(len(DIRECTION_LABELS)))
    cbar.ax.set_yticklabels(DIRECTION_LABELS)
    cbar.set_label(metric_label(metric))


def draw_metric_map(
    ax: plt.Axes,
    frame: pd.DataFrame,
    metric: str,
    norm: Optional[Normalize],
    extent: tuple[float, float, float, float],
    panel_index: int,
    boundary_gdf,
    inner_boundary_gdf,
    label_points: Optional[pd.DataFrame],
) -> None:
    longitudes, latitudes, lon_edges, lat_edges, grid = infer_grid(frame, metric)
    annotate_panel(ax, panel_index=panel_index, title=metric_label(metric))

    if metric_kind(metric) == "direction":
        cmap, direction_norm = get_direction_style()
        masked = np.ma.masked_where((grid < 0) | ~np.isfinite(grid), grid)
        mesh = ax.pcolormesh(lon_edges, lat_edges, masked, cmap=cmap, norm=direction_norm, shading="auto", zorder=1)
        add_direction_colorbar(ax, cmap, direction_norm, metric)
        add_direction_compass(ax)
    else:
        masked = np.ma.masked_invalid(grid)
        mesh = ax.pcolormesh(
            lon_edges,
            lat_edges,
            masked,
            cmap=METRIC_CONFIG.get(metric, {}).get("cmap", "viridis"),
            norm=norm,
            shading="auto",
            zorder=1,
        )
        add_continuous_colorbar(ax, mesh, metric)

    maybe_outline_valid_mask(ax, longitudes, latitudes, grid)
    overlay_vector_boundaries(ax, boundary_gdf, inner_boundary_gdf)
    overlay_label_points(ax, label_points)
    configure_map_axes(ax, extent)
    add_north_arrow(ax)


def draw_metric_map_core(
    ax: plt.Axes,
    frame: pd.DataFrame,
    metric: str,
    norm: Optional[Normalize],
    extent: tuple[float, float, float, float],
    boundary_gdf,
    inner_boundary_gdf,
    label_points: Optional[pd.DataFrame],
    panel_title: str,
    add_compass: bool = True,
    show_north_arrow: bool = True,
    label_fontsize: float = 9.0,
):
    longitudes, latitudes, lon_edges, lat_edges, grid = infer_grid(frame, metric)
    ax.set_title(panel_title, pad=8, fontsize=11)

    if metric_kind(metric) == "direction":
        cmap, direction_norm = get_direction_style()
        masked = np.ma.masked_where((grid < 0) | ~np.isfinite(grid), grid)
        mesh = ax.pcolormesh(lon_edges, lat_edges, masked, cmap=cmap, norm=direction_norm, shading="auto", zorder=1)
        if add_compass:
            add_direction_compass(ax)
    else:
        masked = np.ma.masked_invalid(grid)
        mesh = ax.pcolormesh(
            lon_edges,
            lat_edges,
            masked,
            cmap=METRIC_CONFIG.get(metric, {}).get("cmap", "viridis"),
            norm=norm,
            shading="auto",
            zorder=1,
        )

    maybe_outline_valid_mask(ax, longitudes, latitudes, grid)
    overlay_vector_boundaries(ax, boundary_gdf, inner_boundary_gdf)
    overlay_label_points(ax, label_points=label_points, fontsize=label_fontsize)
    configure_map_axes(ax, extent)
    if show_north_arrow:
        add_north_arrow(ax)
    return mesh


def create_window_metric_pair_figure(
    row: pd.Series,
    pair_cfg: Dict[str, object],
    extent: tuple[float, float, float, float],
    boundary_gdf=None,
    inner_boundary_gdf=None,
    label_points: Optional[pd.DataFrame] = None,
):
    configure_style()
    frame = row["metrics_df"]
    metrics = [metric for metric in pair_cfg["metrics"] if metric in frame.columns]
    if len(metrics) != 2:
        raise ValueError("当前窗口缺少绘制该指标对所需的列。")

    fig, axes = plt.subplots(1, 2, figsize=(17.4, 6.8), constrained_layout=True)
    for panel_index, metric in enumerate(metrics):
        norm = build_norm(metric, [frame]) if metric_kind(metric) == "continuous" else None
        draw_metric_map(
            ax=axes[panel_index],
            frame=frame,
            metric=metric,
            norm=norm,
            extent=extent,
            panel_index=panel_index,
            boundary_gdf=boundary_gdf,
            inner_boundary_gdf=inner_boundary_gdf,
            label_points=label_points,
        )

    start = row.get("window_start")
    end = row.get("window_end")
    if pd.notna(start) and pd.notna(end):
        title = f"{pair_cfg['title']}: {start:%Y-%m-%d} to {end:%Y-%m-%d}"
    else:
        title = f"{pair_cfg['title']}: {row['window_label']}"
    fig.suptitle(title, fontsize=17, fontweight="semibold")
    return fig


def export_window_pairs(
    catalog: pd.DataFrame,
    pair_configs: Sequence[Dict[str, object]],
    out_dir: str | Path,
    formats: Sequence[str],
    dpi: int,
    boundary_gdf=None,
    inner_boundary_gdf=None,
    label_points: Optional[pd.DataFrame] = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extent = compute_catalog_extent(catalog)

    for _, row in catalog.iterrows():
        for pair_cfg in pair_configs:
            figure = create_window_metric_pair_figure(
                row=row,
                pair_cfg=pair_cfg,
                extent=extent,
                boundary_gdf=boundary_gdf,
                inner_boundary_gdf=inner_boundary_gdf,
                label_points=label_points,
            )
            out_base = out_dir / f"{sanitize_name(row['window_name'])}_{sanitize_name(str(pair_cfg['pair_id']))}"
            for fmt in formats:
                figure.savefig(out_base.with_suffix(f".{fmt}"), dpi=dpi)
            plt.close(figure)

    return out_dir


def create_metric_comparison_figure(
    catalog: pd.DataFrame,
    metric: str,
    boundary_gdf=None,
    inner_boundary_gdf=None,
    label_points: Optional[pd.DataFrame] = None,
):
    configure_style()
    extent = compute_catalog_extent(catalog)
    n_windows = len(catalog)
    ncols = 1 if n_windows <= 3 else 2
    nrows = ceil(n_windows / ncols)
    fig_width = 8.4 if ncols == 1 else 16.2
    fig_height = max(7.0, 6.6 * nrows + 0.6)
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_width, fig_height), constrained_layout=True)
    axes_array = np.atleast_1d(axes).ravel()

    norm = build_norm(metric, [row["metrics_df"] for _, row in catalog.iterrows()]) if metric_kind(metric) == "continuous" else None
    comparison_label_points = label_points if n_windows <= 4 else None
    last_mesh = None
    for axis in axes_array[n_windows:]:
        axis.set_visible(False)

    for index, (_, row) in enumerate(catalog.iterrows()):
        title = str(row["window_label"])
        start = row.get("window_start")
        end = row.get("window_end")
        if pd.notna(start) and pd.notna(end):
            title = f"{start:%Y-%m}\n{end:%Y-%m}"
        last_mesh = draw_metric_map_core(
            ax=axes_array[index],
            frame=row["metrics_df"],
            metric=metric,
            norm=norm,
            extent=extent,
            boundary_gdf=boundary_gdf,
            inner_boundary_gdf=inner_boundary_gdf,
            label_points=comparison_label_points,
            panel_title=title,
            add_compass=metric_kind(metric) == "direction" and index == 0,
            show_north_arrow=index == 0,
            label_fontsize=8.2,
        )

    if metric_kind(metric) == "direction":
        cmap, direction_norm = get_direction_style()
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=direction_norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=axes_array[:n_windows].tolist(), shrink=0.92, pad=0.015, ticks=np.arange(len(DIRECTION_LABELS)))
        cbar.ax.set_yticklabels(DIRECTION_LABELS)
        cbar.set_label(metric_label(metric))
    elif last_mesh is not None:
        cbar = fig.colorbar(last_mesh, ax=axes_array[:n_windows].tolist(), shrink=0.92, pad=0.015)
        cbar.set_label(metric_label(metric))

    fig.suptitle(f"{metric_label(metric)} 多窗口比较", fontsize=18, fontweight="semibold")
    return fig


def create_metric_trend_figure(catalog: pd.DataFrame, metric: str):
    configure_style()
    fig, ax = plt.subplots(1, 1, figsize=(12.5, 6.2), constrained_layout=True)

    labels = []
    for _, row in catalog.iterrows():
        start = row.get("window_start")
        end = row.get("window_end")
        if pd.notna(start) and pd.notna(end):
            labels.append(f"{start:%Y-%m}\n{end:%Y-%m}")
        else:
            labels.append(str(row["window_label"]))

    x = np.arange(len(catalog))
    if metric_kind(metric) == "direction":
        counts_by_direction = []
        for _, row in catalog.iterrows():
            frame = row["metrics_df"]
            values = pd.to_numeric(frame.get(metric), errors="coerce").dropna().astype(int)
            counts = np.array([(values == idx).sum() for idx in range(len(DIRECTION_LABELS))], dtype=float)
            total = counts.sum()
            counts_by_direction.append(counts / total if total > 0 else counts)

        proportions = np.vstack(counts_by_direction) if counts_by_direction else np.zeros((0, len(DIRECTION_LABELS)))
        bottom = np.zeros(len(catalog))
        for idx, direction_label in enumerate(DIRECTION_LABELS):
            values = proportions[:, idx] if len(proportions) else np.zeros(len(catalog))
            ax.bar(x, values, bottom=bottom, color=DIRECTION_COLORS[idx], label=direction_label, width=0.72)
            bottom += values
        ax.set_ylabel("Proportion")
        ax.set_ylim(0, 1)
        ax.legend(ncol=4, frameon=False, loc="upper right")
    else:
        means = []
        medians = []
        minimums = []
        maximums = []
        for _, row in catalog.iterrows():
            frame = row["metrics_df"]
            values = pd.to_numeric(frame.get(metric), errors="coerce").dropna()
            if values.empty:
                means.append(np.nan)
                medians.append(np.nan)
                minimums.append(np.nan)
                maximums.append(np.nan)
            else:
                means.append(float(values.mean()))
                medians.append(float(values.median()))
                minimums.append(float(values.min()))
                maximums.append(float(values.max()))

        means = np.array(means, dtype=float)
        medians = np.array(medians, dtype=float)
        minimums = np.array(minimums, dtype=float)
        maximums = np.array(maximums, dtype=float)
        ax.fill_between(x, minimums, maximums, color="#bfd7ea", alpha=0.45, label="Min-Max Range")
        ax.plot(x, means, color="#c1121f", marker="o", linewidth=2.1, label="Mean")
        ax.plot(x, medians, color="#1d3557", marker="s", linewidth=1.9, label="Median")
        ax.legend(frameon=False)
        ax.set_ylabel(metric_label(metric))

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.set_xlabel("Window")
    ax.set_title(f"{metric_label(metric)} Trend", fontsize=15, fontweight="semibold")
    return fig
