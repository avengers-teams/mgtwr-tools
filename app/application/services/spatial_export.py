from __future__ import annotations

import re

import geopandas as gpd
import pandas as pd


class CoefficientsSpatialExporter:
    FIELD_ALIASES = {
        "经度": "lon",
        "纬度": "lat",
        "年份": "year",
        "时间": "time",
        "日期": "date",
        "重力值": "value",
        "省份": "province",
        "城市": "city",
    }

    @staticmethod
    def load_excel_sheet(path: str, sheet_name: str | None = None) -> tuple[pd.DataFrame, list[str], str]:
        workbook = pd.ExcelFile(path)
        resolved_sheet = sheet_name
        if not resolved_sheet:
            resolved_sheet = "coefficients" if "coefficients" in workbook.sheet_names else workbook.sheet_names[0]
        dataframe = workbook.parse(resolved_sheet)
        dataframe.columns = [str(column).strip() for column in dataframe.columns]
        return dataframe, workbook.sheet_names, resolved_sheet

    @staticmethod
    def numeric_candidate_columns(dataframe: pd.DataFrame) -> list[str]:
        columns = []
        for column in dataframe.columns:
            if pd.to_numeric(dataframe[column], errors="coerce").notna().any():
                columns.append(str(column))
        return columns

    @classmethod
    def export_to_shp(
        cls,
        dataframe: pd.DataFrame,
        output_path: str,
        longitude_column: str,
        latitude_column: str,
        projection: str = "EPSG:4326",
    ) -> tuple[int, list[str]]:
        if longitude_column == latitude_column:
            raise ValueError("经度列和纬度列不能相同")
        missing_columns = [column for column in (longitude_column, latitude_column) if column not in dataframe.columns]
        if missing_columns:
            raise ValueError(f"缺少字段: {', '.join(missing_columns)}")

        export_frame = dataframe.copy()
        export_frame[longitude_column] = pd.to_numeric(export_frame[longitude_column], errors="coerce")
        export_frame[latitude_column] = pd.to_numeric(export_frame[latitude_column], errors="coerce")
        export_frame = export_frame.dropna(subset=[longitude_column, latitude_column]).reset_index(drop=True)
        if export_frame.empty:
            raise ValueError("经纬度列没有可用于导出的有效点数据")

        geo_frame = gpd.GeoDataFrame(
            export_frame,
            geometry=gpd.points_from_xy(export_frame[longitude_column], export_frame[latitude_column]),
            crs=projection,
        )

        renamed_columns = cls._sanitize_shapefile_columns([column for column in geo_frame.columns if column != "geometry"])
        geo_frame = geo_frame.rename(columns=renamed_columns)
        geo_frame.to_file(output_path, driver="ESRI Shapefile", encoding="utf-8")
        return len(geo_frame), list(renamed_columns.values())

    @staticmethod
    def _sanitize_shapefile_columns(columns: list[str]) -> dict[str, str]:
        rename_map = {}
        used = set()
        for index, original in enumerate(columns, start=1):
            original_text = str(original)
            candidate = original_text
            for source, target in CoefficientsSpatialExporter.FIELD_ALIASES.items():
                candidate = candidate.replace(source, target)
            candidate = re.sub(r"[^0-9A-Za-z_]", "_", candidate).strip("_")
            candidate = candidate or f"field{index}"
            candidate = candidate[:10]
            base = candidate
            counter = 1
            while candidate.lower() in used:
                suffix = str(counter)
                candidate = f"{base[:max(1, 10 - len(suffix))]}{suffix}"
                counter += 1
            used.add(candidate.lower())
            rename_map[original] = candidate
        return rename_map

