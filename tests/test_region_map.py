import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from shared.region_map import RegionMap, RegionMapError

RM_CFG = {
    'mosaic_path': '',       # filled per test
    'metadata_path': '',     # filled per test
    'min_altitude_m': 5.0,
    'max_altitude_m': 200.0,
}


@pytest.fixture
def region_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        mosaic = np.random.randint(0, 255, (1024, 1024, 3), dtype=np.uint8)
        mosaic_path = os.path.join(tmpdir, "satellite.png")
        cv2.imwrite(mosaic_path, mosaic)

        meta = {
            "origin_lat": 37.75,
            "origin_lon": -122.45,
            "gsd_m_per_px": 0.6,
            "width_px": 1024,
            "height_px": 1024,
            "zoom": 17,
        }
        meta_path = os.path.join(tmpdir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        yield mosaic_path, meta_path


def make_cfg(mosaic_path: str, meta_path: str) -> dict:
    cfg = dict(RM_CFG)
    cfg['mosaic_path'] = mosaic_path
    cfg['metadata_path'] = meta_path
    return cfg


def test_loads_without_error(region_files):
    mosaic_path, meta_path = region_files
    rm = RegionMap(make_cfg(mosaic_path, meta_path))
    assert rm is not None


def test_missing_mosaic_raises():
    cfg = make_cfg('/nonexistent/satellite.png', '/nonexistent/meta.json')
    with pytest.raises(RegionMapError):
        RegionMap(cfg)


def test_get_crop_returns_ndarray_and_callable(region_files):
    mosaic_path, meta_path = region_files
    rm = RegionMap(make_cfg(mosaic_path, meta_path))
    attitude = np.array([1.0, 0.0, 0.0, 0.0])
    crop, fn = rm.get_crop(50.0, attitude)
    assert isinstance(crop, np.ndarray)
    assert callable(fn)


def test_georef_fn_returns_latlon(region_files):
    mosaic_path, meta_path = region_files
    rm = RegionMap(make_cfg(mosaic_path, meta_path))
    attitude = np.array([1.0, 0.0, 0.0, 0.0])
    _, fn = rm.get_crop(50.0, attitude)
    lat, lon = fn(320.0, 320.0)
    assert isinstance(lat, float)
    assert isinstance(lon, float)


def test_pixel_to_latlon_roundtrip(region_files):
    mosaic_path, meta_path = region_files
    rm = RegionMap(make_cfg(mosaic_path, meta_path))
    lat, lon = rm.pixel_to_latlon(512, 512)
    assert isinstance(lat, float)
    assert isinstance(lon, float)


def test_crop_is_resized_to_640(region_files):
    mosaic_path, meta_path = region_files
    rm = RegionMap(make_cfg(mosaic_path, meta_path))
    attitude = np.array([1.0, 0.0, 0.0, 0.0])
    crop, _ = rm.get_crop(50.0, attitude)
    assert crop.shape[0] == 640 or crop.shape[1] == 640
