# Macula Desktop App

Tauri 2 + React desktop application for configuring and deploying the Macula VPS Inertial system.
Handles satellite map downloads, AI model management, deployment to Raspberry Pi 5 via SSH/SCP,
and ground control station (GCS) functionality for PX4/ArduPilot drones.

---

## Stack

| Layer | Technology |
|---|---|
| Desktop shell | Tauri 2 (Rust backend + WebView2 frontend) |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS (custom dark drone/tech theme) |
| State | Zustand |
| Maps | react-leaflet + leaflet-draw |
| SSH/SCP | ssh2 Rust crate (sync, wrapped in spawn_blocking) |
| Tile fetch | reqwest + image Rust crates |
| Config | serde_yaml |
| Persistence | `%LOCALAPPDATA%\Macula\` — profile.json, devices.json, regions.json |

---

## Directory Layout

```
Desktop-App/
  dev.bat                      ← Windows launcher (sets MSVC env, runs npm run tauri dev)
  package.json
  tailwind.config.js
  src/
    App.tsx                    ← Root: loads profile/devices/regions on startup, routing
    index.css                  ← Leaflet CSS first, then Tailwind directives
    components/
      Layout.tsx               ← Sidebar nav + custom frameless title bar
    pages/
      Onboarding.tsx           ← 4-step setup: welcome → profile → device → done
      Dashboard.tsx            ← Overview, saved regions with inline editing
      Maps.tsx                 ← Satellite map download + region import
      Models.tsx               ← AI model set management (SuperPoint + LightGlue)
      Devices.tsx              ← SSH device management + Pi5 remote control + setup guide
      Upload.tsx               ← SCP upload to active device
      Settings.tsx             ← YAML config editor + API keys
    lib/
      store.ts                 ← Zustand: profile, devices, regions, activeDeviceId
      tauri.ts                 ← Typed invoke() wrappers (cmd.*)
      types.ts                 ← Shared TypeScript interfaces
      utils.ts                 ← cn(), generateId(), formatDate()
  src-tauri/
    Cargo.toml
    tauri.conf.json            ← decorations: false (custom title bar), 1280×800, csp: null
    capabilities/
      default.json             ← All Tauri v2 permissions
    icons/                     ← Generated via PowerShell System.Drawing (cyan crosshair)
    src/
      lib.rs                   ← Plugin init + tauri::generate_handler![]
      commands/
        satellite.rs           ← Tile download (ESRI / Mapbox / Bing), mosaic stitch
        ssh.rs                 ← SSH connection test, SCP upload, ssh_run_command
        config_cmd.rs          ← YAML read/write
        profile.rs             ← Profile, Device, Region persistence (JSON files)
```

---

## Running in Development

**Always use `dev.bat`** — it activates the VS 2019 MSVC environment before compiling:

```
Desktop-App\dev.bat
```

What it does:
1. Calls `vcvars64.bat` from VS 2019 Build Tools to set `PATH`, `LIB`, `INCLUDE`
2. `cd`s to `Desktop-App/`
3. Runs `npm run tauri dev`

Vite starts on `http://localhost:1420`. Rust compiles and launches `macula-desktop.exe`.
All 455 Rust dependencies are cached after first build — subsequent builds take ~30s.

**Do NOT** run `npm run tauri dev` directly in a plain PowerShell session — `link.exe` won't be found.

### Prerequisites (Windows)

- **Rust** — installed via `winget install Rustlang.Rustup`
- **VS 2019 Build Tools** — `winget install Microsoft.VisualStudio.2019.BuildTools`
  - Workload: "C++ build tools", components: MSVC v142, Windows 10 SDK
- **Windows SDK 10.0.26100** — `winget install Microsoft.WindowsSDK.10.0.26100`
- **Node.js** — for npm + Vite

---

## Features

### Onboarding (`/onboarding`)
4-step wizard shown on first launch (profile.onboarding_complete = false):
1. **Welcome** — intro screen
2. **Profile** — name (required), org, email, accent color (7 choices)
3. **Device** — optional: add Pi5 (IP/port/username/password or SSH key) or Local
4. **Done** — saves profile with onboarding_complete: true

### Dashboard (`/dashboard`)
- Readiness checklist: Device configured / Region downloaded / Ready to deploy
- Status bar: active device badge, region count, device count
- Quick actions: Download Region / Manage Models / Manage Devices / Upload to Device
- **Saved Regions list** — with inline metadata display and editing:
  - Location label (city, country via Nominatim reverse geocode)
  - Resolution (GSD in m/px)
  - Estimated file size (MB)
  - Zoom level badge
  - Download date
  - Inline name editing (pencil icon on hover → input → Enter/blur to save)
  - Delete button (removes from store + regions.json)

### Maps (`/maps`)
Downloads satellite image mosaics for use by the VPS system on-device.

**Imagery sources** (selector in right panel):
| Source | Zoom | Key needed | Notes |
|---|---|---|---|
| ESRI World Imagery | up to 19 | No | Free, global, default |
| Mapbox Satellite | up to 22 | Yes (mapbox_key in profile) | Sharpest available |
| Bing Maps Aerial | up to 20 | Yes (bing_key in profile) | Good alternative |

**Selection tools** (3 buttons in right panel):
- **Rectangle** — manual Leaflet mousedown/mousemove/mouseup (NOT L.Draw.Rectangle — that has a WebView2 pointer-capture bug on Windows)
- **Triangle** — polygon tool, click 3 corners, closes automatically
- **Polygon** — polygon tool, click N points + double-click to close

**Download flow:**
1. Draw shape → bbox computed from bounds
2. Panel shows tile count, estimated MB, GSD
3. Pick output folder
4. Download → Rust `download_tiles` command → `tile-progress` events stream back
5. Saves `satellite.png` + `metadata.json` to output folder
6. Reverse geocodes center point via Nominatim (no API key required)
7. Region added to Zustand store + saved to `regions.json`

**Import existing folder** — "Import existing folder…" button reads `metadata.json`
from any pre-downloaded region folder and recovers bbox, GSD, and location. Useful
if regions.json was lost or a region was downloaded outside the app.

**Tile caching:** `.tile_cache/` subfolder in output dir. Cache key: `{source}_{z}_{x}_{y}.jpg`.

**metadata.json format** (written by Rust after download):
```json
{
  "origin_lat": 37.798,   // NW corner of tile grid (top-left)
  "origin_lon": -122.480,
  "gsd_m_per_px": 0.236,
  "width_px": 6400,
  "height_px": 5632,
  "zoom": 19,
  "source": "esri"
}
```

### Models (`/models`)
Manages SuperPoint + LightGlue model weight pairs. Paths sync to `params.yaml` on upload.
Note: download URLs are currently placeholders.

### Devices (`/devices`)
SSH device CRUD with two panels per device:

**Add/Edit form fields (Pi5):**
- Name, host, port, username, auth (password or SSH key)
- Remote project path
- **MAVLink endpoint** — e.g. `serial:/dev/ttyAMA0:921600`, `udp:14550`, `tcp:host:port`
- **Autopilot** — PX4 (default) or ArduPilot toggle

**Per-device control panel** (expandable, two tabs):

*Control tab:*
- Status — `pgrep -af 'python.*main.py'`
- Run VPS — `nohup python3 main.py --headless --config config/params_rpi5.yaml`
- Stop VPS — `pkill -f 'python.*main.py'`
- View Logs — `tail -n 60 /tmp/macula_vps.log`
- Service — `systemctl status macula-vps`
- Terminal output pane with blinking cursor while running
- MAVLink endpoint + autopilot badge shown in footer

*Setup Guide tab (Cyclops-inspired, 5 steps):*
1. **UART Wiring** — GPIO 14 (TX) → FC RX, GPIO 15 (RX) → FC TX, GND → GND, 3.3V no level shifter
2. **Enable UART on Pi5** — one-click SSH: disables serial console in cmdline.txt, adds `dtoverlay=uart0-pi5` + `enable_uart=1` to config.txt
3. **Verify MAVLink Device** — checks `/dev/ttyAMA0` exists and has data flowing via pyserial
4. **Install Macula as Systemd Service** — installs `macula-vps.service`, enables on boot
5. **FC Parameters** — PX4 or ArduPilot param table (switches per autopilot setting), all copyable

**PX4 EKF2 params for external vision:**
| Param | Value | Note |
|---|---|---|
| EKF2_EV_CTRL | 15 | Enable EV pos + vel + yaw + height |
| EKF2_HGT_REF | 3 | Vision as height reference |
| EKF2_EV_DELAY | 25 | Camera latency ms — tune per rig |
| EKF2_EV_NOISE_MD | 0 | Use covariance from EV message |
| EKF2_EVP_NOISE | 0.1 | Fallback position noise (m) |
| EKF2_EVA_NOISE | 0.05 | Fallback angle noise (rad) |

### Upload (`/upload`)
Uploads files to active device via SCP. Auto-populates with all downloaded region files
on mount. Per-file progress bars via `upload-progress` Tauri events.

### Settings (`/settings`)
- YAML config file picker + section-by-section editor (booleans as toggles, arrays as JSON)
- **API Keys** card — Mapbox and Bing key inputs (saved to profile.json)

---

## Persistence

All data persisted to `%LOCALAPPDATA%\Macula\`:

| File | Contents |
|---|---|
| `profile.json` | Name, org, email, accent color, onboarding flag, API keys |
| `devices.json` | SSH device list (host, auth, paths, MAVLink endpoint, autopilot) |
| `regions.json` | Saved region library (bbox, zoom, GSD, file size, location label) |

Loaded on startup in `App.tsx` via parallel `Promise.all([loadProfile, loadDevices, loadRegions])`.

**Recovering a lost region:** If `regions.json` is missing, use the Maps page
"Import existing folder…" button and point it at the folder containing `metadata.json`.

---

## Architecture Notes

### Custom frameless window
`tauri.conf.json` sets `decorations: false`. `Layout.tsx` renders a custom title bar with
minimize/maximize/close using `getCurrentWindow()`. Requires explicit capabilities:
`core:window:allow-minimize`, `allow-close`, `allow-toggle-maximize`.

### Profile & API keys
`profile.json` at `%LOCALAPPDATA%\Macula\profile.json`:
```json
{
  "name": "...", "email": "...", "org": "...",
  "accent_color": "#06B6D4",
  "onboarding_complete": true,
  "mapbox_key": "pk.eyJ1...",
  "bing_key": "..."
}
```

### Region metadata & reverse geocoding
After download, `Maps.tsx` calls `https://nominatim.openstreetmap.org/reverse` (free, no key,
requires `User-Agent` header per Nominatim policy). CSP is `null` in tauri.conf.json so
external fetches from WebView are allowed. Location stored as `"City, Country"` string.

### Satellite tile sources (Rust)
`satellite.rs` supports three sources via `build_tile_url()`:
- **ESRI** — standard XYZ, Referer header required
- **Mapbox** — standard XYZ with `?access_token=` query param
- **Bing** — quadkey addressing; `tile_to_quadkey()` converts x/y/z → quadkey string

`origin_lat`/`origin_lon` in `metadata.json` is the **NW corner** of the tile grid
(`tile_to_latlon(x_min, y_min, zoom)`), not the bbox center.

### Map draw tools
Rectangle uses manual Leaflet `mousedown`/`mousemove`/`mouseup` (NOT `L.Draw.Rectangle`
which is unreliable in WebView2 due to pointer-capture behaviour on Windows).
Triangle/Polygon use `L.Draw.Polygon` with vertex counting for triangle auto-close.

### SSH
`ssh2` crate is synchronous — all SSH in `tokio::task::spawn_blocking`.
`ssh_run_command` returns `{ exit_code, stdout, stderr }` for arbitrary Pi5 commands.

### Rust commands reference
| Command | File | Purpose |
|---|---|---|
| `load_profile` / `save_profile` | profile.rs | Profile persistence |
| `load_devices` / `save_devices` | profile.rs | Device list persistence |
| `load_regions` / `save_regions` | profile.rs | Region library persistence |
| `estimate_tiles` | satellite.rs | Tile count + GSD preview (no download) |
| `download_tiles` | satellite.rs | Full mosaic download with progress events |
| `test_ssh_connection` | ssh.rs | SSH handshake + fingerprint check |
| `ssh_run_command` | ssh.rs | Run arbitrary command over SSH, returns stdout/stderr |
| `ssh_upload_files` | ssh.rs | SCP file upload with progress events |
| `read_yaml_config` | config_cmd.rs | Read params.yaml → JSON |
| `write_yaml_config` | config_cmd.rs | Write JSON → params.yaml |
| `list_yaml_configs` | config_cmd.rs | List config files in a directory |

---

## Ground Control Station (GCS) — Roadmap

The desktop app is evolving into a full GCS for Macula-powered drones.
Design reference: QGroundControl (dark theme, map-centric, MAVLink-native).

### Core GCS Goals

| Feature | Priority | Status |
|---|---|---|
| MAVLink TCP/UDP/serial connection to PX4 | P0 | Planned |
| Real-time 2D map: actual vs estimated position overlay | P0 | Planned |
| Telemetry HUD (altitude, speed, battery, mode, VPS health) | P0 | Planned |
| Log streaming (desktop + Pi5 SSH + feature matching) | P1 | Planned |
| Arm/Disarm, flight mode switching | P1 | Planned |
| 3D attitude viewer (roll/pitch/yaw indicator) | P2 | Planned |
| ArduPilot compatibility (secondary to PX4) | P2 | Planned |

### MAVLink Architecture (planned)

```
Drone (PX4 + Macula Pi5)
   │  MAVLink over UDP (default 14550) / TCP / serial
   ▼
Rust backend (mavlink crate — not yet added)
   ├── parse_mavlink_stream() — HEARTBEAT, LOCAL_POSITION_NED,
   │     ATT_POS_MOCAP, VISION_POSITION_ESTIMATE, VFR_HUD
   └── Tauri events → frontend
         ├── "mavlink-telemetry"  — { lat, lon, alt, vx, vy, vz, roll, pitch, yaw, mode, armed }
         ├── "vps-fix"           — { ned_n, ned_e, ned_d, cov }
         └── "mavlink-raw"       — raw bytes for log panel
```

### GCS Layout (planned, QGroundControl-style)

```
┌──────────────────────────────────────────────────────────────────┐
│ [●] PX4   STABILIZED   12.4V   ▲ 42m   → 3.2m/s   VPS: OK      │  ← Status bar
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Leaflet map (satellite)                          │ Attitude    │
│   ● actual position (GPS/EKF2, blue dot)           │ indicator   │
│   ◆ VPS estimate (cyan dot)                        │ (roll/pitch)│
│   ─── flight path history                          │             │
│                                                    │ Altitude    │
│                                                    │ tape        │
│                                                    │             │
├──────────────────────────────────────────────────────────────────┤
│ Logs:  [App] [Pi5 SSH] [VPS Matching]  ─── scrolling terminal   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Progress Log

| Date | Change |
|---|---|
| 2026-06-19 | App compiling and running. Onboarding, Maps, Models, Devices, Upload, Settings pages complete. |
| 2026-06-20 | Dashboard readiness checklist + bug fix. Settings: Mapbox/Bing API key inputs. Upload: auto-populates downloaded regions. Devices: Pi5 remote control panel (Status/Run VPS/Stop VPS/Logs/Service). Maps: rectangle draw rewritten with manual Leaflet mouse events (fixes WebView2 drag bug). |
| 2026-06-20 | Devices: MAVLink endpoint + autopilot fields added to form. Pi5 Setup Guide tab: UART wiring diagram, one-click SSH commands for UART enable + MAVLink verify + systemd service install, PX4/ArduPilot FC param tables with copy buttons. GCS roadmap documented. |
| 2026-06-20 | Region persistence: regions.json at %LOCALAPPDATA%\Macula\. Region metadata: GSD, file size, location (Nominatim reverse geocode). Dashboard region cards: location/resolution/size display, inline name editing, delete. Maps: "Import existing folder" button to recover pre-downloaded regions from metadata.json. |

---

## Known Issues / TODO

### Pages
- [ ] Models page download URLs are placeholders — need real SuperPoint/LightGlue weights
- [ ] No usage ledger / billing event hooks yet

### GCS (not started)
- [ ] Add `mavlink` crate to Cargo.toml, implement `connect_mavlink` command
- [ ] GCS page — map view with position overlay
- [ ] Telemetry HUD panel
- [ ] Log streaming panel (tabbed: App / Pi5 / MAVLink)
- [ ] Arm/Disarm + mode switching
- [ ] 3D attitude indicator

---

## Tailwind Theme

Custom colors in `tailwind.config.js`:
```
bg.base:     #080E1C   (darkest, window background)
bg.surface:  #0D1526   (sidebar, panels)
bg.card:     #121E35   (cards, inputs)
bg.elevated: #172440   (hover states)
border:      #1E2E4A
border-strong: #2A3F60
cyan.500:    #06B6D4   (accent)
```

Component classes (in `index.css`): `.btn-primary`, `.btn-secondary`, `.btn-ghost`,
`.card`, `.input-field`, `.label`, `.section-title`, `.badge-*`
