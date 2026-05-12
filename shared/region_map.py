import json
import logging
import math
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class RegionMapError(Exception):
    pass


class RegionMap:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        mosaic_path = Path(config['mosaic_path'])
        metadata_path = Path(config['metadata_path'])

        if not mosaic_path.exists():
            raise RegionMapError(f"Mosaic not found: {mosaic_path}")
        if not metadata_path.exists():
            raise RegionMapError(f"Metadata not found: {metadata_path}")

        self._mosaic = cv2.imread(str(mosaic_path))
        if self._mosaic is None:
            raise RegionMapError(f"Failed to load mosaic: {mosaic_path}")

        with open(metadata_path) as f:
            self._meta = json.load(f)

        self._origin_lat: float = self._meta['origin_lat']
        self._origin_lon: float = self._meta['origin_lon']
        self._gsd: float = self._meta['gsd_m_per_px']
        self._w: int = self._meta['width_px']
        self._h: int = self._meta['height_px']

        logger.debug(
            "RegionMap loaded %dx%d mosaic GSD=%.4f m/px origin=(%.6f,%.6f)",
            self._w, self._h, self._gsd, self._origin_lat, self._origin_lon,
        )

    def get_crop(
        self,
        altitude_m: float,
        attitude_q: np.ndarray,
        fov_deg: float = 90.0,
        crop_size: int = 640,
    ) -> tuple[np.ndarray, Callable[[float, float], tuple[float, float]]]:
        altitude_m = float(np.clip(
            altitude_m,
            self._cfg['min_altitude_m'],
            self._cfg['max_altitude_m'],
        ))

        center_px, footprint_px = self._compute_footprint(
            altitude_m, attitude_q, fov_deg
        )

        cx, cy = int(round(center_px[0])), int(round(center_px[1]))
        half = footprint_px // 2

        x0 = max(0, cx - half)
        y0 = max(0, cy - half)
        x1 = min(self._w, cx + half)
        y1 = min(self._h, cy + half)

        crop = self._mosaic[y0:y1, x0:x1]
        if crop.size == 0:
            raise RegionMapError("Crop is empty — position outside mosaic bounds")

        scale = crop_size / max(crop.shape[0], crop.shape[1])
        crop_resized = cv2.resize(crop, (crop_size, crop_size))

        def georef_fn(pixel_x: float, pixel_y: float) -> tuple[float, float]:
            map_px = x0 + pixel_x / scale
            map_py = y0 + pixel_y / scale
            return self.pixel_to_latlon(map_px, map_py)

        return crop_resized, georef_fn

    def _compute_footprint(
        self,
        altitude_m: float,
        attitude_q: np.ndarray,
        fov_deg: float,
    ) -> tuple[np.ndarray, int]:
        # Rotate camera boresight through body-to-world to find ground center
        boresight_cam = np.array([0.0, 0.0, 1.0])
        boresight_world = _rotate_vector(attitude_q, boresight_cam)

        # Ground intersection: scale so z-component reaches altitude
        if abs(boresight_world[2]) < 1e-6:
            boresight_world = np.array([0.0, 0.0, 1.0])
        scale_to_ground = altitude_m / boresight_world[2]
        ground_offset_m = boresight_world * scale_to_ground

        # Convert ground offset (NED) to pixel offset on mosaic
        north_m, east_m = ground_offset_m[0], ground_offset_m[1]
        origin_px = self._latlon_to_pixel(self._origin_lat, self._origin_lon)
        center_north_px = origin_px[1] - north_m / self._gsd
        center_east_px = origin_px[0] + east_m / self._gsd
        center_px = np.array([center_east_px, center_north_px])

        half_fov_rad = math.radians(fov_deg / 2.0)
        footprint_m = 2.0 * altitude_m * math.tan(half_fov_rad)
        footprint_px = int(footprint_m / self._gsd)

        return center_px, max(footprint_px, 64)

    def _latlon_to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        north_m = (lat - self._origin_lat) * 111320.0
        east_m = (lon - self._origin_lon) * 111320.0 * math.cos(math.radians(self._origin_lat))
        px = east_m / self._gsd
        py = -north_m / self._gsd
        return px, py

    def pixel_to_latlon(self, px: float, py: float) -> tuple[float, float]:
        east_m = px * self._gsd
        north_m = -py * self._gsd
        lat = self._origin_lat + north_m / 111320.0
        lon = self._origin_lon + east_m / (111320.0 * math.cos(math.radians(self._origin_lat)))
        return lat, lon

    @property
    def metadata(self) -> dict:
        return dict(self._meta)


def _rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vector v by quaternion q (scalar-first w,x,y,z)."""
    w, x, y, z = q / np.linalg.norm(q)
    # Rodrigues via quaternion sandwich: q * [0,v] * q_conj
    t = 2.0 * np.cross(np.array([x, y, z]), v)
    return v + w * t + np.cross(np.array([x, y, z]), t)
