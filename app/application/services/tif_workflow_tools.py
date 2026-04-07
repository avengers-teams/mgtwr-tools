from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import geopandas as gpd
import numpy as np
import pyproj
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.mask import mask as raster_mask
from rasterio.transform import Affine, array_bounds, from_origin
from rasterio.warp import calculate_default_transform, reproject
from shapely.geometry import mapping


ProgressCallback = Callable[[str], None]
StopCallback = Callable[[], bool]


@dataclass(slots=True)
class TifBatchProcessResult:
    processed_files: int
    failed_files: int
    generated_outputs: list[str]
    failures: list[str]


@dataclass(slots=True)
class ClipStepConfig:
    mode: str
    mask_path: str
    apply_reference_nodata: bool = True
    trim_nodata_border: bool = False
    all_touched: bool = False
    resampling: str = "nearest"


@dataclass(slots=True)
class ResampleStepConfig:
    mode: str
    reference_path: str | None = None
    resolution: tuple[float, float] | None = None
    resampling: str = "nearest"


@dataclass(slots=True)
class ReprojectStepConfig:
    target_crs: str
    resampling: str = "nearest"


@dataclass(slots=True)
class ReclassifyStepConfig:
    mode: str
    rules_text: str
    keep_unmatched: bool = True
    output_nodata: float | None = None


WorkflowStepConfig = ClipStepConfig | ResampleStepConfig | ReprojectStepConfig | ReclassifyStepConfig


@dataclass(slots=True)
class TifBatchWorkflowOptions:
    input_path: str
    output_dir: str
    recursive: bool = False
    source_crs_override: str | None = None
    output_suffix: str = "workflow"
    steps: tuple[WorkflowStepConfig, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class RasterState:
    data: np.ndarray
    transform: Affine
    crs: CRS | None
    nodata: float | int | None
    profile: dict[str, object]

    @property
    def count(self) -> int:
        return int(self.data.shape[0])

    @property
    def height(self) -> int:
        return int(self.data.shape[1])

    @property
    def width(self) -> int:
        return int(self.data.shape[2])


class TifWorkflowToolsService:
    RESAMPLING_ITEMS = [
        ("nearest", "Nearest"),
        ("bilinear", "Bilinear"),
        ("cubic", "Cubic"),
        ("average", "Average"),
        ("mode", "Mode"),
        ("max", "Max"),
        ("min", "Min"),
        ("med", "Median"),
        ("q1", "Q1"),
        ("q3", "Q3"),
    ]
    CLIP_MODE_ITEMS = [
        ("shp", "矢量掩膜 (shp/geojson/gpkg)"),
        ("reference", "参考 TIFF 掩膜"),
    ]
    RESAMPLE_MODE_ITEMS = [
        ("reference", "参考 TIFF 对齐"),
        ("manual", "手动输入分辨率"),
    ]
    RECLASS_MODE_ITEMS = [
        ("interval", "区间映射"),
        ("value_map", "一对一映射"),
    ]
    PROJECTION_PRESETS = [
        ("EPSG:4326", "WGS 84 (EPSG:4326)"),
        ("EPSG:3857", "Web Mercator (EPSG:3857)"),
        ("EPSG:4490", "CGCS2000 (EPSG:4490)"),
        ("EPSG:4547", "CGCS2000 / 3-degree GK CM 114E (EPSG:4547)"),
        ("EPSG:4549", "CGCS2000 / 3-degree GK CM 120E (EPSG:4549)"),
        ("EPSG:32649", "WGS 84 / UTM zone 49N (EPSG:32649)"),
        ("EPSG:32650", "WGS 84 / UTM zone 50N (EPSG:32650)"),
        ("custom", "自定义 CRS"),
    ]

    @classmethod
    def resampling_items(cls) -> list[tuple[str, str]]:
        return list(cls.RESAMPLING_ITEMS)

    @classmethod
    def clip_mode_items(cls) -> list[tuple[str, str]]:
        return list(cls.CLIP_MODE_ITEMS)

    @classmethod
    def resample_mode_items(cls) -> list[tuple[str, str]]:
        return list(cls.RESAMPLE_MODE_ITEMS)

    @classmethod
    def reclass_mode_items(cls) -> list[tuple[str, str]]:
        return list(cls.RECLASS_MODE_ITEMS)

    @classmethod
    def projection_preset_items(cls) -> list[tuple[str, str]]:
        return list(cls.PROJECTION_PRESETS)

    @staticmethod
    def parse_optional_float(text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        return float(stripped)

    @staticmethod
    def inspect_raster(path: str) -> dict[str, object]:
        with rasterio.open(path) as dataset:
            res_x = abs(float(dataset.transform.a))
            res_y = abs(float(dataset.transform.e))
            crs_info = TifWorkflowToolsService.describe_crs(dataset.crs)
            return {
                "path": path,
                "bands": dataset.count,
                "width": dataset.width,
                "height": dataset.height,
                "dtype": dataset.dtypes[0] if dataset.dtypes else "",
                "nodata": dataset.nodata,
                "crs": crs_info["crs"],
                "crs_display": crs_info["display"],
                "crs_input": crs_info["input"],
                "resolution": (res_x, res_y),
            }

    @staticmethod
    def describe_crs(crs: CRS | None) -> dict[str, str]:
        if crs is None:
            return {"crs": "", "display": "", "input": ""}

        epsg = crs.to_epsg()
        if epsg is not None:
            text = f"EPSG:{epsg}"
            return {"crs": text, "display": text, "input": text}

        proj_text = crs.to_proj4() if hasattr(crs, "to_proj4") else ""
        wkt_text = crs.to_wkt() if hasattr(crs, "to_wkt") else str(crs)
        display_parts = ["自定义投影"]
        try:
            pycrs = pyproj.CRS.from_user_input(wkt_text)
            method_name = getattr(getattr(pycrs, "coordinate_operation", None), "method_name", "") or ""
            ellipsoid_name = getattr(getattr(pycrs, "ellipsoid", None), "name", "") or ""
            if method_name and method_name.lower() != "unknown":
                display_parts.append(method_name)
            if ellipsoid_name and ellipsoid_name.lower() != "unknown":
                display_parts.append(f"椭球={ellipsoid_name}")
        except Exception:
            pass

        display = " / ".join(display_parts)
        input_text = proj_text.strip() or wkt_text.strip()
        return {"crs": wkt_text.strip(), "display": display, "input": input_text}

    @classmethod
    def inspect_input_source(cls, input_path: str, recursive: bool = False) -> dict[str, object] | None:
        sample_path = cls._resolve_sample_file(input_path, recursive)
        if sample_path is None:
            return None
        return cls.inspect_raster(sample_path)

    @classmethod
    def process_batch(
        cls,
        options: TifBatchWorkflowOptions,
        progress_callback: ProgressCallback | None = None,
        stop_callback: StopCallback | None = None,
    ) -> TifBatchProcessResult:
        progress = progress_callback or (lambda _message: None)
        should_stop = stop_callback or (lambda: False)

        if not options.steps:
            raise ValueError("至少需要在流程区放入一个处理步骤")

        if options.source_crs_override:
            CRS.from_user_input(options.source_crs_override)

        input_files = cls._collect_input_files(options.input_path, options.recursive)
        if not input_files:
            raise ValueError("没有找到 tif/tiff 文件")

        os.makedirs(options.output_dir, exist_ok=True)

        processed = 0
        failed = 0
        outputs: list[str] = []
        failures: list[str] = []
        input_root = options.input_path if os.path.isdir(options.input_path) else os.path.dirname(options.input_path)

        for index, input_file in enumerate(input_files, start=1):
            if should_stop():
                raise InterruptedError("任务已终止")

            progress(f"[{index}/{len(input_files)}] 处理中: {input_file}")
            try:
                output_path = cls._process_single_file(input_file, input_root, options)
            except InterruptedError:
                raise
            except Exception as exc:
                failed += 1
                message = f"{input_file}: {exc}"
                failures.append(message)
                progress(f"失败: {message}")
                continue

            processed += 1
            outputs.append(output_path)
            progress(f"完成: {output_path}")

        return TifBatchProcessResult(
            processed_files=processed,
            failed_files=failed,
            generated_outputs=outputs,
            failures=failures,
        )

    @classmethod
    def _process_single_file(cls, input_file: str, input_root: str, options: TifBatchWorkflowOptions) -> str:
        state = cls._read_raster_state(input_file, options.source_crs_override)
        for step in options.steps:
            if isinstance(step, ClipStepConfig):
                state = cls._apply_clip_step(state, step)
            elif isinstance(step, ResampleStepConfig):
                state = cls._apply_resample_step(state, step)
            elif isinstance(step, ReprojectStepConfig):
                state = cls._apply_reproject_step(state, step)
            elif isinstance(step, ReclassifyStepConfig):
                state = cls._apply_reclassify_step(state, step)
            else:
                raise ValueError(f"不支持的流程步骤: {type(step).__name__}")

        output_path = cls._build_output_path(input_file, input_root, options.output_dir, options.output_suffix)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cls._write_state(output_path, state)
        return output_path

    @classmethod
    def _read_raster_state(cls, input_file: str, source_crs_override: str | None) -> RasterState:
        with rasterio.open(input_file) as dataset:
            profile = dict(dataset.profile)
            data = dataset.read(masked=False)
            crs = dataset.crs
            if crs is None and source_crs_override:
                crs = CRS.from_user_input(source_crs_override)
            return RasterState(
                data=data,
                transform=dataset.transform,
                crs=crs,
                nodata=dataset.nodata,
                profile=profile,
            )

    @classmethod
    def _apply_clip_step(cls, state: RasterState, step: ClipStepConfig) -> RasterState:
        if step.mode == "shp":
            return cls._clip_by_vector(state, step)
        if step.mode == "reference":
            return cls._clip_by_reference(state, step)
        raise ValueError(f"不支持的裁切模式: {step.mode}")

    @classmethod
    def _clip_by_vector(cls, state: RasterState, step: ClipStepConfig) -> RasterState:
        if not step.mask_path:
            raise ValueError("裁切步骤缺少矢量文件")
        if state.crs is None:
            raise ValueError("当前栅格缺少投影，无法按矢量裁切")

        vector = gpd.read_file(step.mask_path)
        vector = vector.loc[vector.geometry.notna()].copy()
        if vector.empty:
            raise ValueError("裁切矢量中没有有效几何")
        if vector.crs is None:
            raise ValueError("裁切矢量缺少投影")
        if vector.crs != state.crs:
            vector = vector.to_crs(state.crs)

        dst_state = cls._ensure_nodata(state)
        geoms = [mapping(geom) for geom in vector.geometry]
        with MemoryFile() as memory_file:
            with memory_file.open(**cls._build_profile(dst_state)) as dataset:
                dataset.write(dst_state.data)
                data, transform = raster_mask(
                    dataset,
                    geoms,
                    crop=True,
                    filled=True,
                    nodata=dst_state.nodata,
                    all_touched=step.all_touched,
                )
        clipped = cls._replace_state(dst_state, data=data, transform=transform)
        if step.trim_nodata_border:
            clipped = cls._trim_nodata_border(clipped)
        return clipped

    @classmethod
    def _clip_by_reference(cls, state: RasterState, step: ClipStepConfig) -> RasterState:
        if not step.mask_path:
            raise ValueError("裁切步骤缺少参考 tif")
        with rasterio.open(step.mask_path) as reference:
            if reference.crs is None and state.crs is None:
                raise ValueError("源栅格和参考 tif 都缺少投影，无法对齐")
            aligned = cls._reproject_to_grid(
                state,
                width=reference.width,
                height=reference.height,
                transform=reference.transform,
                crs=reference.crs,
                resampling=step.resampling,
            )
            if step.apply_reference_nodata:
                aligned = cls._apply_mask(aligned, reference.dataset_mask() == 0)
        if step.trim_nodata_border:
            aligned = cls._trim_nodata_border(aligned)
        return aligned

    @classmethod
    def _apply_resample_step(cls, state: RasterState, step: ResampleStepConfig) -> RasterState:
        if step.mode == "reference":
            if not step.reference_path:
                raise ValueError("重采样步骤缺少参考 tif")
            with rasterio.open(step.reference_path) as reference:
                if reference.crs is None and state.crs is None:
                    raise ValueError("源栅格和参考 tif 都缺少投影，无法参考重采样")
                return cls._reproject_to_grid(
                    state,
                    width=reference.width,
                    height=reference.height,
                    transform=reference.transform,
                    crs=reference.crs,
                    resampling=step.resampling,
                )

        if step.mode != "manual":
            raise ValueError(f"不支持的重采样模式: {step.mode}")
        if step.resolution is None:
            raise ValueError("手动重采样时必须填写输出分辨率")

        res_x, res_y = step.resolution
        if res_x <= 0 or res_y <= 0:
            raise ValueError("输出分辨率必须大于 0")

        xmin, ymin, xmax, ymax = array_bounds(state.height, state.width, state.transform)
        width = max(1, int(math.ceil((xmax - xmin) / res_x)))
        height = max(1, int(math.ceil((ymax - ymin) / res_y)))
        transform = from_origin(xmin, ymax, res_x, res_y)
        return cls._reproject_to_grid(
            state,
            width=width,
            height=height,
            transform=transform,
            crs=state.crs,
            resampling=step.resampling,
        )

    @classmethod
    def _apply_reproject_step(cls, state: RasterState, step: ReprojectStepConfig) -> RasterState:
        if state.crs is None:
            raise ValueError("当前栅格缺少投影，无法执行重投影")

        target_crs = CRS.from_user_input(step.target_crs)
        if target_crs == state.crs:
            return state

        left, bottom, right, top = array_bounds(state.height, state.width, state.transform)
        transform, width, height = calculate_default_transform(
            state.crs,
            target_crs,
            state.width,
            state.height,
            left,
            bottom,
            right,
            top,
        )
        return cls._reproject_to_grid(
            state,
            width=width,
            height=height,
            transform=transform,
            crs=target_crs,
            resampling=step.resampling,
        )

    @classmethod
    def _apply_reclassify_step(cls, state: RasterState, step: ReclassifyStepConfig) -> RasterState:
        rules = cls._parse_reclass_rules(step.mode, step.rules_text)
        working = cls._ensure_float_state(state)
        nodata = step.output_nodata if step.output_nodata is not None else working.nodata
        if nodata is None:
            nodata = np.nan

        source = working.data.astype(np.float32, copy=False)
        invalid_mask = cls._nodata_mask(source, working.nodata)

        result = np.full(source.shape, nodata, dtype=np.float32)
        if step.keep_unmatched:
            result[:] = source
        else:
            result[:] = nodata

        valid = ~invalid_mask
        if step.mode == "interval":
            for minimum, maximum, target_value in rules:
                current = valid & (source >= minimum)
                if not (math.isinf(maximum) and maximum > 0):
                    current &= source < maximum
                result[current] = target_value
        else:
            for old_value, new_value in rules:
                current = valid & np.isclose(source, old_value, equal_nan=False)
                result[current] = new_value

        result[invalid_mask] = nodata
        profile = dict(working.profile)
        profile["dtype"] = "float32"
        return RasterState(
            data=result,
            transform=working.transform,
            crs=working.crs,
            nodata=nodata,
            profile=profile,
        )

    @classmethod
    def _reproject_to_grid(
        cls,
        state: RasterState,
        width: int,
        height: int,
        transform: Affine,
        crs: CRS | None,
        resampling: str,
    ) -> RasterState:
        if state.crs is None and crs is not None:
            raise ValueError("源栅格缺少投影，无法对齐到目标网格")
        if state.crs is not None and crs is None:
            raise ValueError("目标网格缺少投影，无法执行重投影/重采样")

        working = cls._ensure_nodata(state)
        destination = np.full(
            (working.count, height, width),
            working.nodata,
            dtype=working.data.dtype,
        )
        method = cls._resolve_resampling(resampling)

        for band_index in range(working.count):
            reproject(
                source=working.data[band_index],
                destination=destination[band_index],
                src_transform=working.transform,
                src_crs=working.crs,
                src_nodata=working.nodata,
                dst_transform=transform,
                dst_crs=crs,
                dst_nodata=working.nodata,
                resampling=method,
            )

        return cls._replace_state(
            working,
            data=destination,
            transform=transform,
            crs=crs,
        )

    @classmethod
    def _ensure_nodata(cls, state: RasterState) -> RasterState:
        if state.nodata is not None:
            return state
        if np.issubdtype(state.data.dtype, np.integer):
            temporary_nodata = cls._pick_temporary_integer_nodata(state.data)
            if temporary_nodata is not None:
                return cls._replace_state(state, nodata=temporary_nodata)
            raise ValueError("当前整数栅格缺少 NoData，且无法找到安全的临时整数 NoData 值，请先为源数据设置 NoData")
        return cls._ensure_float_state(state, nodata=np.nan)

    @classmethod
    def _ensure_float_state(cls, state: RasterState, nodata: float = np.nan) -> RasterState:
        float_data = state.data.astype(np.float32, copy=False)
        float_nodata = nodata if state.nodata is None else float(state.nodata)
        profile = dict(state.profile)
        profile["dtype"] = "float32"
        if np.issubdtype(state.data.dtype, np.floating):
            return RasterState(
                data=float_data,
                transform=state.transform,
                crs=state.crs,
                nodata=float_nodata,
                profile=profile,
            )
        return RasterState(
            data=float_data,
            transform=state.transform,
            crs=state.crs,
            nodata=float_nodata,
            profile=profile,
        )

    @classmethod
    def _apply_mask(cls, state: RasterState, mask_2d: np.ndarray) -> RasterState:
        working = cls._ensure_nodata(state)
        result = np.where(mask_2d[None, :, :], working.nodata, working.data)
        return cls._replace_state(working, data=result)

    @classmethod
    def _trim_nodata_border(cls, state: RasterState) -> RasterState:
        invalid_mask = cls._nodata_mask(state.data, state.nodata)
        valid_mask = ~np.all(invalid_mask, axis=0)
        if not valid_mask.any():
            raise ValueError("裁切后没有有效像元")

        row_index = np.where(valid_mask.any(axis=1))[0]
        col_index = np.where(valid_mask.any(axis=0))[0]
        row_start, row_end = int(row_index[0]), int(row_index[-1]) + 1
        col_start, col_end = int(col_index[0]), int(col_index[-1]) + 1
        data = state.data[:, row_start:row_end, col_start:col_end]
        transform = state.transform * Affine.translation(col_start, row_start)
        return cls._replace_state(state, data=data, transform=transform)

    @staticmethod
    def _replace_state(
        state: RasterState,
        *,
        data: np.ndarray | None = None,
        transform: Affine | None = None,
        crs: CRS | None | object = ...,
        nodata: float | int | None | object = ...,
    ) -> RasterState:
        next_profile = dict(state.profile)
        next_data = data if data is not None else state.data
        next_transform = transform if transform is not None else state.transform
        next_crs = state.crs if crs is ... else crs
        next_nodata = state.nodata if nodata is ... else nodata
        next_profile["dtype"] = np.dtype(next_data.dtype).name
        return RasterState(
            data=next_data,
            transform=next_transform,
            crs=next_crs,
            nodata=next_nodata,
            profile=next_profile,
        )

    @staticmethod
    def _build_profile(state: RasterState) -> dict[str, object]:
        profile = dict(state.profile)
        for key in ("blockxsize", "blockysize", "tiled"):
            profile.pop(key, None)
        profile.update(
            driver="GTiff",
            count=state.count,
            height=state.height,
            width=state.width,
            transform=state.transform,
            dtype=np.dtype(state.data.dtype).name,
            nodata=state.nodata,
        )
        if state.crs is not None:
            profile["crs"] = state.crs
        else:
            profile.pop("crs", None)
        return profile

    @classmethod
    def _write_state(cls, output_path: str, state: RasterState) -> None:
        with rasterio.open(output_path, "w", **cls._build_profile(state)) as dataset:
            dataset.write(state.data)

    @classmethod
    def _nodata_mask(cls, data: np.ndarray, nodata: float | int | None) -> np.ndarray:
        if nodata is None:
            if np.issubdtype(data.dtype, np.floating):
                return np.isnan(data)
            return np.zeros(data.shape, dtype=bool)
        if isinstance(nodata, float) and math.isnan(nodata):
            return np.isnan(data)
        if np.issubdtype(data.dtype, np.floating):
            return np.isclose(data, nodata, equal_nan=True)
        return data == nodata

    @classmethod
    def _parse_reclass_rules(cls, mode: str, rules_text: str) -> list[tuple[float, ...]]:
        lines = [line.strip() for line in rules_text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("重分类规则不能为空")

        if mode == "interval":
            rules: list[tuple[float, float, float]] = []
            for line in lines:
                parts = [item.strip() for item in re.split(r"[,\t，]+", line) if item.strip()]
                if len(parts) != 3:
                    raise ValueError(f"区间映射格式错误: {line}")
                minimum = cls._parse_interval_endpoint(parts[0], negative_default=True)
                maximum = cls._parse_interval_endpoint(parts[1], negative_default=False)
                if minimum >= maximum:
                    raise ValueError(f"区间上下界无效: {line}")
                rules.append((minimum, maximum, float(parts[2])))
            return rules

        if mode == "value_map":
            rules = []
            for line in lines:
                parts = [item.strip() for item in re.split(r"[,\t，]+", line) if item.strip()]
                if len(parts) != 2:
                    raise ValueError(f"一对一映射格式错误: {line}")
                rules.append((float(parts[0]), float(parts[1])))
            return rules

        raise ValueError(f"不支持的重分类模式: {mode}")

    @staticmethod
    def _parse_interval_endpoint(text: str, negative_default: bool) -> float:
        lowered = text.strip().lower()
        if lowered in {"-inf", "-infinity", "min"}:
            return float("-inf")
        if lowered in {"inf", "+inf", "infinity", "max"}:
            return float("inf")
        if lowered == "":
            return float("-inf") if negative_default else float("inf")
        return float(lowered)

    @classmethod
    def _resolve_resampling(cls, value: str) -> Resampling:
        mapping = {name: enum for name, enum in Resampling.__members__.items()}
        if value not in mapping:
            raise ValueError(f"不支持的重采样方法: {value}")
        return mapping[value]

    @classmethod
    def _pick_temporary_integer_nodata(cls, data: np.ndarray) -> int | None:
        dtype = data.dtype
        info = np.iinfo(dtype)
        flat = data.reshape(-1)
        candidates = [
            int(info.min),
            int(info.max),
            0,
            -9999,
            -32768,
            32767,
            65535,
            9999,
        ]

        seen: set[int] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate < int(info.min) or candidate > int(info.max):
                continue
            cast_candidate = np.array(candidate, dtype=dtype).item()
            if not np.any(flat == cast_candidate):
                return int(cast_candidate)

        return None

    @staticmethod
    def _build_output_path(input_file: str, input_root: str, output_dir: str, suffix: str) -> str:
        input_path = Path(input_file)
        root_path = Path(input_root) if input_root else input_path.parent
        try:
            relative_parent = input_path.parent.relative_to(root_path)
        except ValueError:
            relative_parent = Path()

        suffix_text = suffix.strip()
        filename = f"{input_path.stem}_{suffix_text}.tif" if suffix_text else f"{input_path.stem}.tif"
        return str(Path(output_dir) / relative_parent / filename)

    @classmethod
    def _resolve_sample_file(cls, input_path: str, recursive: bool) -> str | None:
        if not input_path:
            return None
        path = Path(input_path)
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}:
            return str(path)
        if not path.is_dir():
            return None
        pattern = "**/*" if recursive else "*"
        matches = sorted(
            file_path for file_path in path.glob(pattern) if file_path.is_file() and file_path.suffix.lower() in {".tif", ".tiff"}
        )
        return str(matches[0]) if matches else None

    @classmethod
    def _collect_input_files(cls, input_path: str, recursive: bool) -> list[str]:
        path = Path(input_path)
        if path.is_file():
            if path.suffix.lower() not in {".tif", ".tiff"}:
                raise ValueError("输入文件必须是 tif/tiff")
            return [str(path)]
        if not path.is_dir():
            raise ValueError("输入路径不存在")

        iterator = path.rglob("*") if recursive else path.glob("*")
        files = [str(file_path) for file_path in iterator if file_path.is_file() and file_path.suffix.lower() in {".tif", ".tiff"}]
        return sorted(files)
