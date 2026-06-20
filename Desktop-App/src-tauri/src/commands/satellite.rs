use anyhow::{anyhow, Result};
use image::{ImageBuffer, Rgb};
use serde::{Deserialize, Serialize};
use std::path::Path;
use tauri::{AppHandle, Emitter};

const MAX_TILES: u64 = 5_000;

#[derive(Serialize, Clone)]
pub struct DownloadProgress {
    pub current: u32,
    pub total: u32,
    pub percent: f32,
    pub tile_x: i32,
    pub tile_y: i32,
}

#[derive(Serialize)]
pub struct DownloadResult {
    pub mosaic_path: String,
    pub metadata_path: String,
    pub width_px: u32,
    pub height_px: u32,
    pub gsd_m_per_px: f64,
    pub origin_lat: f64,
    pub origin_lon: f64,
    pub tile_count: u32,
}

#[derive(Serialize)]
pub struct TileEstimate {
    pub tile_count: u32,
    pub nx: i32,
    pub ny: i32,
    pub estimated_mb: f64,
    pub gsd_m_per_px: f64,
    pub too_large: bool,
}

#[derive(Deserialize)]
pub struct BBox {
    pub lat_min: f64,
    pub lat_max: f64,
    pub lon_min: f64,
    pub lon_max: f64,
}

fn latlon_to_tile(lat: f64, lon: f64, zoom: u32) -> (i32, i32) {
    let n = (2u64.pow(zoom)) as f64;
    let x = ((lon + 180.0) / 360.0 * n) as i32;
    let lat_rad = lat.to_radians();
    let y = ((1.0 - (lat_rad.tan() + 1.0 / lat_rad.cos()).ln() / std::f64::consts::PI) / 2.0
        * n) as i32;
    (x, y)
}

fn tile_to_latlon(x: i32, y: i32, zoom: u32) -> (f64, f64) {
    let n = (2u64.pow(zoom)) as f64;
    let lon = x as f64 / n * 360.0 - 180.0;
    let lat_rad = (std::f64::consts::PI * (1.0 - 2.0 * y as f64 / n)).sinh().atan();
    (lat_rad.to_degrees(), lon)
}

fn gsd_at_zoom(zoom: u32, lat: f64) -> f64 {
    40075016.686 * lat.to_radians().cos() / (256.0 * 2u64.pow(zoom) as f64)
}

fn tile_to_quadkey(x: i32, y: i32, zoom: u32) -> String {
    (1..=zoom)
        .rev()
        .map(|i| {
            let mut d = 0u8;
            let mask = 1i32 << (i - 1);
            if x & mask != 0 { d += 1; }
            if y & mask != 0 { d += 2; }
            char::from_digit(d as u32, 10).unwrap()
        })
        .collect()
}

fn build_tile_url(source: &str, x: i32, y: i32, zoom: u32, api_key: Option<&str>) -> String {
    match source {
        "mapbox" => {
            let key = api_key.unwrap_or("");
            format!("https://api.mapbox.com/v4/mapbox.satellite/{zoom}/{x}/{y}.jpg90?access_token={key}")
        }
        "bing" => {
            let key = api_key.unwrap_or("");
            let qk = tile_to_quadkey(x, y, zoom);
            let sub = ((x.abs() + y.abs()) % 4) as u32;
            format!("https://t{sub}.ssl.ak.tiles.virtualearth.net/tiles/a{qk}.jpeg?g=7&token={key}")
        }
        _ => format!(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
        ),
    }
}

#[tauri::command]
pub fn estimate_tiles(bbox: BBox, zoom: u32) -> TileEstimate {
    let (x_min_raw, y_max_raw) = latlon_to_tile(bbox.lat_min, bbox.lon_min, zoom);
    let (x_max_raw, y_min_raw) = latlon_to_tile(bbox.lat_max, bbox.lon_max, zoom);
    let x_min = x_min_raw.min(x_max_raw);
    let x_max = x_min_raw.max(x_max_raw);
    let y_min = y_min_raw.min(y_max_raw);
    let y_max = y_min_raw.max(y_max_raw);
    let nx = x_max - x_min + 1;
    let ny = y_max - y_min + 1;
    // Use u64 to avoid i32 overflow on large selections (e.g. whole continents).
    let tile_count_64 = nx as u64 * ny as u64;
    let too_large = tile_count_64 > MAX_TILES;
    let tile_count = tile_count_64.min(u32::MAX as u64) as u32;
    let gsd = gsd_at_zoom(zoom, (bbox.lat_min + bbox.lat_max) / 2.0);
    TileEstimate {
        tile_count,
        nx,
        ny,
        estimated_mb: tile_count as f64 * 0.05,
        gsd_m_per_px: gsd,
        too_large,
    }
}

async fn fetch_tile_bytes(
    x: i32,
    y: i32,
    zoom: u32,
    source: &str,
    api_key: Option<&str>,
    cache_dir: &Path,
) -> Result<Vec<u8>> {
    let cache_path = cache_dir.join(format!("{source}_{zoom}_{x}_{y}.jpg"));
    if cache_path.exists() {
        return Ok(std::fs::read(&cache_path)?);
    }

    let url = build_tile_url(source, x, y, zoom, api_key);
    let client = reqwest::Client::builder()
        .user_agent("VPS-Inertial/1.0 mosaic-builder")
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let mut req = client.get(&url);
    if source == "esri" {
        req = req.header("Referer", "https://www.arcgis.com");
    }

    let bytes = req.send().await?.bytes().await?.to_vec();
    std::fs::write(&cache_path, &bytes)?;
    Ok(bytes)
}

#[tauri::command]
pub async fn download_tiles(
    app: AppHandle,
    bbox: BBox,
    zoom: u32,
    output_dir: String,
    source: String,
    api_key: Option<String>,
) -> Result<DownloadResult, String> {
    inner_download(app, bbox, zoom, output_dir, source, api_key)
        .await
        .map_err(|e| e.to_string())
}

async fn inner_download(
    app: AppHandle,
    bbox: BBox,
    zoom: u32,
    output_dir: String,
    source: String,
    api_key: Option<String>,
) -> Result<DownloadResult> {
    let out = Path::new(&output_dir);
    std::fs::create_dir_all(out)?;
    let cache_dir = out.join(".tile_cache");
    std::fs::create_dir_all(&cache_dir)?;

    let (x_min_raw, y_max_raw) = latlon_to_tile(bbox.lat_min, bbox.lon_min, zoom);
    let (x_max_raw, y_min_raw) = latlon_to_tile(bbox.lat_max, bbox.lon_max, zoom);
    let x_min = x_min_raw.min(x_max_raw);
    let x_max = x_min_raw.max(x_max_raw);
    let y_min = y_min_raw.min(y_max_raw);
    let y_max = y_min_raw.max(y_max_raw);

    let nx = (x_max - x_min + 1) as u64;
    let ny = (y_max - y_min + 1) as u64;
    let total = nx * ny;
    if total > MAX_TILES {
        return Err(anyhow!(
            "Region too large: {} tiles (max {}). Keep your area under ~18 km × 18 km at zoom 17.",
            total, MAX_TILES
        ));
    }
    let nx = nx as u32;
    let ny = ny as u32;
    let total = total as u32;
    let tile_size: u32 = 256;

    let mosaic_w = nx * tile_size;
    let mosaic_h = ny * tile_size;
    let mut mosaic: ImageBuffer<Rgb<u8>, Vec<u8>> = ImageBuffer::new(mosaic_w, mosaic_h);

    let mut current = 0u32;
    for yi in 0..ny {
        for xi in 0..nx {
            let tx = x_min + xi as i32;
            let ty = y_min + yi as i32;
            current += 1;
            let _ = app.emit(
                "tile-progress",
                DownloadProgress {
                    current,
                    total,
                    percent: current as f32 / total as f32 * 100.0,
                    tile_x: tx,
                    tile_y: ty,
                },
            );

            match fetch_tile_bytes(tx, ty, zoom, &source, api_key.as_deref(), &cache_dir).await {
                Ok(bytes) => {
                    if let Ok(img) = image::load_from_memory(&bytes) {
                        let rgb = img.to_rgb8();
                        let col0 = xi * tile_size;
                        let row0 = yi * tile_size;
                        for py in 0..tile_size {
                            for px in 0..tile_size {
                                let src_px = rgb.get_pixel(
                                    px.min(rgb.width().saturating_sub(1)),
                                    py.min(rgb.height().saturating_sub(1)),
                                );
                                mosaic.put_pixel(col0 + px, row0 + py, *src_px);
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Tile fetch failed {source}/{zoom}/{tx}/{ty}: {e}");
                }
            }
        }
    }

    let mosaic_path = out.join("satellite.png");
    mosaic
        .save(&mosaic_path)
        .map_err(|e| anyhow!("Failed to save mosaic: {e}"))?;

    let (origin_lat, origin_lon) = tile_to_latlon(x_min, y_min, zoom);
    let gsd = gsd_at_zoom(zoom, (bbox.lat_min + bbox.lat_max) / 2.0);

    let meta = serde_json::json!({
        "origin_lat": origin_lat,
        "origin_lon": origin_lon,
        "gsd_m_per_px": gsd,
        "width_px": mosaic_w,
        "height_px": mosaic_h,
        "zoom": zoom,
        "source": source,
    });
    let meta_path = out.join("metadata.json");
    std::fs::write(&meta_path, serde_json::to_string_pretty(&meta)?)?;

    Ok(DownloadResult {
        mosaic_path: mosaic_path.to_string_lossy().into_owned(),
        metadata_path: meta_path.to_string_lossy().into_owned(),
        width_px: mosaic_w,
        height_px: mosaic_h,
        gsd_m_per_px: gsd,
        origin_lat,
        origin_lon,
        tile_count: total,
    })
}
