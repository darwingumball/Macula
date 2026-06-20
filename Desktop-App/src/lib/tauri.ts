import { invoke } from "@tauri-apps/api/core";
import type { BBox, CommandResult, Device, DownloadProgress, Profile, Region, TileEstimate } from "./types";

export const cmd = {
  loadProfile: () => invoke<Profile>("load_profile"),
  saveProfile: (profile: Profile) => invoke<void>("save_profile", { profile }),
  loadDevices: () => invoke<Device[]>("load_devices"),
  saveDevices: (devices: Device[]) => invoke<void>("save_devices", { devices }),
  loadRegions: () => invoke<Region[]>("load_regions"),
  saveRegions: (regions: Region[]) => invoke<void>("save_regions", { regions }),
  estimateTiles: (bbox: BBox, zoom: number) =>
    invoke<TileEstimate>("estimate_tiles", { bbox, zoom }),
  downloadTiles: (bbox: BBox, zoom: number, outputDir: string, source = "esri", apiKey?: string) =>
    invoke("download_tiles", { bbox, zoom, outputDir, source, apiKey }),
  testSshConnection: (
    host: string,
    port: number,
    username: string,
    auth: Device["auth"]
  ) => invoke<{ ok: boolean; message: string; server_banner?: string; fingerprint?: string }>(
    "test_ssh_connection",
    { host, port, username, auth }
  ),
  sshRunCommand: (
    host: string,
    port: number,
    username: string,
    auth: Device["auth"],
    command: string
  ) => invoke<CommandResult>("ssh_run_command", { host, port, username, auth, command }),
  sshUploadFiles: (
    host: string,
    port: number,
    username: string,
    auth: Device["auth"],
    localPaths: string[],
    remoteDir: string
  ) => invoke<void>("ssh_upload_files", { host, port, username, auth, localPaths, remoteDir }),
  readYamlConfig: (path: string) => invoke<Record<string, unknown>>("read_yaml_config", { path }),
  writeYamlConfig: (path: string, data: Record<string, unknown>) =>
    invoke<void>("write_yaml_config", { path, data }),
  listYamlConfigs: (dir: string) => invoke<string[]>("list_yaml_configs", { dir }),
};

export type { DownloadProgress };
