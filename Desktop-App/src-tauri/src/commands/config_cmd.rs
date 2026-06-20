use anyhow::{Context, Result};
use std::path::Path;

#[tauri::command]
pub fn read_yaml_config(path: String) -> Result<serde_json::Value, String> {
    let text = std::fs::read_to_string(&path)
        .with_context(|| format!("Cannot read {path}"))
        .map_err(|e| e.to_string())?;
    let val: serde_yaml::Value = serde_yaml::from_str(&text)
        .map_err(|e| e.to_string())?;
    serde_json::to_value(val).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn write_yaml_config(path: String, data: serde_json::Value) -> Result<(), String> {
    let yaml_val: serde_yaml::Value = serde_json::from_value(data)
        .map_err(|e| e.to_string())?;
    let text = serde_yaml::to_string(&yaml_val).map_err(|e| e.to_string())?;
    if let Some(parent) = Path::new(&path).parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    std::fs::write(&path, text).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn list_yaml_configs(dir: String) -> Result<Vec<String>, String> {
    let path = Path::new(&dir);
    if !path.exists() {
        return Ok(vec![]);
    }
    let entries = std::fs::read_dir(path).map_err(|e| e.to_string())?;
    let mut files = vec![];
    for entry in entries.flatten() {
        let p = entry.path();
        if p.extension().and_then(|e| e.to_str()) == Some("yaml") {
            files.push(p.to_string_lossy().into_owned());
        }
    }
    Ok(files)
}
