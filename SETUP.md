# VPS Inertial — Hardware Setup Guide

Two supported platforms. Run the matching script, then follow the checklist.

| | Jetson Orin Nano | Raspberry Pi 5 |
|---|---|---|
| **Role** | Primary flight hardware | Ground test / dev |
| **GPU** | Ampere (CUDA 12) | None |
| **Matching rate** | 5 Hz (GPU) | ~1 Hz (CPU) |
| **Config** | `config/params.yaml` | `config/params_rpi5.yaml` |
| **Setup script** | `setup_orin.sh` | `setup_rpi5.sh` |

---

## Quick Start

```bash
# On device, clone the repo and run the platform script
git clone https://github.com/evansfsu/Macula.git && cd Macula

# Orin Nano
chmod +x setup_orin.sh && ./setup_orin.sh

# RPi5
chmod +x setup_rpi5.sh && ./setup_rpi5.sh
```

Then follow the platform sections below for camera and IMU wiring.

---

## Jetson Orin Nano

### Prerequisites

- JetPack 6.0+ flashed via SDK Manager or Balena Etcher (image from NVIDIA)
- Ubuntu 22.04 on device (L4T r36+)
- SSH access or HDMI + keyboard connected
- Internet access from device during setup

### 1 — Camera

**USB global shutter camera (recommended for initial testing)**
```yaml
# config/params.yaml
camera:
  device_id: 0       # /dev/video0
  width: 1920
  height: 1080
  fps: 30
```
Verify: `v4l2-ctl --list-devices`

**CSI camera (e.g. Arducam IMX219, IMX477)**

Set `device_id` to the GStreamer pipeline string:
```yaml
camera:
  device_id: "nvarguscamerasrc sensor-id=0 ! video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1,format=NV12 ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
  width: 1920
  height: 1080
  fps: 30
```

Test CSI pipeline independently:
```bash
gst-launch-1.0 nvarguscamerasrc ! nvvidconv ! videoconvert ! fpsdisplaysink video-sink=xvimagesink
```

### 2 — IMU

Connect IMU (e.g. VectorNav VN-100, Pixhawk via MAVLink) to USB serial:
```yaml
imu:
  port: "/dev/ttyUSB0"   # adjust if needed (ttyACM0, ttyUSB1, ...)
  baud: 921600
```

After setup, log out and back in so the `dialout` group takes effect, or:
```bash
sudo chmod a+rw /dev/ttyUSB0   # temporary, for immediate testing
```

### 3 — Display options

**Windowed (HDMI monitor attached)**
```bash
source .venv/bin/activate
python main.py
# Press q or Esc to quit
```

**Headless (SSH, no monitor)**
```bash
python main.py --headless
# Stats logged to stderr, full state to logs/
```

**Remote display via X11 forwarding**
```bash
# From your laptop:
ssh -X user@<orin-ip>
cd vps_inertial && source .venv/bin/activate
python main.py
# Window appears on your laptop screen
```

**Remote display via VNC**
```bash
# On Orin (one-time):
sudo apt-get install -y tigervnc-standalone-server
tigervncserver :1 -geometry 1280x720 -depth 24
export DISPLAY=:1

# Then run main.py normally — window appears in VNC client
# Connect: vncviewer <orin-ip>:1
```

### 4 — CUDA verification

```bash
source .venv/bin/activate
python -c "import torch; print(torch.cuda.get_device_name(0))"
# Should print: Orin (or similar Ampere device name)
```

If this fails, reinstall PyTorch via the NVIDIA wheel index (see `setup_orin.sh` step 4).

---

## Raspberry Pi 5

### Prerequisites

- Raspberry Pi OS Bookworm 64-bit (Debian 12), flashed via Raspberry Pi Imager
- Enable SSH and set hostname in Imager advanced options
- Internet access during setup

### 1 — Camera

**USB global shutter camera (simplest, recommended)**
```yaml
# config/params_rpi5.yaml
camera:
  device_id: 0
  width: 1280
  height: 720
  fps: 30
```
Check device: `v4l2-ctl --list-devices` or `ls /dev/video*`

**Pi Camera Module v3 (CSI via libcamera)**

Enable in `/boot/firmware/config.txt` (add `camera_auto_detect=1` if not present).

Then use GStreamer via libcamera:
```yaml
camera:
  device_id: "libcamerasrc ! video/x-raw,width=1280,height=720,framerate=30/1 ! videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
  width: 1280
  height: 720
  fps: 30
```

Test libcamera:
```bash
libcamera-hello --timeout 5000
```

> **Note**: OpenCV from pip does not include GStreamer support by default on RPi5. Install the system OpenCV (`python3-opencv`) and use `--system-site-packages` venv (done by `setup_rpi5.sh`), or build OpenCV from source with `-DWITH_GSTREAMER=ON`.

### 2 — IMU

Same as Orin Nano — USB serial on `/dev/ttyUSB0` or `/dev/ttyACM0`.

For I2C IMUs (e.g. MPU-6050):
```bash
sudo raspi-config   # Interface Options → I2C → Enable
i2cdetect -y 1     # should show device address
```
I2C IMU support requires a custom `imu_preintegrator.py` reader (not included — only UART is supported by default).

### 3 — Display options

**Windowed (HDMI monitor)**
```bash
source .venv/bin/activate
python main.py --config config/params_rpi5.yaml
```

**Headless**
```bash
python main.py --config config/params_rpi5.yaml --headless
```

**Remote display via X11**
```bash
ssh -X pi@<rpi-ip>
python main.py --config config/params_rpi5.yaml
```

**Remote display via VNC (built-in on RPi OS)**
```bash
sudo raspi-config   # Display → VNC → Enable
# Connect from laptop with any VNC client to <rpi-ip>:5900
```

### 4 — Performance expectations on RPi5

- **Optical flow tracking**: 30 fps (runs on CPU, fast)
- **SuperPoint + LightGlue**: ~600–1200 ms per frame on CPU
- **Effective matching rate**: ~1 Hz (set by `min_match_interval_frames: 30`)
- **ESKF predict**: <1 ms per step
- The system still navigates correctly — IMU bridges the gaps between slow visual fixes

---

## Region Map Preparation (both platforms)

Run once before flight to download the satellite mosaic for your area.

**Default test region — Newhall Community Park, Concord CA**
```bash
python tools/prepare_region.py \
  --lat-min 37.971 --lat-max 37.978 \
  --lon-min -122.001 --lon-max -121.993 \
  --zoom 17 \
  --output region/
```

**Using a different region**

Pick your bounding box from Google Maps or similar:
1. Right-click the SW corner → *What's here?* → note lat/lon
2. Right-click the NE corner → repeat
3. Pass those four values as `--lat-min`, `--lat-max`, `--lon-min`, `--lon-max`

```bash
# Example: custom area
python tools/prepare_region.py \
  --lat-min <SW_LAT> --lat-max <NE_LAT> \
  --lon-min <SW_LON> --lon-max <NE_LON> \
  --zoom 17 \
  --output region/
```

- `--zoom 17` gives ~1 m/px resolution — good for altitudes 10–80 m
- Keep the box under ~2 km × 2 km or mosaic RAM use grows significantly
- The output path must match `region_map.mosaic_path` and `region_map.metadata_path` in your params yaml (defaults: `region/satellite.png`, `region/metadata.json`)

Check output: `region/satellite.png` (open with any image viewer) and `region/metadata.json`.

---

## Camera Calibration (both platforms)

Print a 9×6 checkerboard at 25 mm square size. Run with a physical checkerboard:

```bash
python tools/calibrate.py \
  --device 0 \
  --board-size 9x6 \
  --square-size 0.025 \
  --output config/
```

Copy the printed `fx, fy, cx, cy, distortion_coeffs` into your platform's params yaml. Pass threshold: reprojection error < 0.5 px.

---

## Hardware Validation Checklist

Work through in order. Each step has a binary pass/fail.

```
[ ] Step 1  pytest tests/                         — all pass
[ ] Step 2  python tools/calibrate.py             — reproj error < 0.5 px
[ ] Step 3  python tools/time_sync.py             — time_offset_s set in yaml
[ ] Step 4  python tools/prepare_region.py        — mosaic created and correct
[ ] Step 5  python main.py (stationary on desk)   — VISION_POSITION_ESTIMATE
            visible in QGroundControl, error < 5 m
[ ] Step 6  Hand-carry over mosaic printout       — position tracks motion
[ ] Step 7  PX4 EKF2 params set, EV valid flag   — estimator_status.vision_pos_valid
[ ] Step 8  python tools/replay_eval.py           — ESKF RMS within 20% of EKF2
[ ] Step 9  Tethered hover (quadrotor, 5 m)       — stable 60 s hold
[ ] Step 10 Free hover                            — sticks-off stable
```

---

## Systemd Service (headless autostart)

Create `/etc/systemd/system/vps.service`:

```ini
[Unit]
Description=VPS Inertial positioning
After=network.target

[Service]
User=<your-user>
WorkingDirectory=/home/<your-user>/vps_inertial
ExecStart=/home/<your-user>/vps_inertial/.venv/bin/python main.py --headless
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable vps
sudo systemctl start vps
sudo journalctl -u vps -f   # follow logs
```

For RPi5, add `--config config/params_rpi5.yaml` to `ExecStart`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `CameraError: Cannot open camera` | Wrong device_id | `v4l2-ctl --list-devices`, try 0, 1, 2 |
| GStreamer pipeline hangs | Bad pipeline string | Test with `gst-launch-1.0` first |
| numpy sanity check RuntimeError on import | System numpy mixed into venv | Delete `.venv/`, re-run `setup_rpi5.sh` (script now uses isolated venv) |
| `torch.cuda.is_available() = False` | Wrong PyTorch build | Reinstall from NVIDIA wheel index |
| SuperPoint ImportError | lightglue not installed | `pip install lightglue` |
| Serial port permission denied | Not in dialout group | `sudo usermod -aG dialout $USER` + re-login |
| Fix acceptance rate 0% | Mosaic mismatch | Re-run `prepare_region.py` for correct area |
| High fix rejection rate | Altitude wrong | Check ESKF altitude estimate vs actual |
| OpenCV window fails headless | DISPLAY not set | Add `--headless` or set up VNC/X11 |
