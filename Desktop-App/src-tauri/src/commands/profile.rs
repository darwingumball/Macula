use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

fn profile_path() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Macula")
        .join("profile.json")
}

#[derive(Serialize, Deserialize, Clone, Default)]
pub struct Profile {
    pub name: String,
    pub email: String,
    pub org: String,
    pub accent_color: String,
    pub onboarding_complete: bool,
    #[serde(default)]
    pub mapbox_key: Option<String>,
    #[serde(default)]
    pub bing_key: Option<String>,
}

#[tauri::command]
pub fn load_profile() -> Result<Profile, String> {
    let path = profile_path();
    if !path.exists() {
        return Ok(Profile::default());
    }
    let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_profile(profile: Profile) -> Result<(), String> {
    let path = profile_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(&profile).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(tag = "type")]
pub enum DeviceAuth {
    Password { password: String },
    Key {
        key_path: String,
        #[serde(default)]
        passphrase: Option<String>,
    },
}

#[derive(Serialize, Deserialize, Clone)]
pub struct Device {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub username: Option<String>,
    pub auth: Option<DeviceAuth>,
    pub remote_project_path: Option<String>,
    #[serde(default)]
    pub known_fingerprint: Option<String>,
    #[serde(default)]
    pub mavlink_endpoint: Option<String>,
    #[serde(default)]
    pub autopilot: Option<String>,
}

fn devices_path() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Macula")
        .join("devices.json")
}

#[tauri::command]
pub fn load_devices() -> Result<Vec<Device>, String> {
    let path = devices_path();
    if !path.exists() {
        return Ok(vec![]);
    }
    let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_devices(devices: Vec<Device>) -> Result<(), String> {
    let path = devices_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(&devices).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())
}

#[derive(Serialize, Deserialize, Clone)]
pub struct Region {
    pub id: String,
    pub name: String,
    pub lat_min: f64,
    pub lat_max: f64,
    pub lon_min: f64,
    pub lon_max: f64,
    pub zoom: u32,
    #[serde(default)]
    pub source: Option<String>,
    pub output_path: String,
    #[serde(default)]
    pub last_downloaded: Option<String>,
    #[serde(default)]
    pub tile_count: Option<u64>,
    #[serde(default)]
    pub gsd_m_per_px: Option<f64>,
    #[serde(default)]
    pub file_size_mb: Option<f64>,
    #[serde(default)]
    pub location_label: Option<String>,
}

fn regions_path() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Macula")
        .join("regions.json")
}

#[tauri::command]
pub fn load_regions() -> Result<Vec<Region>, String> {
    let path = regions_path();
    if !path.exists() {
        return Ok(vec![]);
    }
    let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_regions(regions: Vec<Region>) -> Result<(), String> {
    let path = regions_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(&regions).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())
}
