mod commands;

use commands::{
    config_cmd::{list_yaml_configs, read_yaml_config, write_yaml_config},
    profile::{load_devices, load_profile, load_regions, save_devices, save_profile, save_regions},
    satellite::{download_tiles, estimate_tiles},
    ssh::{ssh_run_command, ssh_upload_files, test_ssh_connection},
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            load_profile,
            save_profile,
            load_devices,
            save_devices,
            load_regions,
            save_regions,
            estimate_tiles,
            download_tiles,
            test_ssh_connection,
            ssh_run_command,
            ssh_upload_files,
            read_yaml_config,
            write_yaml_config,
            list_yaml_configs,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Macula");
}
