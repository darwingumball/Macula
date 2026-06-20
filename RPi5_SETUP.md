# Macula on Raspberry Pi 5 — Setup Guide

CPU-only deployment. Effective match rate ~1 Hz (SuperPoint + LightGlue on CPU);
ESKF and optical flow run at full camera framerate regardless.

---

## 1. Flash OS

Use **Raspberry Pi OS Bookworm 64-bit** (Debian 12). Flash via Raspberry Pi Imager.

In Imager advanced options before writing:
- Enable SSH
- Set hostname (e.g. `macula-pi`)
- Set username and password

Boot the Pi and confirm SSH access: `ssh pi@macula-pi.local`

---

## 2. Clone and run setup script

```bash
git clone https://github.com/evansfsu/Macula.git
cd Macula
chmod +x setup_rpi5.sh
./setup_rpi5.sh
```

The script installs system packages, creates a Python virtual environment with
`--system-site-packages` (needed for system OpenCV which includes GStreamer), and
installs all Python dependencies. Expect 5–10 minutes.

---

## 3. Camera

### USB camera (recommended for initial testing)

Plug in and verify:

```bash
v4l2-ctl --list-devices
```

Config (`config/params_rpi5.yaml`):

```yaml
camera:
  device_id: 0        # /dev/video0; increment if multiple cameras
  width: 1280
  height: 720
  fps: 30
```

### Pi Camera Module v3 (CSI)

Enable in `/boot/firmware/config.txt` (add if not present):

```
camera_auto_detect=1
```

Test:

```bash
libcamera-hello --timeout 5000
```

Config:

```yaml
camera:
  device_id: "libcamerasrc ! video/x-raw,width=1280,height=720,framerate=30/1 ! videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
  width: 1280
  height: 720
  fps: 30
```

> System OpenCV (via `python3-opencv`) is required for GStreamer support. The setup
> script handles this. If you see GStreamer errors, delete `.venv/` and re-run `setup_rpi5.sh`.

---

## 4. IMU

Connect a UART IMU (e.g. VectorNav VN-100, or Pixhawk MAVLink) to USB serial.

```bash
ls /dev/ttyUSB*   # or /dev/ttyACM*
```

Add user to `dialout` group (required once):

```bash
sudo usermod -aG dialout $USER
# Log out and back in for the group to take effect
```

Config:

```yaml
imu:
  port: "/dev/ttyUSB0"
  baud: 921600
```

For MAVLink UART wiring directly to FC (no USB adapter):

| Pi 5 GPIO | Flight Controller |
|---|---|
| GPIO 14 (TX) | FC TELEM RX |
| GPIO 15 (RX) | FC TELEM TX |
| GND | GND |
| 3.3V | (do not connect — power FC from its own supply) |

No level shifter needed: Pi 5 UART is 3.3V, same as FC TELEM pins.

Enable UART on Pi 5:

```bash
# Remove console from serial port
sudo sed -i 's/console=serial0,[0-9]* //' /boot/firmware/cmdline.txt

# Enable UART and load the Pi5 UART overlay
echo "enable_uart=1" | sudo tee -a /boot/firmware/config.txt
echo "dtoverlay=uart0-pi5" | sudo tee -a /boot/firmware/config.txt

sudo reboot
```

Verify after reboot:

```bash
ls /dev/ttyAMA0       # should exist
python3 -c "import serial; s=serial.Serial('/dev/ttyAMA0',921600,timeout=1); print('ok')"
```

---

## 5. Prepare satellite mosaic

Run once before flight to download the satellite image for your area:

```bash
source .venv/bin/activate
python tools/prepare_region.py \
  --lat-min 37.971 --lat-max 37.978 \
  --lon-min -122.001 --lon-max -121.993 \
  --zoom 17 \
  --output region/
```

Replace lat/lon with your target area. The Macula Desktop app can also download and
SCP regions directly from the Maps page without using this CLI.

Verify output:

```bash
ls -lh region/satellite.png region/metadata.json
```

---

## 6. Camera calibration

Print a 9×6 checkerboard at 25 mm square size. Run with the checkerboard held in front of the camera in various orientations:

```bash
python tools/calibrate.py \
  --device 0 \
  --board-size 9x6 \
  --square-size 0.025 \
  --output config/
```

Copy the resulting `fx`, `fy`, `cx`, `cy`, `distortion_coeffs` into `config/params_rpi5.yaml`. Pass criterion: reprojection error < 0.5 px.

Without calibration, visual odometry (VO) returns `valid=False` and the VO HUD line will not appear.

---

## 7. Run

```bash
source .venv/bin/activate

# Headless (SSH, no monitor)
python main.py --config config/params_rpi5.yaml --headless

# With display (HDMI monitor attached)
python main.py --config config/params_rpi5.yaml

# Remote display via X11 forwarding (from your laptop)
ssh -X pi@macula-pi.local
python main.py --config config/params_rpi5.yaml
```

Expected headless output:

```
fps=28 tq=0.82 flow=1.3px vo=0.12m/s fix=ACCEPTED innov=1.4m pos=N:3.2 E:-1.1 D:-12.0
```

---

## 8. Systemd service (autostart on boot)

Create `/etc/systemd/system/macula-vps.service`:

```ini
[Unit]
Description=Macula VPS Inertial
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/Macula
ExecStart=/home/pi/Macula/.venv/bin/python main.py --headless --config config/params_rpi5.yaml
Restart=on-failure
RestartSec=5
StandardOutput=append:/tmp/macula_vps.log
StandardError=append:/tmp/macula_vps.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable macula-vps
sudo systemctl start macula-vps

# Follow logs
sudo journalctl -u macula-vps -f
# or
tail -f /tmp/macula_vps.log
```

The Macula Desktop app (Devices page → Control tab) can install this service and manage it remotely via SSH.

---

## 9. Validation checklist

```
[ ] pytest tests/ -q                         — all pass
[ ] Camera: python main.py shows live feed   — no CameraError
[ ] Calibration: reproj error < 0.5 px       — fx/fy set in params_rpi5.yaml
[ ] Time sync: python tools/time_sync.py     — time_offset_s set
[ ] Mosaic: region/satellite.png exists      — correct area visible
[ ] Stationary run: MAVLink visible in QGC  — VISION_POSITION_ESTIMATE, error < 5 m
[ ] Hand-carry test: position tracks motion
[ ] Replay eval: ESKF within 20% of EKF2
[ ] Tethered hover: stable 60 s
[ ] Free hover: Mode 2 enabled
```

---

## Performance on Pi 5

| Operation | Rate | Notes |
|---|---|---|
| Optical flow (FAST + LK) | 30 fps | CPU-bound, fast |
| SuperPoint + LightGlue | ~600–1200 ms | ~1 Hz effective |
| ESKF predict step | < 1 ms | IMU bridges gaps |
| End-to-end latency | ~1 s for fix | Acceptable for low-speed flight |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `CameraError: Cannot open camera` | `v4l2-ctl --list-devices`, try device_id 0, 1, 2 |
| GStreamer pipeline hangs | Test with `gst-launch-1.0 libcamerasrc ! videoconvert ! autovideosink` first |
| numpy sanity check RuntimeError | Delete `.venv/`, re-run `setup_rpi5.sh` (system numpy mixing issue) |
| Serial port permission denied | `sudo usermod -aG dialout $USER` + re-login |
| `/dev/ttyAMA0` missing | Check `dtoverlay=uart0-pi5` is in `/boot/firmware/config.txt`, reboot |
| Fix acceptance rate 0% | Mosaic area mismatch — re-run `prepare_region.py` |
| VO HUD line missing | `fx`/`fy` not in params yaml — run calibration step |
| OpenCV window fails over SSH | Use `--headless` or `ssh -X` for X11 forwarding |
