from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import geopandas as gpd
import numpy as np
import rasterio
from netCDF4 import Dataset
from rasterio.features import geometry_mask
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine, array_bounds, from_origin
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.windows import transform as window_transform
from shapely.geometry import mapping


ProgressCallback = Callable[[str], None]
StopCallback = Callable[[], bool]


@dataclass(slots=True)
class NCRasterBatchOptions:
    input_path: str
    output_dir: str
    output_format: str = "nc"
    recursive: bool = False
    reference_path: str | None = None
    reference_nodata: float | int | None = None
    mask_by_reference: bool = False
    clip_vector_path: str | None = None
    target_crs: str | None = None
    crop_bounds: tuple[float, float, float, float] | None = None
    resolution: tuple[float, float] | None = None
    nodata: float | int | None = None
    resampling: str = "nearest"
    suffix: str = "aligned"
    variables: tuple[str, ...] = field(default_factory=tuple)
    tif_split_dims: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class BatchProcessResult:
    processed_files: int
    failed_files: int
    generated_outputs: list[str]
    failures: list[str]


@dataclass(slots=True)
class ClipGeometry:
    geometry: object
    crs: CRS


@dataclass(slots=True)
class RasterMaskSource:
    mask: np.ndarray
    grid: SpatialGrid


@dataclass(slots=True)
class SpatialGrid:
    width: int
    height: int
    transform: Affine
    crs: CRS | None
    x_name: str
    y_name: str

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return array_bounds(self.height, self.width, self.transform)

    @property
    def resolution(self) -> tuple[float, float]:
        return abs(float(self.transform.a)), abs(float(self.transform.e))

    @property
    def x_values(self) -> np.ndarray:
        return self.transform.c + (np.arange(self.width, dtype=np.float64) + 0.5) * self.transform.a

    @property
    def y_values(self) -> np.ndarray:
        return self.transform.f + (np.arange(self.height, dtype=np.float64) + 0.5) * self.transform.e

    def is_equivalent(self, other: SpatialGrid) -> bool:
        if self.width != other.width or self.height != other.height:
            return False
        if self.crs != other.crs:
            return False
        return all(
            math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
            for a, b in zip(self.transform[:6], other.transform[:6])
        )


@dataclass(slots=True)
class SpatialVariableContext:
    name: str
    dimensions: tuple[str, ...]
    shape: tuple[int, ...]
    x_dim: str
    y_dim: str
    x_axis: int
    y_axis: int
    source_grid: SpatialGrid
    x_reverse: bool
    y_reverse: bool
    grid_mapping_name: str | None


class NCRasterToolsService:
    X_ALIASES = {
        "x",
        "lon",
        "lng",
        "long",
        "longitude",
        "easting",
        "projection_x_coordinate",
    }
    Y_ALIASES = {
        "y",
        "lat",
        "latitude",
        "northing",
        "projection_y_coordinate",
    }
    GEOGRAPHIC_X_NAMES = {"lon", "longitude", "lng", "long"}
    GEOGRAPHIC_Y_NAMES = {"lat", "latitude"}
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

    @classmethod
    def resampling_items(cls) -> list[tuple[str, str]]:
        return list(cls.RESAMPLING_ITEMS)

    @staticmethod
    def output_format_items() -> list[tuple[str, str]]:
        return [
            ("nc", "输出 NC"),
            ("tif", "输出 TIFF"),
            ("both", "同时输出 NC 和 TIFF"),
        ]

    @staticmethod
    def parse_optional_float(text: str) -> float | None:
        value = text.strip()
        if not value:
            return None
        return float(value)

    @staticmethod
    def parse_variable_text(text: str) -> tuple[str, ...]:
        values = [item.strip() for item in re.split(r"[,\n;，；]+", text) if item.strip()]
        return tuple(dict.fromkeys(values))

    @staticmethod
    def parse_bounds_text(text: str) -> tuple[float, float, float, float] | None:
        stripped = text.strip()
        if not stripped:
            return None
        parts = [item.strip() for item in re.split(r"[,\s，]+", stripped) if item.strip()]
        if len(parts) != 4:
            raise ValueError("裁切范围必须是 4 个数值：xmin,ymin,xmax,ymax")
        xmin, ymin, xmax, ymax = map(float, parts)
        if xmin >= xmax or ymin >= ymax:
            raise ValueError("裁切范围必须满足 xmin < xmax 且 ymin < ymax")
        return xmin, ymin, xmax, ymax

    @staticmethod
    def inspect_reference_tif(path: str) -> dict[str, object]:
        with rasterio.open(path) as dataset:
            return {
                "nodata": dataset.nodata,
                "count": dataset.count,
                "width": dataset.width,
                "height": dataset.height,
                "crs": str(dataset.crs) if dataset.crs else "",
            }

    @classmethod
    def inspect_tif_split_dimensions(
        cls,
        input_path: str,
        recursive: bool = False,
        variable_filter: Iterable[str] = (),
    ) -> tuple[list[str], str | None]:
        input_files = cls._collect_input_files(input_path, recursive)
        if not input_files:
            return [], None

        sample_file = input_files[0]
        with Dataset(sample_file, "r") as dataset:
            contexts = cls._collect_spatial_contexts(dataset, variable_filter)
            if not contexts:
                return [], sample_file

            seen: set[str] = set()
            dimensions: list[str] = []
            for context in contexts:
                for dim_name in context.dimensions:
                    if dim_name in {context.x_dim, context.y_dim} or dim_name in seen:
                        continue
                    seen.add(dim_name)
                    dimensions.append(dim_name)
            return dimensions, sample_file

    @classmethod
    def process_batch(
        cls,
        options: NCRasterBatchOptions,
        progress_callback: ProgressCallback | None = None,
        stop_callback: StopCallback | None = None,
    ) -> BatchProcessResult:
        cls._ensure_directory(options.output_dir)
        progress = progress_callback or (lambda _message: None)
        should_stop = stop_callback or (lambda: False)

        input_files = cls._collect_input_files(options.input_path, options.recursive)
        if not input_files:
            raise ValueError("未找到可处理的 nc 文件")

        reference_grid = None
        reference_mask_source = None
        if options.reference_path:
            progress(f"读取参考网格: {options.reference_path}")
            reference_grid = cls._load_reference_grid(options.reference_path)
            if options.mask_by_reference:
                progress("读取参考栅格掩膜")
                reference_mask_source = cls._load_reference_mask(options.reference_path, options.reference_nodata)

        clip_geometry = None
        if options.clip_vector_path:
            progress(f"读取裁切矢量: {options.clip_vector_path}")
            clip_geometry = cls._load_clip_geometry(options.clip_vector_path)

        generated_outputs: list[str] = []
        failures: list[str] = []
        processed_files = 0

        for index, input_file in enumerate(input_files, start=1):
            if should_stop():
                raise InterruptedError("任务已终止")

            progress(f"[{index}/{len(input_files)}] 处理文件: {input_file}")
            try:
                outputs = cls._process_single_file(
                    input_file,
                    options,
                    reference_grid,
                    reference_mask_source,
                    clip_geometry,
                    progress,
                    should_stop,
                )
                generated_outputs.extend(outputs)
                processed_files += 1
            except InterruptedError:
                raise
            except Exception as exc:
                failures.append(f"{input_file}: {exc}")
                progress(f"处理失败: {input_file} -> {exc}")

        return BatchProcessResult(
            processed_files=processed_files,
            failed_files=len(failures),
            generated_outputs=generated_outputs,
            failures=failures,
        )

    @classmethod
    def _process_single_file(
        cls,
        input_path: str,
        options: NCRasterBatchOptions,
        reference_grid: SpatialGrid | None,
        reference_mask_source: RasterMaskSource | None,
        clip_geometry: ClipGeometry | None,
        progress: ProgressCallback,
        should_stop: StopCallback,
    ) -> list[str]:
        with Dataset(input_path, "r") as src_ds:
            contexts = cls._collect_spatial_contexts(src_ds, options.variables)
            if not contexts:
                raise ValueError("未发现包含空间维度的变量")

            if options.output_format in {"nc", "both"}:
                cls._ensure_nc_grid_compatibility(contexts, options, reference_grid, clip_geometry)

            relative_base = cls._relative_output_base(options.input_path, input_path, options.output_dir, options.suffix)
            outputs: list[str] = []

            nc_dataset = None
            nc_variables: dict[str, object] = {}
            output_grid_by_var: dict[str, SpatialGrid] = {}
            try:
                if options.output_format in {"nc", "both"}:
                    nc_output_path = f"{relative_base}.nc"
                    cls._ensure_directory(os.path.dirname(nc_output_path))
                    nc_dataset, nc_variables, output_grid_by_var = cls._prepare_output_nc(
                        src_ds,
                        contexts,
                        nc_output_path,
                        options,
                        reference_grid,
                        clip_geometry,
                        progress,
                    )
                    outputs.append(nc_output_path)

                tif_dir = None
                if options.output_format in {"tif", "both"}:
                    tif_dir = relative_base
                    cls._ensure_directory(tif_dir)

                for context in contexts:
                    if should_stop():
                        raise InterruptedError("任务已终止")
                    progress(f"变量处理中: {context.name}")
                    output_grid = output_grid_by_var.get(context.name) or cls._build_output_grid(
                        context.source_grid,
                        options,
                        reference_grid,
                        clip_geometry,
                    )
                    reference_mask = cls._resolve_reference_mask(reference_mask_source, output_grid) if reference_mask_source else None
                    clip_mask = cls._build_clip_mask(clip_geometry, output_grid) if clip_geometry else None
                    tif_outputs = cls._process_variable(
                        src_ds,
                        context,
                        output_grid,
                        options,
                        reference_mask=reference_mask,
                        clip_mask=clip_mask,
                        nc_dataset=nc_dataset,
                        nc_variable=nc_variables.get(context.name),
                        tif_dir=tif_dir,
                        progress=progress,
                        should_stop=should_stop,
                    )
                    outputs.extend(tif_outputs)
            finally:
                if nc_dataset is not None:
                    nc_dataset.close()

        return outputs

    @classmethod
    def _prepare_output_nc(
        cls,
        src_ds: Dataset,
        contexts: list[SpatialVariableContext],
        output_path: str,
        options: NCRasterBatchOptions,
        reference_grid: SpatialGrid | None,
        clip_geometry: ClipGeometry | None,
        progress: ProgressCallback,
    ) -> tuple[Dataset, dict[str, object], dict[str, SpatialGrid]]:
        first_grid = cls._build_output_grid(contexts[0].source_grid, options, reference_grid, clip_geometry)
        output_grid_by_var = {contexts[0].name: first_grid}
        for context in contexts[1:]:
            candidate_grid = cls._build_output_grid(context.source_grid, options, reference_grid, clip_geometry)
            output_grid_by_var[context.name] = candidate_grid
            if not first_grid.is_equivalent(candidate_grid):
                raise ValueError("当前文件包含多个空间网格，无法合并到单个输出 nc，请改用 TIFF 输出")

        spatial_dims = {context.x_dim for context in contexts} | {context.y_dim for context in contexts}
        output_x_name, output_y_name = cls._derive_output_dim_names(first_grid)

        dst_ds = Dataset(output_path, "w", format="NETCDF4")
        for attribute in src_ds.ncattrs():
            dst_ds.setncattr(attribute, src_ds.getncattr(attribute))

        for dimension_name, dimension in src_ds.dimensions.items():
            if dimension_name in spatial_dims:
                continue
            dst_ds.createDimension(dimension_name, None if dimension.isunlimited() else len(dimension))
        dst_ds.createDimension(output_y_name, first_grid.height)
        dst_ds.createDimension(output_x_name, first_grid.width)

        cls._create_spatial_coord_vars(dst_ds, first_grid, output_x_name, output_y_name)

        context_by_name = {context.name: context for context in contexts}
        nc_variables: dict[str, object] = {}
        created_names = {output_x_name, output_y_name, "spatial_ref"}

        for variable_name, variable in src_ds.variables.items():
            if variable_name in created_names:
                continue
            context = context_by_name.get(variable_name)
            if context is not None:
                output_dims = list(context.dimensions)
                output_dims[context.y_axis] = output_y_name
                output_dims[context.x_axis] = output_x_name
                fill_value = cls._resolve_dst_nodata(variable, options.nodata)
                output_dtype = cls._resolve_output_dtype(np.dtype(variable.dtype), fill_value)
                dst_var = cls._create_output_variable(
                    dst_ds,
                    variable_name,
                    variable,
                    tuple(output_dims),
                    fill_value,
                    processed=True,
                    dtype_override=output_dtype,
                )
                nc_variables[variable_name] = dst_var
                continue

            if any(dimension_name in spatial_dims for dimension_name in variable.dimensions):
                progress(f"跳过变量 {variable_name}: 含旧空间维度但不属于可处理栅格变量")
                continue

            dst_var = cls._create_output_variable(
                dst_ds,
                variable_name,
                variable,
                variable.dimensions,
                cls._extract_fill_value(variable),
                processed=False,
            )
            if variable.ndim == 0:
                dst_var.assignValue(variable.getValue())
            else:
                dst_var[:] = variable[:]

        return dst_ds, nc_variables, output_grid_by_var

    @classmethod
    def _process_variable(
        cls,
        src_ds: Dataset,
        context: SpatialVariableContext,
        output_grid: SpatialGrid,
        options: NCRasterBatchOptions,
        reference_mask: np.ndarray | None,
        clip_mask: np.ndarray | None,
        nc_dataset: Dataset | None,
        nc_variable,
        tif_dir: str | None,
        progress: ProgressCallback,
        should_stop: StopCallback,
    ) -> list[str]:
        source_var = src_ds.variables[context.name]
        source_data = source_var[:]
        if isinstance(source_data, np.ma.MaskedArray):
            source_fill = cls._resolve_src_nodata(source_var)
            fill_value = source_fill if source_fill is not None else np.nan
            source_data = source_data.filled(fill_value)

        array = np.asarray(source_data)
        array = cls._normalize_spatial_axes(array, context)
        src_nodata = cls._resolve_src_nodata(source_var)
        dst_nodata = cls._resolve_dst_nodata(source_var, options.nodata)

        write_dtype = cls._resolve_output_dtype(array.dtype, dst_nodata)
        leading_axes = [axis for axis in range(len(context.dimensions)) if axis not in {context.y_axis, context.x_axis}]
        leading_dim_names = [context.dimensions[axis] for axis in leading_axes]
        moved = np.moveaxis(array, leading_axes + [context.y_axis, context.x_axis], list(range(array.ndim)))
        leading_shape = moved.shape[:-2]

        tif_outputs: list[str] = []
        tif_groups: dict[tuple[tuple[str, int], ...], list[tuple[str, np.ndarray]]] = {}
        split_positions = cls._resolve_tif_split_positions(leading_dim_names, options.tif_split_dims)
        iterator = [()] if not leading_shape else np.ndindex(*leading_shape)
        for leading_index in iterator:
            if should_stop():
                raise InterruptedError("任务已终止")

            source_slice = moved[leading_index] if leading_shape else moved
            destination = cls._project_array(
                np.asarray(source_slice),
                context.source_grid,
                output_grid,
                src_nodata=src_nodata,
                dst_nodata=dst_nodata,
                resampling=options.resampling,
                write_dtype=write_dtype,
            )
            if reference_mask is not None:
                destination = cls._apply_external_mask(destination, reference_mask, dst_nodata)
            if clip_mask is not None:
                destination = cls._apply_external_mask(destination, clip_mask, dst_nodata)

            if nc_variable is not None:
                cls._write_nc_slice(nc_variable, context, leading_index, destination)

            if tif_dir:
                split_key, band_label = cls._partition_tif_indices(leading_dim_names, leading_index, split_positions, src_ds)
                tif_groups.setdefault(split_key, []).append((band_label, destination))

        if tif_dir:
            for split_key, band_items in tif_groups.items():
                tif_path = cls._build_tif_output_path(context.name, split_key, tif_dir)
                band_labels = [label for label, _array in band_items]
                tif_stack = np.stack([data for _label, data in band_items], axis=0)
                cls._write_tif(
                    tif_path,
                    tif_stack,
                    output_grid,
                    write_dtype,
                    dst_nodata,
                    band_descriptions=band_labels,
                )
                tif_outputs.append(tif_path)

        return tif_outputs

    @classmethod
    def _project_array(
        cls,
        source_array: np.ndarray,
        source_grid: SpatialGrid,
        output_grid: SpatialGrid,
        src_nodata: float | int | None,
        dst_nodata: float | int | None,
        resampling: str,
        write_dtype: np.dtype,
    ) -> np.ndarray:
        if source_grid.is_equivalent(output_grid):
            destination = np.asarray(source_array, dtype=write_dtype)
            return cls._apply_dst_nodata(destination, src_nodata, dst_nodata)

        if source_grid.crs is None or output_grid.crs is None:
            raise ValueError("无法完成重投影/重采样：源网格或目标网格缺少坐标系")

        destination = np.full(
            (output_grid.height, output_grid.width),
            cls._default_fill_value(write_dtype, dst_nodata),
            dtype=write_dtype,
        )
        reproject(
            source=np.asarray(source_array, dtype=write_dtype),
            destination=destination,
            src_transform=source_grid.transform,
            src_crs=source_grid.crs,
            src_nodata=src_nodata,
            dst_transform=output_grid.transform,
            dst_crs=output_grid.crs,
            dst_nodata=dst_nodata,
            resampling=cls._resampling_enum(resampling),
        )
        return destination

    @classmethod
    def _build_output_grid(
        cls,
        source_grid: SpatialGrid,
        options: NCRasterBatchOptions,
        reference_grid: SpatialGrid | None,
        clip_geometry: ClipGeometry | None,
    ) -> SpatialGrid:
        if reference_grid is not None:
            working_grid = reference_grid
        else:
            target_crs = cls._parse_crs(options.target_crs) if options.target_crs else source_grid.crs
            if source_grid.crs is None and target_crs is not None:
                source_grid = SpatialGrid(
                    width=source_grid.width,
                    height=source_grid.height,
                    transform=source_grid.transform,
                    crs=target_crs,
                    x_name=source_grid.x_name,
                    y_name=source_grid.y_name,
                )

            working_grid = source_grid
            if target_crs != source_grid.crs:
                if source_grid.crs is None:
                    raise ValueError("源 nc 缺少坐标系，无法执行重投影，请指定带坐标系的参考数据")
                transform, width, height = calculate_default_transform(
                    source_grid.crs,
                    target_crs,
                    source_grid.width,
                    source_grid.height,
                    *source_grid.bounds,
                    resolution=options.resolution,
                )
                x_name, y_name = cls._derive_output_dim_names_from_crs(target_crs)
                working_grid = SpatialGrid(width=width, height=height, transform=transform, crs=target_crs, x_name=x_name, y_name=y_name)

        clip_bounds = cls._clip_bounds_for_grid(clip_geometry, working_grid) if clip_geometry else None
        bounds = options.crop_bounds or clip_bounds or working_grid.bounds
        resolution = options.resolution or working_grid.resolution
        if options.crop_bounds is not None or options.resolution is not None or clip_bounds is not None:
            x_res, y_res = resolution
            width = max(1, int(math.ceil((bounds[2] - bounds[0]) / x_res)))
            height = max(1, int(math.ceil((bounds[3] - bounds[1]) / y_res)))
            transform = from_origin(bounds[0], bounds[3], x_res, y_res)
            x_name, y_name = cls._derive_output_dim_names_from_crs(working_grid.crs)
            return SpatialGrid(width=width, height=height, transform=transform, crs=working_grid.crs, x_name=x_name, y_name=y_name)

        return working_grid

    @classmethod
    def _load_reference_grid(cls, path: str) -> SpatialGrid:
        extension = Path(path).suffix.lower()
        if extension in {".tif", ".tiff"}:
            with rasterio.open(path) as dataset:
                x_name, y_name = cls._derive_output_dim_names_from_crs(dataset.crs)
                return SpatialGrid(
                    width=dataset.width,
                    height=dataset.height,
                    transform=dataset.transform,
                    crs=dataset.crs,
                    x_name=x_name,
                    y_name=y_name,
                )

        if extension == ".nc":
            with Dataset(path, "r") as dataset:
                contexts = cls._collect_spatial_contexts(dataset, ())
                if not contexts:
                    raise ValueError("参考 nc 中未发现可用空间网格")
                source_grid = contexts[0].source_grid
                x_name, y_name = cls._derive_output_dim_names_from_crs(source_grid.crs)
                return SpatialGrid(
                    width=source_grid.width,
                    height=source_grid.height,
                    transform=source_grid.transform,
                    crs=source_grid.crs,
                    x_name=x_name,
                    y_name=y_name,
                )

        raise ValueError("参考文件仅支持 tif/tiff/nc")

    @classmethod
    def _load_reference_mask(cls, path: str, reference_nodata: float | int | None) -> RasterMaskSource:
        extension = Path(path).suffix.lower()
        if extension not in {".tif", ".tiff"}:
            raise ValueError("参考掩膜仅支持从 tif/tiff 生成")

        with rasterio.open(path) as dataset:
            grid = SpatialGrid(
                width=dataset.width,
                height=dataset.height,
                transform=dataset.transform,
                crs=dataset.crs,
                x_name="x",
                y_name="y",
            )
            if reference_nodata is not None:
                data = dataset.read(masked=False)
                if data.ndim == 2:
                    data = data[np.newaxis, ...]
                invalid_stack = np.isclose(data, reference_nodata, equal_nan=True) if np.issubdtype(data.dtype, np.floating) else data == reference_nodata
                return RasterMaskSource(mask=np.all(invalid_stack, axis=0), grid=grid)

            dataset_mask = dataset.dataset_mask()
            return RasterMaskSource(mask=(dataset_mask == 0), grid=grid)

    @classmethod
    def _load_clip_geometry(cls, path: str) -> ClipGeometry:
        dataframe = gpd.read_file(path)
        if dataframe.empty:
            raise ValueError("裁切矢量为空")
        if dataframe.crs is None:
            raise ValueError("裁切矢量缺少坐标系")
        geometry = dataframe.geometry.union_all()
        if geometry is None or geometry.is_empty:
            raise ValueError("裁切矢量没有有效几何")
        return ClipGeometry(geometry=geometry, crs=CRS.from_user_input(dataframe.crs))

    @classmethod
    def _clip_bounds_for_grid(
        cls,
        clip_geometry: ClipGeometry,
        output_grid: SpatialGrid,
    ) -> tuple[float, float, float, float]:
        if output_grid.crs is None:
            raise ValueError("输出网格缺少坐标系，无法按矢量裁切")
        geometry = cls._transform_geometry(clip_geometry.geometry, clip_geometry.crs, output_grid.crs)
        min_x, min_y, max_x, max_y = geometry.bounds
        grid_min_x, grid_min_y, grid_max_x, grid_max_y = output_grid.bounds
        clipped_bounds = (
            max(min_x, grid_min_x),
            max(min_y, grid_min_y),
            min(max_x, grid_max_x),
            min(max_y, grid_max_y),
        )
        if clipped_bounds[0] >= clipped_bounds[2] or clipped_bounds[1] >= clipped_bounds[3]:
            raise ValueError("裁切矢量与输出范围没有交集")
        return clipped_bounds

    @classmethod
    def _build_clip_mask(
        cls,
        clip_geometry: ClipGeometry,
        output_grid: SpatialGrid,
    ) -> np.ndarray:
        if output_grid.crs is None:
            raise ValueError("输出网格缺少坐标系，无法按矢量掩膜")
        geometry = cls._transform_geometry(clip_geometry.geometry, clip_geometry.crs, output_grid.crs)
        return geometry_mask(
            [mapping(geometry)],
            out_shape=(output_grid.height, output_grid.width),
            transform=output_grid.transform,
            invert=False,
        )

    @classmethod
    def _resolve_reference_mask(
        cls,
        mask_source: RasterMaskSource,
        output_grid: SpatialGrid,
    ) -> np.ndarray:
        if mask_source.grid.is_equivalent(output_grid):
            return np.asarray(mask_source.mask, dtype=bool)
        if mask_source.grid.crs is None or output_grid.crs is None:
            raise ValueError("参考掩膜或输出网格缺少坐标系，无法对齐掩膜")
        destination = np.zeros((output_grid.height, output_grid.width), dtype=np.uint8)
        reproject(
            source=np.asarray(mask_source.mask, dtype=np.uint8),
            destination=destination,
            src_transform=mask_source.grid.transform,
            src_crs=mask_source.grid.crs,
            dst_transform=output_grid.transform,
            dst_crs=output_grid.crs,
            resampling=Resampling.nearest,
        )
        return destination.astype(bool)

    @classmethod
    def _collect_spatial_contexts(
        cls,
        dataset: Dataset,
        variable_filter: Iterable[str],
    ) -> list[SpatialVariableContext]:
        filter_set = {name for name in variable_filter if name}
        contexts: list[SpatialVariableContext] = []
        for variable_name, variable in dataset.variables.items():
            if filter_set and variable_name not in filter_set:
                continue
            context = cls._build_spatial_context(dataset, variable_name, variable)
            if context is not None:
                contexts.append(context)
        return contexts

    @classmethod
    def _build_spatial_context(cls, dataset: Dataset, variable_name: str, variable) -> SpatialVariableContext | None:
        if getattr(variable, "ndim", 0) < 2:
            return None

        dim_types = [cls._infer_axis_type(dataset, dimension_name) for dimension_name in variable.dimensions]
        x_candidates = [index for index, axis_type in enumerate(dim_types) if axis_type == "x"]
        y_candidates = [index for index, axis_type in enumerate(dim_types) if axis_type == "y"]
        if not x_candidates or not y_candidates:
            return None

        x_axis = x_candidates[-1]
        y_axis = y_candidates[-1]
        if x_axis == y_axis:
            return None

        x_dim = variable.dimensions[x_axis]
        y_dim = variable.dimensions[y_axis]
        x_values = cls._resolve_coordinate_values(dataset, x_dim)
        y_values = cls._resolve_coordinate_values(dataset, y_dim)
        if x_values is None or y_values is None:
            return None

        grid_mapping_name = getattr(variable, "grid_mapping", None)
        crs = cls._infer_variable_crs(dataset, variable, x_dim, y_dim, grid_mapping_name)
        source_grid, x_reverse, y_reverse = cls._build_source_grid(x_dim, y_dim, x_values, y_values, crs)
        return SpatialVariableContext(
            name=variable_name,
            dimensions=tuple(variable.dimensions),
            shape=tuple(variable.shape),
            x_dim=x_dim,
            y_dim=y_dim,
            x_axis=x_axis,
            y_axis=y_axis,
            source_grid=source_grid,
            x_reverse=x_reverse,
            y_reverse=y_reverse,
            grid_mapping_name=grid_mapping_name,
        )

    @classmethod
    def _build_source_grid(
        cls,
        x_dim: str,
        y_dim: str,
        x_values: np.ndarray,
        y_values: np.ndarray,
        crs: CRS | None,
    ) -> tuple[SpatialGrid, bool, bool]:
        x_coords = np.asarray(x_values, dtype=np.float64).copy()
        y_coords = np.asarray(y_values, dtype=np.float64).copy()
        if x_coords.ndim != 1 or y_coords.ndim != 1:
            raise ValueError("仅支持 1 维规则网格坐标")
        if x_coords.size < 2 or y_coords.size < 2:
            raise ValueError("空间维度长度至少需要为 2")

        x_reverse = False
        if x_coords[0] > x_coords[-1]:
            x_coords = x_coords[::-1]
            x_reverse = True

        y_reverse = False
        if y_coords[0] < y_coords[-1]:
            y_coords = y_coords[::-1]
            y_reverse = True

        x_res = cls._validate_even_spacing(x_coords, x_dim)
        y_res = cls._validate_even_spacing(y_coords, y_dim)
        transform = from_origin(x_coords[0] - x_res / 2.0, y_coords[0] + y_res / 2.0, x_res, y_res)
        x_name, y_name = cls._derive_output_dim_names_from_coords(x_dim, y_dim, crs)
        grid = SpatialGrid(width=x_coords.size, height=y_coords.size, transform=transform, crs=crs, x_name=x_name, y_name=y_name)
        return grid, x_reverse, y_reverse

    @classmethod
    def _infer_variable_crs(
        cls,
        dataset: Dataset,
        variable,
        x_dim: str,
        y_dim: str,
        grid_mapping_name: str | None,
    ) -> CRS | None:
        if grid_mapping_name and grid_mapping_name in dataset.variables:
            grid_mapping_var = dataset.variables[grid_mapping_name]
            attrs = {name: grid_mapping_var.getncattr(name) for name in grid_mapping_var.ncattrs()}
            try:
                return CRS.from_cf(attrs)
            except Exception:
                pass
            for attr_name in ("spatial_ref", "crs_wkt", "wkt"):
                attr_value = attrs.get(attr_name)
                if attr_value:
                    try:
                        return CRS.from_user_input(attr_value)
                    except Exception:
                        pass

        for candidate_name in ("spatial_ref", "crs"):
            if candidate_name not in dataset.variables:
                continue
            crs_var = dataset.variables[candidate_name]
            for attr_name in ("spatial_ref", "crs_wkt", "wkt"):
                attr_value = getattr(crs_var, attr_name, None)
                if attr_value:
                    try:
                        return CRS.from_user_input(attr_value)
                    except Exception:
                        pass

        if cls._looks_geographic_axis(x_dim) and cls._looks_geographic_axis(y_dim):
            return CRS.from_epsg(4326)

        return None

    @classmethod
    def _infer_axis_type(cls, dataset: Dataset, dimension_name: str) -> str | None:
        dimension_key = dimension_name.lower()
        if dimension_key in cls.X_ALIASES:
            return "x"
        if dimension_key in cls.Y_ALIASES:
            return "y"

        variable = dataset.variables.get(dimension_name)
        if variable is None:
            return None

        axis_attr = str(getattr(variable, "axis", "")).lower()
        if axis_attr == "x":
            return "x"
        if axis_attr == "y":
            return "y"

        standard_name = str(getattr(variable, "standard_name", "")).lower()
        if standard_name in cls.X_ALIASES:
            return "x"
        if standard_name in cls.Y_ALIASES:
            return "y"

        units = str(getattr(variable, "units", "")).lower()
        if "degrees_east" in units or "degree_east" in units:
            return "x"
        if "degrees_north" in units or "degree_north" in units:
            return "y"

        if cls._looks_geographic_axis(dimension_name):
            if any(name in dimension_key for name in cls.GEOGRAPHIC_X_NAMES):
                return "x"
            if any(name in dimension_key for name in cls.GEOGRAPHIC_Y_NAMES):
                return "y"
        return None

    @classmethod
    def _resolve_coordinate_values(cls, dataset: Dataset, dimension_name: str) -> np.ndarray | None:
        variable = dataset.variables.get(dimension_name)
        if variable is None or getattr(variable, "ndim", 0) != 1:
            return None
        if variable.shape[0] < 2:
            return None
        if getattr(variable.dtype, "kind", "") not in {"f", "i", "u"}:
            return None
        return np.asarray(variable[:], dtype=np.float64)

    @classmethod
    def _create_spatial_coord_vars(
        cls,
        dataset: Dataset,
        grid: SpatialGrid,
        x_name: str,
        y_name: str,
    ) -> None:
        x_var = dataset.createVariable(x_name, "f8", (x_name,))
        y_var = dataset.createVariable(y_name, "f8", (y_name,))
        x_var[:] = grid.x_values
        y_var[:] = grid.y_values

        if grid.crs and grid.crs.is_geographic:
            x_var.standard_name = "longitude"
            x_var.long_name = "longitude"
            x_var.units = "degrees_east"
            y_var.standard_name = "latitude"
            y_var.long_name = "latitude"
            y_var.units = "degrees_north"
        else:
            x_var.standard_name = "projection_x_coordinate"
            x_var.long_name = "x coordinate of projection"
            x_var.units = "metre"
            y_var.standard_name = "projection_y_coordinate"
            y_var.long_name = "y coordinate of projection"
            y_var.units = "metre"

        if grid.crs is None:
            return

        spatial_ref = dataset.createVariable("spatial_ref", "i4")
        spatial_ref.spatial_ref = grid.crs.to_wkt()
        spatial_ref.crs_wkt = grid.crs.to_wkt()
        try:
            cf_attrs = grid.crs.to_cf()
        except Exception:
            cf_attrs = {}
        for name, value in cf_attrs.items():
            spatial_ref.setncattr(name, value)

    @classmethod
    def _create_output_variable(
        cls,
        dataset: Dataset,
        variable_name: str,
        source_variable,
        dimensions: tuple[str, ...],
        fill_value: float | int | None,
        processed: bool,
        dtype_override=None,
    ):
        dtype_code = dtype_override if dtype_override is not None else source_variable.datatype
        if isinstance(dtype_code, np.dtype):
            dtype_code = cls._netcdf_dtype_code(dtype_code)
        create_kwargs = {}
        if fill_value is not None and np.dtype(source_variable.dtype).kind in {"i", "u", "f"}:
            create_kwargs["fill_value"] = fill_value
        dst_var = dataset.createVariable(variable_name, dtype_code, dimensions, **create_kwargs)

        ignored_attrs = {"_FillValue"}
        if processed:
            ignored_attrs.update({"missing_value", "grid_mapping"})
        for attr_name in source_variable.ncattrs():
            if attr_name in ignored_attrs:
                continue
            dst_var.setncattr(attr_name, source_variable.getncattr(attr_name))

        if processed and "spatial_ref" in dataset.variables:
            dst_var.setncattr("grid_mapping", "spatial_ref")
            if fill_value is not None:
                dst_var.setncattr("missing_value", fill_value)
        return dst_var

    @classmethod
    def _write_nc_slice(cls, variable, context: SpatialVariableContext, leading_index: tuple[int, ...], data: np.ndarray) -> None:
        output_slices = [slice(None)] * len(context.dimensions)
        leading_axes = [axis for axis in range(len(context.dimensions)) if axis not in {context.y_axis, context.x_axis}]
        for axis, index_value in zip(leading_axes, leading_index):
            output_slices[axis] = index_value
        output_slices[context.y_axis] = slice(None)
        output_slices[context.x_axis] = slice(None)
        variable[tuple(output_slices)] = data

    @classmethod
    def _write_tif(
        cls,
        output_path: str,
        data: np.ndarray,
        grid: SpatialGrid,
        dtype: np.dtype,
        nodata: float | int | None,
        band_descriptions: list[str] | None = None,
    ) -> None:
        array = np.asarray(data, dtype=dtype)
        if array.ndim == 2:
            array = array[np.newaxis, ...]
        profile = {
            "driver": "GTiff",
            "width": grid.width,
            "height": grid.height,
            "count": int(array.shape[0]),
            "dtype": np.dtype(dtype).name,
            "transform": grid.transform,
            "crs": grid.crs,
            "nodata": nodata,
        }
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(array)
            for band_index, description in enumerate(band_descriptions or [], start=1):
                if description:
                    dst.set_band_description(band_index, description)

    @classmethod
    def _normalize_spatial_axes(cls, array: np.ndarray, context: SpatialVariableContext) -> np.ndarray:
        result = array
        if context.x_reverse:
            result = np.flip(result, axis=context.x_axis)
        if context.y_reverse:
            result = np.flip(result, axis=context.y_axis)
        return result

    @classmethod
    def _build_tif_output_path(
        cls,
        variable_name: str,
        split_key: tuple[tuple[str, str], ...],
        tif_dir: str,
    ) -> str:
        suffix = cls._split_key_suffix(split_key)
        if suffix:
            filename = f"{cls._sanitize_filename(variable_name)}_{suffix}.tif"
        else:
            filename = f"{cls._sanitize_filename(variable_name)}.tif"
        return os.path.join(tif_dir, filename)

    @classmethod
    def _split_key_suffix(cls, split_key: tuple[tuple[str, str], ...]) -> str:
        if not split_key:
            return ""
        return "_".join(f"{cls._sanitize_filename(dim_name)}_{cls._sanitize_filename(str(index_value))}" for dim_name, index_value in split_key)

    @classmethod
    def _resolve_tif_split_positions(cls, leading_dim_names: list[str], requested_split_dims: tuple[str, ...]) -> list[int]:
        if not leading_dim_names:
            return []
        if not requested_split_dims:
            return list(range(len(leading_dim_names)))
        requested = {dim for dim in requested_split_dims if dim}
        return [position for position, dim_name in enumerate(leading_dim_names) if dim_name in requested]

    @classmethod
    def _partition_tif_indices(
        cls,
        leading_dim_names: list[str],
        leading_index: tuple[int, ...],
        split_positions: list[int],
        dataset: Dataset,
    ) -> tuple[tuple[tuple[str, str], ...], str]:
        split_key_parts: list[tuple[str, str]] = []
        band_parts: list[str] = []
        for position, (dim_name, index_value) in enumerate(zip(leading_dim_names, leading_index)):
            value_label = cls._slice_value_label(dataset, dim_name, index_value)
            if position in split_positions:
                split_key_parts.append((dim_name, value_label))
            else:
                band_parts.append(f"{cls._sanitize_filename(dim_name)}_{value_label}")
        band_label = "_".join(band_parts) if band_parts else "band_1"
        return tuple(split_key_parts), band_label

    @classmethod
    def _slice_value_label(cls, dataset: Dataset, dim_name: str, index_value: int) -> str:
        variable = dataset.variables.get(dim_name)
        if variable is not None and getattr(variable, "ndim", 0) == 1 and len(variable) > index_value:
            value = variable[index_value]
            value_array = np.asarray(value)
            value_text = str(value_array.item() if value_array.shape == () else value)
            return cls._sanitize_filename(value_text)
        return f"{index_value:03d}"

    @classmethod
    def _collect_input_files(cls, input_path: str, recursive: bool) -> list[str]:
        path = Path(input_path)
        if path.is_file():
            if path.suffix.lower() != ".nc":
                raise ValueError("输入文件必须是 .nc")
            return [str(path)]
        if not path.is_dir():
            raise ValueError("输入路径不存在")

        pattern = "**/*.nc" if recursive else "*.nc"
        return [str(item) for item in sorted(path.glob(pattern)) if item.is_file()]

    @classmethod
    def _relative_output_base(cls, root_input: str, input_file: str, output_dir: str, suffix: str) -> str:
        input_path = Path(input_file)
        root_path = Path(root_input)
        if root_path.is_dir():
            relative = input_path.relative_to(root_path)
            relative_no_suffix = relative.with_suffix("")
            return str(Path(output_dir) / relative_no_suffix.parent / f"{relative_no_suffix.name}_{suffix}")
        return str(Path(output_dir) / f"{input_path.stem}_{suffix}")

    @classmethod
    def _ensure_nc_grid_compatibility(
        cls,
        contexts: list[SpatialVariableContext],
        options: NCRasterBatchOptions,
        reference_grid: SpatialGrid | None,
        clip_geometry: ClipGeometry | None,
    ) -> None:
        if len(contexts) < 2:
            return
        first_grid = cls._build_output_grid(contexts[0].source_grid, options, reference_grid, clip_geometry)
        for context in contexts[1:]:
            current_grid = cls._build_output_grid(context.source_grid, options, reference_grid, clip_geometry)
            if not first_grid.is_equivalent(current_grid):
                raise ValueError("检测到多个空间网格，单个输出 nc 无法同时容纳，请改用 TIFF 输出")

    @classmethod
    def _derive_output_dim_names(cls, grid: SpatialGrid) -> tuple[str, str]:
        return cls._derive_output_dim_names_from_crs(grid.crs)

    @classmethod
    def _derive_output_dim_names_from_crs(cls, crs: CRS | None) -> tuple[str, str]:
        if crs and crs.is_geographic:
            return "lon", "lat"
        return "x", "y"

    @classmethod
    def _derive_output_dim_names_from_coords(cls, x_dim: str, y_dim: str, crs: CRS | None) -> tuple[str, str]:
        if crs and crs.is_geographic:
            return "lon", "lat"
        if cls._looks_geographic_axis(x_dim) and cls._looks_geographic_axis(y_dim):
            return "lon", "lat"
        return "x", "y"

    @classmethod
    def _looks_geographic_axis(cls, name: str) -> bool:
        lowered = name.lower()
        return any(alias in lowered for alias in cls.GEOGRAPHIC_X_NAMES | cls.GEOGRAPHIC_Y_NAMES)

    @staticmethod
    def _validate_even_spacing(values: np.ndarray, dim_name: str) -> float:
        diffs = np.diff(values)
        if not np.all(np.isfinite(diffs)):
            raise ValueError(f"维度 {dim_name} 含非法坐标值")
        abs_diffs = np.abs(diffs)
        mean_diff = float(abs_diffs.mean())
        if mean_diff <= 0:
            raise ValueError(f"维度 {dim_name} 无法推断分辨率")
        if not np.allclose(abs_diffs, mean_diff, rtol=1e-5, atol=1e-8):
            raise ValueError(f"维度 {dim_name} 不是等间距规则网格，当前工具暂不支持")
        return mean_diff

    @staticmethod
    def _parse_crs(text: str) -> CRS:
        return CRS.from_user_input(text)

    @classmethod
    def _resampling_enum(cls, value: str) -> Resampling:
        try:
            return getattr(Resampling, value)
        except AttributeError as exc:
            raise ValueError(f"不支持的重采样方法: {value}") from exc

    @staticmethod
    def _default_fill_value(dtype: np.dtype, nodata: float | int | None):
        if nodata is not None:
            return nodata
        if np.dtype(dtype).kind == "f":
            return np.nan
        return 0

    @staticmethod
    def _resolve_output_dtype(source_dtype: np.dtype, nodata: float | int | None) -> np.dtype:
        dtype = np.dtype(source_dtype)
        if dtype.kind == "f":
            return dtype
        if nodata is None:
            return np.dtype("float32")
        if dtype.kind == "u" and float(nodata) < 0:
            return np.dtype("float32")
        return dtype

    @staticmethod
    def _extract_fill_value(variable) -> float | int | None:
        for attr_name in ("_FillValue", "missing_value"):
            if hasattr(variable, attr_name):
                value = getattr(variable, attr_name)
                try:
                    return np.asarray(value).item()
                except Exception:
                    return value
        return None

    @classmethod
    def _resolve_src_nodata(cls, variable) -> float | int | None:
        return cls._extract_fill_value(variable)

    @classmethod
    def _resolve_dst_nodata(cls, variable, override_nodata: float | int | None) -> float | int | None:
        if override_nodata is not None:
            return override_nodata
        fill_value = cls._extract_fill_value(variable)
        if fill_value is not None:
            return fill_value
        dtype = np.dtype(variable.dtype)
        if dtype.kind == "f":
            return np.nan
        return -9999 if dtype.kind == "i" else None

    @staticmethod
    def _apply_dst_nodata(
        array: np.ndarray,
        src_nodata: float | int | None,
        dst_nodata: float | int | None,
    ) -> np.ndarray:
        result = np.asarray(array).copy()
        if src_nodata is None or dst_nodata is None:
            return result
        mask = np.isclose(result, src_nodata, equal_nan=True) if np.issubdtype(result.dtype, np.floating) else result == src_nodata
        result[mask] = dst_nodata
        return result

    @staticmethod
    def _apply_external_mask(
        array: np.ndarray,
        mask: np.ndarray,
        dst_nodata: float | int | None,
    ) -> np.ndarray:
        if array.shape != mask.shape:
            raise ValueError("参考掩膜尺寸与输出栅格不一致")
        result = np.asarray(array).copy()
        fill_value = dst_nodata if dst_nodata is not None else (np.nan if np.issubdtype(result.dtype, np.floating) else 0)
        result[mask] = fill_value
        return result

    @staticmethod
    def _transform_geometry(geometry, source_crs: CRS, target_crs: CRS):
        if source_crs == target_crs:
            return geometry
        transformed = gpd.GeoSeries([geometry], crs=source_crs.to_string()).to_crs(target_crs.to_string())
        return transformed.iloc[0]

    @staticmethod
    def _netcdf_dtype_code(dtype: np.dtype) -> str:
        resolved = np.dtype(dtype)
        if resolved.kind == "f":
            return "f8" if resolved.itemsize > 4 else "f4"
        if resolved.kind == "i":
            return {1: "i1", 2: "i2", 4: "i4", 8: "i8"}.get(resolved.itemsize, "i4")
        if resolved.kind == "u":
            return {1: "u1", 2: "u2", 4: "u4", 8: "u8"}.get(resolved.itemsize, "u4")
        return "f4"

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        text = re.sub(r"[^\w.\-]+", "_", str(value).strip(), flags=re.UNICODE)
        return text.strip("._") or "item"

    @staticmethod
    def _ensure_directory(path: str) -> None:
        if path:
            os.makedirs(path, exist_ok=True)
