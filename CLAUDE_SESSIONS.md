# Claude Code Session History

Development log of features and decisions made across Claude Code sessions.
Ordered chronologically. Each entry covers what was built, why, and any key decisions made.

---

## VPS Inertial Core System

### Initial architecture

Designed and implemented the full VPS Inertial Python system:

- `shared/camera_source.py` — CameraSource with GStreamer/OpenCV backend
- `shared/tracker.py` — FAST keypoint detection + Lucas-Kanade optical flow
- `shared/matcher.py` — SuperPoint + LightGlue feature matching + RANSAC + georeferencing
- `shared/fix_quality.py` — Mahalanobis gate, adaptive covariance, quality scoring
- `shared/region_map.py` — Satellite mosaic load, altitude-scaled crop, coordinate transforms
- `estimator/imu_preintegrator.py` — Background IMU thread, bias correction, attitude propagation
- `estimator/eskf.py` — 16-state error-state Kalman filter (pos + vel + att + biases)
- `estimator/mavlink_bridge.py` — Mode 1 (raw fix) / Mode 2 (fused pose) MAVLink output
- `tools/display.py` — Live overlay window with flow lines, tracked points, VO HUD
- `tools/prepare_region.py` — Satellite tile download + mosaic stitch CLI
- `tools/calibrate.py` — Camera intrinsic calibration CLI
- `tools/time_sync.py` — Camera-IMU temporal offset estimation
- `tools/replay_eval.py` — Offline ESKF validation against recorded flight logs
- `main.py` — Top-level loop wiring all modules together
- `config/params.yaml` + `config/params_rpi5.yaml` — All numeric parameters, no hardcoded values

**Key decisions:**
- Error-state (not full-state) Kalman filter: numerically stable, minimal state for embedded
- Scalar-first quaternion `[w, x, y, z]` throughout
- NED frame from takeoff origin; lat/lon → NED via equirectangular approx
- AsyncMatcher wraps synchronous Matcher in a thread so main loop never blocks on GPU
- Mode 1 / Mode 2 switch: validate visually first, then enable ESKF output

### Visual odometry estimator added

Added `shared/vo_estimator.py` (VOEstimator):
- Converts FAST+LK optical flow to body-frame NED velocity using camera intrinsics
- Provides independent velocity estimate to complement fix-rate-limited matcher
- Feeds VO HUD line in display and headless log output

**Key decision:** VO as supplementary data only — not fused into ESKF directly (risks double-counting with IMU). Displayed for operator situational awareness.

---

## Desktop App (Tauri 2 + React)

### Scaffold and initial pages (~2026-06-19)

Created `Desktop-App/` with full Tauri 2 + React 18 + TypeScript + Tailwind CSS stack.

**Build environment settled:**
- VS 2019 Build Tools with MSVC v142 workload (not 2022 — path is hard-coded in dev.bat)
- Windows SDK 10.0.26100 for kernel32.lib
- `dev.bat` wrapper to activate vcvars64 before `npm run tauri dev`

**Pages completed:** Onboarding (4-step wizard), Maps (satellite download), Models (SuperPoint/LightGlue weight management), Devices (SSH CRUD), Upload (SCP), Settings (YAML editor).

**Key decisions:**
- Frameless window (`decorations: false`) with custom title bar in Layout.tsx
- Rectangle draw rewritten with manual Leaflet mouse events (L.Draw.Rectangle has WebView2 pointer-capture bug on Windows — unreliable drag behavior)
- SSH via ssh2 Rust crate (synchronous) → all SSH in `tokio::task::spawn_blocking`
- CSP set to `null` in tauri.conf.json so WebView can fetch Nominatim and satellite tile sources

### Dashboard, Settings, Upload, Devices control panel (~2026-06-20)

- **Dashboard:** Readiness checklist (Device / Region / Ready), status bar, quick action buttons
- **Settings:** Added Mapbox and Bing API key input cards (persisted in profile.json)
- **Upload:** Auto-populates with all downloaded region files on mount
- **Devices:** Pi5 remote control panel — Status / Run VPS / Stop VPS / View Logs / Service tabs
  - Terminal output pane with live SSH output
  - MAVLink endpoint + autopilot badge in footer

### Devices: MAVLink + Setup Guide (~2026-06-20)

Added two new fields to the device form:
- `mavlink_endpoint` — e.g. `serial:/dev/ttyAMA0:921600`, `udp:14550`
- `autopilot` — px4 or ardupilot toggle

Added **Setup Guide** tab in device control panel (5-step Cyclops-inspired flow):
1. UART wiring diagram (GPIO 14 TX → FC RX, GPIO 15 RX → FC TX, GND, 3.3V — no level shifter)
2. Enable UART — one-click SSH patches `cmdline.txt` + `config.txt`
3. Verify MAVLink device — checks `/dev/ttyAMA0` and pyserial handshake
4. Install `macula-vps.service` systemd unit
5. FC parameter table — switches between PX4 EKF2 params and ArduPilot EKF3 params based on autopilot field

**Key decision:** Parameters in Setup Guide tab are read-only reference tables with copy buttons, not editable forms — the Pi5 owns its own config, desktop just shows what to set.

### Region persistence and metadata (~2026-06-20)

Added `regions.json` to app data persistence. Region objects now carry:
- `gsd_m_per_px` — from TileEstimate at download time
- `file_size_mb` — estimated from tile count
- `location_label` — Nominatim reverse geocode of center point; format "City, Country"
- `origin_lat` / `origin_lon` — NW corner of tile grid (not center)

Dashboard region cards updated to show location, resolution, file size, zoom, date, with inline name editing (click pencil → type → Enter) and delete.

Maps page **Import existing folder** button added: reads `metadata.json`, reconstructs bbox from pixel dimensions + GSD, reverse-geocodes for location label. Used to recover regions after `regions.json` loss.

**Key decision:** Nominatim for geocoding (free, no API key) rather than Google/Mapbox geocoding API. Requires `User-Agent` header and rate limiting — handled in frontend fetch.

---

## What's next

- **GCS page** (`/gcs`): Leaflet map with actual GPS (blue) vs VPS estimate (cyan), telemetry HUD, MAVLink log panel, arm/disarm, flight mode switching
- **Logs page** (`/logs`): Unified viewer for app logs, Pi5 SSH output, VPS matching events
- **Models:** Replace placeholder download URLs with real SuperPoint + LightGlue weights
- **ArduPilot EKF3** validation (PX4 EKF2 is primary target)
