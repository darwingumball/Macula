"""
Prepare a georeferenced satellite mosaic for a lat/lon bounding box.

Usage:
    python tools/prepare_region.py \
        --lat-min 37.75 --lat-max 37.80 \
        --lon-min -122.45 --lon-max -122.40 \
        --zoom 17 \
        --output region/
"""

import argparse
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np


def latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_latlon(x: int, y: int, zoom: int) -> tuple[float, float]:
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def gsd_at_zoom(zoom: int, lat: float) -> float:
    """Ground sample distance in meters per pixel at given zoom and latitude."""
    earth_circumference = 40075016.686
    return earth_circumference * math.cos(math.radians(lat)) / (256 * 2 ** zoom)


def fetch_tile(x: int, y: int, zoom: int, cache_dir: Path) -> np.ndarray | None:
    cache_path = cache_dir / f"{zoom}_{x}_{y}.png"
    if cache_path.exists():
        img = cv2.imread(str(cache_path))
        if img is not None:
            return img

    # ESRI World Imagery — free satellite tiles, no API key required
    # Axis order is z/row/col i.e. z/y/x (opposite of OSM)
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
    headers = {"User-Agent": "VPS-Inertial/1.0 mosaic-builder", "Referer": "https://www.arcgis.com"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            cv2.imwrite(str(cache_path), img)
        return img
    except Exception as e:
        print(f"  Warning: failed to fetch tile {zoom}/{x}/{y}: {e}", file=sys.stderr)
        return None


def build_mosaic(
    lat_min: float, lat_max: float,
    lon_min: float, lon_max: float,
    zoom: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / ".tile_cache"
    cache_dir.mkdir(exist_ok=True)

    x_min, y_max = latlon_to_tile(lat_min, lon_min, zoom)
    x_max, y_min = latlon_to_tile(lat_max, lon_max, zoom)

    x_min, x_max = min(x_min, x_max), max(x_min, x_max)
    y_min, y_max = min(y_min, y_max), max(y_min, y_max)

    nx = x_max - x_min + 1
    ny = y_max - y_min + 1
    print(f"Fetching {nx * ny} tiles ({nx}x{ny}) at zoom {zoom}...")

    tile_size = 256
    mosaic = np.zeros((ny * tile_size, nx * tile_size, 3), dtype=np.uint8)

    for yi, y in enumerate(range(y_min, y_max + 1)):
        for xi, x in enumerate(range(x_min, x_max + 1)):
            print(f"  Tile {xi+1+yi*nx}/{nx*ny}: {zoom}/{x}/{y}", end="\r")
            tile = fetch_tile(x, y, zoom, cache_dir)
            if tile is None:
                continue
            row0 = yi * tile_size
            col0 = xi * tile_size
            mosaic[row0:row0+tile_size, col0:col0+tile_size] = tile

    print()

    origin_lat, origin_lon = tile_to_latlon(x_min, y_min, zoom)
    gsd = gsd_at_zoom(zoom, (lat_min + lat_max) / 2.0)
    h, w = mosaic.shape[:2]

    mosaic_path = output_dir / "satellite.png"
    cv2.imwrite(str(mosaic_path), mosaic)
    print(f"Mosaic saved: {mosaic_path} ({w}x{h} px)")

    meta = {
        "origin_lat": origin_lat,
        "origin_lon": origin_lon,
        "gsd_m_per_px": gsd,
        "width_px": w,
        "height_px": h,
        "zoom": zoom,
    }
    meta_path = output_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved: {meta_path}")
    print(f"GSD: {gsd:.4f} m/px  Origin: ({origin_lat:.6f}, {origin_lon:.6f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare satellite mosaic for VPS")
    parser.add_argument("--lat-min", type=float, required=True)
    parser.add_argument("--lat-max", type=float, required=True)
    parser.add_argument("--lon-min", type=float, required=True)
    parser.add_argument("--lon-max", type=float, required=True)
    parser.add_argument("--zoom", type=int, default=17)
    parser.add_argument("--output", type=str, default="region/")
    args = parser.parse_args()

    build_mosaic(
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        lon_min=args.lon_min,
        lon_max=args.lon_max,
        zoom=args.zoom,
        output_dir=Path(args.output),
    )


if __name__ == "__main__":
    main()
