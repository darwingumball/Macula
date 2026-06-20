export interface Profile {
  name: string;
  email: string;
  org: string;
  accent_color: string;
  onboarding_complete: boolean;
  mapbox_key?: string;
  bing_key?: string;
}

export type TileSource = "esri" | "mapbox" | "bing";

export type DeviceKind = "pi5" | "local";
export type AuthMethod = "password" | "key";

export interface Device {
  id: string;
  name: string;
  kind: DeviceKind;
  host?: string;
  port?: number;
  username?: string;
  auth?: { type: "Password"; password: string } | { type: "Key"; key_path: string; passphrase?: string };
  remote_project_path?: string;
  known_fingerprint?: string;
  mavlink_endpoint?: string; // e.g. "serial:/dev/ttyAMA0:921600" | "udp:14550" | "tcp:host:port"
  autopilot?: "px4" | "ardupilot";
}

export interface Region {
  id: string;
  name: string;
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
  zoom: number;
  source?: TileSource;
  output_path: string;
  last_downloaded?: string;
  tile_count?: number;
  gsd_m_per_px?: number;
  file_size_mb?: number;
  location_label?: string;
}

export interface ModelSet {
  id: string;
  name: string;
  superpoint_path: string;
  lightglue_path: string;
  is_active: boolean;
  downloaded: boolean;
}

export interface TileEstimate {
  tile_count: number;
  nx: number;
  ny: number;
  estimated_mb: number;
  gsd_m_per_px: number;
  too_large: boolean;
}

export interface DownloadProgress {
  current: number;
  total: number;
  percent: number;
  tile_x: number;
  tile_y: number;
}

export interface UploadProgress {
  file: string;
  bytes_sent: number;
  total_bytes: number;
  percent: number;
}

export interface CommandResult {
  exit_code: number;
  stdout: string;
  stderr: string;
}

export interface BBox {
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
}
