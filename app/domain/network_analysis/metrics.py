from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    from haversine import Unit, haversine_vector

    HAS_HAVERSINE = True
except ImportError:
    HAS_HAVERSINE = False


@dataclass
class NetworkMetrics:
    in_degree: Optional[np.ndarray] = None
    out_degree: Optional[np.ndarray] = None
    degree_diff: Optional[np.ndarray] = None
    strength_in: Optional[np.ndarray] = None
    strength_out: Optional[np.ndarray] = None
    dominant_in_direction: Optional[np.ndarray] = None
    dominant_out_direction: Optional[np.ndarray] = None
    propagation_distance_in: Optional[np.ndarray] = None
    propagation_distance_out: Optional[np.ndarray] = None
    reciprocity: Optional[float] = None


class ESNetwork:
    def __init__(
        self,
        es_matrix: Union[pd.DataFrame, np.ndarray],
        node_coordinates: Optional[Union[Dict[str, Tuple[float, float]], np.ndarray]] = None,
        threshold: float = 0.0,
    ):
        if isinstance(es_matrix, pd.DataFrame):
            self.matrix = es_matrix.values.astype(np.float32)
            self.node_names = list(es_matrix.columns)
        else:
            self.matrix = es_matrix.astype(np.float32)
            self.node_names = [f"node_{i}" for i in range(es_matrix.shape[0])]

        self.n_nodes = self.matrix.shape[0]
        self.threshold = threshold
        self.adj_matrix = (self.matrix > threshold).astype(np.int8)
        self.coordinates = self._resolve_coordinates(node_coordinates)
        self._angles: Optional[np.ndarray] = None
        self._distances: Optional[np.ndarray] = None
        self._graph_cache: Dict[Tuple[bool, bool], "nx.DiGraph"] = {}
        self._direction_metrics_cache: Dict[int, Dict[str, np.ndarray]] = {}
        self._coordinate_arrays: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None
        self.metrics = NetworkMetrics()

    def _resolve_coordinates(
        self,
        node_coordinates: Optional[Union[Dict[str, Tuple[float, float]], np.ndarray]],
    ) -> Dict[str, Tuple[float, float]]:
        if node_coordinates is None:
            return self._parse_coordinates_from_names()

        if isinstance(node_coordinates, dict):
            return node_coordinates

        if isinstance(node_coordinates, np.ndarray):
            if len(node_coordinates) == 0:
                return {}

            first_item = node_coordinates[0]
            if isinstance(first_item, (list, tuple, np.ndarray)) and len(first_item) == 2:
                return {
                    self.node_names[i]: tuple(node_coordinates[i])
                    for i in range(min(len(self.node_names), len(node_coordinates)))
                }

            if isinstance(first_item, str):
                self.node_names = list(node_coordinates)
                return self._parse_coordinates_from_names()

        raise TypeError("node_coordinates 必须为 dict、二维坐标数组、一维节点名数组或 None。")

    def _parse_coordinates_from_names(self) -> Dict[str, Tuple[float, float]]:
        coordinates: Dict[str, Tuple[float, float]] = {}
        for name in self.node_names:
            try:
                if isinstance(name, tuple) and len(name) >= 2:
                    lat, lon = float(name[0]), float(name[1])
                    coordinates[name] = (lat, lon)
                    continue

                name_str = str(name)
                if name_str.startswith("Pixel_") or name_str.startswith("pixel_"):
                    parts = name_str.split("_")
                    if len(parts) >= 3:
                        lon = float(parts[1])
                        lat = float(parts[2])
                        coordinates[name] = (lat, lon)
                    continue

                if "_" in name_str:
                    parts = name_str.split("_")
                    nums = []
                    for part in reversed(parts):
                        try:
                            nums.append(float(part.strip()))
                            if len(nums) >= 2:
                                break
                        except ValueError:
                            continue
                    if len(nums) >= 2:
                        lat, lon = nums[0], nums[1]
                        coordinates[name] = (lat, lon)
                    continue

                if "(" in name_str and ")" in name_str:
                    clean = name_str.replace("(", "").replace(")", "").replace(" ", "")
                    parts = clean.split(",")
                    if len(parts) >= 2:
                        lat = float(parts[0])
                        lon = float(parts[1])
                        coordinates[name] = (lat, lon)
            except (ValueError, IndexError, TypeError):
                continue
        return coordinates

    def _get_coordinate_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._coordinate_arrays is None:
            latitudes = np.full(self.n_nodes, np.nan, dtype=np.float64)
            longitudes = np.full(self.n_nodes, np.nan, dtype=np.float64)
            valid_mask = np.zeros(self.n_nodes, dtype=bool)
            if self.coordinates:
                for i, name in enumerate(self.node_names):
                    coord = self.coordinates.get(name)
                    if coord is None:
                        continue
                    latitudes[i], longitudes[i] = coord
                    valid_mask[i] = True
            self._coordinate_arrays = (latitudes, longitudes, valid_mask)
        return self._coordinate_arrays

    @property
    def angles(self) -> np.ndarray:
        if self._angles is None:
            self._compute_angles()
        return self._angles

    @property
    def distances(self) -> np.ndarray:
        if self._distances is None:
            self._compute_distances()
        return self._distances

    def _compute_angles(self) -> None:
        self._angles = np.zeros((self.n_nodes, self.n_nodes), dtype=np.float32)
        if not self.coordinates:
            return

        latitudes, longitudes, valid_mask = self._get_coordinate_arrays()
        valid_idx = np.flatnonzero(valid_mask)
        if valid_idx.size == 0:
            return

        lat = np.radians(latitudes[valid_idx])
        lon = np.radians(longitudes[valid_idx])
        phi1 = lat[:, None]
        phi2 = lat[None, :]
        lambda1 = lon[:, None]
        lambda2 = lon[None, :]

        numerator = np.sin(lambda2 - lambda1) * np.cos(phi2)
        denominator = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(lambda2 - lambda1)
        theta_ij = np.arctan2(numerator, denominator)
        angle_deg = np.degrees(theta_ij)
        angles = ((90.0 - angle_deg) % 360.0).astype(np.float32, copy=False)
        np.fill_diagonal(angles, 0.0)
        self._angles[np.ix_(valid_idx, valid_idx)] = angles

    def _compute_distances(self) -> None:
        self._distances = np.zeros((self.n_nodes, self.n_nodes), dtype=np.float64)
        if not self.coordinates:
            return

        latitudes, longitudes, valid_mask = self._get_coordinate_arrays()
        valid_idx = np.flatnonzero(valid_mask)
        if valid_idx.size == 0:
            return

        valid_points = list(zip(latitudes[valid_idx], longitudes[valid_idx]))
        if HAS_HAVERSINE:
            dist_matrix = haversine_vector(valid_points, valid_points, unit=Unit.METERS, comb=True)
            dist_matrix = np.asarray(dist_matrix, dtype=np.float64)
        else:
            phi = np.radians(latitudes[valid_idx])
            lam = np.radians(longitudes[valid_idx])
            dphi = phi[:, None] - phi[None, :]
            dlam = lam[:, None] - lam[None, :]
            phi1 = phi[:, None]
            phi2 = phi[None, :]
            a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2
            c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
            dist_matrix = 6371000.0 * c

        np.fill_diagonal(dist_matrix, 0.0)
        self._distances[np.ix_(valid_idx, valid_idx)] = dist_matrix

    def compute_metrics(self) -> NetworkMetrics:
        in_degree = self.matrix.sum(axis=0)
        out_degree = self.matrix.sum(axis=1)
        degree_diff = in_degree - out_degree
        self.metrics.in_degree = in_degree
        self.metrics.out_degree = out_degree
        self.metrics.degree_diff = degree_diff
        self.metrics.strength_in = in_degree.copy()
        self.metrics.strength_out = out_degree.copy()
        return self.metrics

    def compute_direction_metrics(self, n_sectors: int = 8) -> Dict[str, np.ndarray]:
        cached = self._direction_metrics_cache.get(n_sectors)
        if cached is not None:
            self.metrics.dominant_in_direction = cached["dominant_in_direction"]
            self.metrics.dominant_out_direction = cached["dominant_out_direction"]
            return cached

        sector_size = 360 / n_sectors
        angles = self.angles % 360
        edge_mask = self.adj_matrix.astype(bool, copy=False)
        sector_index = np.floor(angles / sector_size).astype(np.int16, copy=False)
        sector_index = np.clip(sector_index, 0, n_sectors - 1)
        weighted_matrix = self.matrix.astype(np.float64, copy=False)

        in_degree_by_sector = np.zeros((self.n_nodes, n_sectors), dtype=np.float64)
        out_degree_by_sector = np.zeros((self.n_nodes, n_sectors), dtype=np.float64)
        for sector in range(n_sectors):
            mask = edge_mask & (sector_index == sector)
            weighted_mask = np.where(mask, weighted_matrix, 0.0)
            out_degree_by_sector[:, sector] = weighted_mask.sum(axis=1)
            in_degree_by_sector[:, sector] = weighted_mask.sum(axis=0)

        dominant_in_direction = np.argmax(in_degree_by_sector, axis=1)
        dominant_out_direction = np.argmax(out_degree_by_sector, axis=1)
        dominant_in_direction[in_degree_by_sector.sum(axis=1) == 0] = -1
        dominant_out_direction[out_degree_by_sector.sum(axis=1) == 0] = -1

        direction_diff = np.abs(in_degree_by_sector - out_degree_by_sector)
        dominant_diff_direction = np.argmax(direction_diff, axis=1)
        dominant_diff_direction[direction_diff.sum(axis=1) == 0] = -1

        self.metrics.dominant_in_direction = dominant_in_direction
        self.metrics.dominant_out_direction = dominant_out_direction
        result = {
            "in_degree_by_sector": in_degree_by_sector,
            "out_degree_by_sector": out_degree_by_sector,
            "dominant_in_direction": dominant_in_direction,
            "dominant_out_direction": dominant_out_direction,
            "dominant_diff_direction": dominant_diff_direction,
        }
        self._direction_metrics_cache[n_sectors] = result
        return result

    def compute_propagation_distance(self, n_sectors: int = 8) -> Dict[str, np.ndarray]:
        direction_metrics = self.compute_direction_metrics(n_sectors)
        dominant_in = direction_metrics["dominant_in_direction"]
        dominant_out = direction_metrics["dominant_out_direction"]
        sector_size = 360 / n_sectors
        angles = self.angles % 360
        distances = self.distances
        edge_mask = self.adj_matrix.astype(bool, copy=False)
        sector_index = np.floor(angles / sector_size).astype(np.int16, copy=False)
        sector_index = np.clip(sector_index, 0, n_sectors - 1)

        dr_in = np.zeros(self.n_nodes, dtype=np.float64)
        dr_out = np.zeros(self.n_nodes, dtype=np.float64)
        mean_out_by_sector = np.zeros((self.n_nodes, n_sectors), dtype=np.float64)
        mean_in_by_sector = np.zeros((self.n_nodes, n_sectors), dtype=np.float64)

        for sector in range(n_sectors):
            mask = edge_mask & (sector_index == sector)
            count_out = mask.sum(axis=1)
            count_in = mask.sum(axis=0)
            sum_out = np.where(mask, distances, 0.0).sum(axis=1)
            sum_in = np.where(mask, distances, 0.0).sum(axis=0)
            valid_out = count_out > 0
            valid_in = count_in > 0
            mean_out_by_sector[valid_out, sector] = sum_out[valid_out] / count_out[valid_out]
            mean_in_by_sector[valid_in, sector] = sum_in[valid_in] / count_in[valid_in]

        valid_out_nodes = dominant_out >= 0
        valid_in_nodes = dominant_in >= 0
        dr_out[valid_out_nodes] = mean_out_by_sector[np.where(valid_out_nodes)[0], dominant_out[valid_out_nodes]]
        dr_in[valid_in_nodes] = mean_in_by_sector[np.where(valid_in_nodes)[0], dominant_in[valid_in_nodes]]
        self.metrics.propagation_distance_in = dr_in / 1000.0
        self.metrics.propagation_distance_out = dr_out / 1000.0
        return {
            "propagation_distance_in": dr_in,
            "propagation_distance_out": dr_out,
            "propagation_distance_in_km": dr_in / 1000.0,
            "propagation_distance_out_km": dr_out / 1000.0,
        }

    def to_dataframe_extended(self, n_sectors: int = 8) -> pd.DataFrame:
        metrics = self.compute_metrics()
        frame = pd.DataFrame(
            {
                "node": self.node_names,
                "in_degree": metrics.in_degree,
                "out_degree": metrics.out_degree,
                "degree_diff": metrics.degree_diff,
                "strength_in": metrics.strength_in,
                "strength_out": metrics.strength_out,
            }
        )

        if self.coordinates:
            latitudes = []
            longitudes = []
            for name in self.node_names:
                coord = self.coordinates.get(name)
                latitudes.append(coord[0] if coord else np.nan)
                longitudes.append(coord[1] if coord else np.nan)
            frame["latitude"] = latitudes
            frame["longitude"] = longitudes

        direction_metrics = self.compute_direction_metrics(n_sectors=n_sectors)
        propagation_metrics = self.compute_propagation_distance(n_sectors=n_sectors)
        frame["dominant_in_direction"] = direction_metrics["dominant_in_direction"]
        frame["dominant_out_direction"] = direction_metrics["dominant_out_direction"]
        frame["dominant_diff_direction"] = direction_metrics["dominant_diff_direction"]
        frame["propagation_distance_in_km"] = propagation_metrics["propagation_distance_in_km"]
        frame["propagation_distance_out_km"] = propagation_metrics["propagation_distance_out_km"]
        return frame

    def compute_reciprocity(self) -> float:
        if not HAS_NETWORKX:
            self.metrics.reciprocity = np.nan
            return self.metrics.reciprocity

        matrix = self.adj_matrix.astype(np.float32)
        graph = nx.from_numpy_array(matrix, create_using=nx.DiGraph())
        reciprocity = nx.reciprocity(graph)
        self.metrics.reciprocity = 0.0 if reciprocity is None else float(reciprocity)
        return self.metrics.reciprocity

    def all_extended_metrics_to_tiff(
        self,
        template_path: str,
        output_dir: str,
        n_sectors: int = 8,
        nodata: float = -9999.0,
        dtype_float: int = None,
        dtype_int: int = None,
    ) -> None:
        import os

        try:
            import rasterio
        except ImportError as exc:
            raise ImportError("导出 GeoTIFF 需要 rasterio。") from exc

        def resolve_output_array(values: np.ndarray, prefer_int: bool) -> np.ndarray:
            output = np.full((rows, cols), nodata, dtype=np.float32)
            for index, name in enumerate(self.node_names):
                coord = self.coordinates.get(name)
                if coord is None:
                    continue
                lat, lon = coord
                col_idx = int(np.floor((lon - x_origin) / pixel_width + 1e-6))
                row_idx = int(np.floor((lat - y_origin) / pixel_height + 1e-6))
                if 0 <= row_idx < rows and 0 <= col_idx < cols:
                    output[row_idx, col_idx] = values[index]

            if prefer_int:
                return output.astype(np.int16)
            return output.astype(np.float32)

        def write_tiff(values: np.ndarray, output_path: str, prefer_int: bool = False) -> None:
            if not self.coordinates:
                raise ValueError("节点坐标为空，无法映射到 TIFF。")

            output_array = resolve_output_array(values, prefer_int=prefer_int)
            profile = template_profile.copy()
            profile.update(
                dtype=str(output_array.dtype),
                count=1,
                nodata=int(nodata) if np.issubdtype(output_array.dtype, np.integer) else float(nodata),
                compress="lzw",
            )
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(output_array, 1)

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"无法打开模板文件: {template_path}")

        with rasterio.open(template_path) as template_ds:
            template_profile = template_ds.profile.copy()
            transform = template_ds.transform
            cols = template_ds.width
            rows = template_ds.height

        x_origin = transform.c
        y_origin = transform.f
        pixel_width = transform.a
        pixel_height = transform.e

        metrics = self.compute_metrics()
        direction_metrics = self.compute_direction_metrics(n_sectors=n_sectors)
        propagation_metrics = self.compute_propagation_distance(n_sectors=n_sectors)
        os.makedirs(output_dir, exist_ok=True)
        write_tiff(metrics.in_degree, os.path.join(output_dir, "in_degree.tif"))
        write_tiff(metrics.out_degree, os.path.join(output_dir, "out_degree.tif"))
        write_tiff(metrics.degree_diff, os.path.join(output_dir, "degree_diff.tif"))
        write_tiff(direction_metrics["dominant_in_direction"], os.path.join(output_dir, "dominant_in_direction.tif"), prefer_int=True)
        write_tiff(direction_metrics["dominant_out_direction"], os.path.join(output_dir, "dominant_out_direction.tif"), prefer_int=True)
        write_tiff(propagation_metrics["propagation_distance_in_km"], os.path.join(output_dir, "propagation_distance_in_km.tif"))
        write_tiff(propagation_metrics["propagation_distance_out_km"], os.path.join(output_dir, "propagation_distance_out_km.tif"))


def build_node_metrics_dataframe(network: ESNetwork, n_sectors: int = 8) -> pd.DataFrame:
    return network.to_dataframe_extended(n_sectors=n_sectors)


def build_network_summary(network: ESNetwork, compare_npz: str, metrics_df: pd.DataFrame) -> dict:
    n_nodes = int(network.n_nodes)
    n_edges = int(network.adj_matrix.sum())
    possible_edges = n_nodes * (n_nodes - 1)
    density = float(n_edges / possible_edges) if possible_edges > 0 else 0.0
    reciprocity = network.compute_reciprocity()
    active_nodes = ((metrics_df["in_degree"].to_numpy() + metrics_df["out_degree"].to_numpy()) > 0).sum()
    return {
        "compare_npz": compare_npz,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "density": density,
        "active_nodes": int(active_nodes),
        "weighted_edge_sum": float(network.matrix.sum()),
        "max_edge_weight": float(network.matrix.max()) if network.matrix.size else 0.0,
        "reciprocity": float(reciprocity) if not pd.isna(reciprocity) else np.nan,
    }
