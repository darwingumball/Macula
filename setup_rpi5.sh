#!/usr/bin/env bash
# VPS Inertial — Raspberry Pi 5 setup script
# Tested on Raspberry Pi OS Bookworm 64-bit (Debian 12)
# Run as normal user (not root). Uses sudo where needed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"

echo "==> VPS Inertial: Raspberry Pi 5 setup"
echo "    Repo: $REPO_DIR"
echo "    NOTE: SuperPoint+LightGlue runs on CPU — matching ~1-2 Hz"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "==> Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev \
    libopencv-dev python3-opencv \
    git wget curl \
    libhdf5-dev libopenblas-dev gfortran \
    v4l-utils \
    libcamera-apps \
    python3-libcamera

# ── 2. Serial port permissions (for IMU) ─────────────────────────────────────
echo "==> Configuring serial port and camera access..."
sudo usermod -aG dialout "$USER"
sudo usermod -aG video "$USER"
echo "    NOTE: log out and back in for group changes to take effect"

# ── 3. Camera interface ───────────────────────────────────────────────────────
echo "==> Enabling camera interface..."
# For Pi Camera Module via libcamera / v4l2 driver
if grep -q "Raspberry Pi 5" /proc/cpuinfo 2>/dev/null; then
    # RPi5 uses RP1 — camera works via libcamera stack
    # v4l2 shim is available via:
    if ! lsmod | grep -q v4l2_mem2mem; then
        echo "    Loading v4l2 compat module..."
        sudo modprobe v4l2-compat-ioctl32 2>/dev/null || true
    fi
fi
echo "    USB camera: works out of the box as /dev/video0"
echo "    CSI (Pi Cam v3): set device_id to libcamera GStreamer string — see SETUP.md"

# ── 4. Python virtual environment ────────────────────────────────────────────
echo "==> Creating Python venv at $VENV..."
# No --system-site-packages: isolates pip packages from system numpy/opencv
# which can cause BLAS sanity-check failures on Bookworm.
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip wheel

# Install numpy first so torch's import finds a clean, pip-managed copy
pip install "numpy>=1.24,<2.0"

# ── 5. PyTorch CPU-only ───────────────────────────────────────────────────────
echo "==> Installing PyTorch (CPU-only for RPi5)..."
# torch>=2.4 is the first release with official Python 3.13 wheels
pip install --no-cache \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.4" torchvision

python3 -c "import torch; print('  torch', torch.__version__, '| CUDA:', torch.cuda.is_available())"

# ── 6. LightGlue ─────────────────────────────────────────────────────────────
echo "==> Installing LightGlue..."
pip install lightglue

# ── 7. Project requirements ───────────────────────────────────────────────────
echo "==> Installing project requirements..."
pip install \
    "opencv-python>=4.8" \
    "scipy>=1.11" \
    "PyYAML>=6.0" \
    "kornia>=0.7" \
    "pymavlink>=2.4.37" \
    "matplotlib>=3.7" \
    "pandas>=2.0" \
    "pytest>=7.4"

# ── 8. Model weights ──────────────────────────────────────────────────────────
echo "==> Downloading SuperPoint + LightGlue weights..."
mkdir -p "$REPO_DIR/weights"
python3 -c "
from lightglue import SuperPoint, LightGlue
import torch
sp = SuperPoint(max_num_keypoints=512).eval()   # smaller budget for CPU
lg = LightGlue(features='superpoint').eval()
torch.save(sp.state_dict(), 'weights/superpoint_v1.pth')
torch.save(lg.state_dict(), 'weights/lightglue_v0.1_disk.pth')
print('  Weights saved to weights/')
"

# ── 9. Runtime directories ────────────────────────────────────────────────────
mkdir -p "$REPO_DIR/region" "$REPO_DIR/logs"

# ── 10. RPi5-specific params override ────────────────────────────────────────
echo "==> Checking for RPi5 params override..."
RPI5_CFG="$REPO_DIR/config/params_rpi5.yaml"
if [ ! -f "$RPI5_CFG" ]; then
    echo "    Creating config/params_rpi5.yaml with RPi5 defaults..."
    cat > "$RPI5_CFG" << 'EOF'
# RPi5 overlay — copy fields you want to override from params.yaml.
# Run: python main.py --config config/params_rpi5.yaml
#
# Key differences from Orin Nano default config:
#   - Camera 1280x720 (reduces CPU load)
#   - use_gpu: false (no CUDA on RPi5)
#   - min_match_interval_frames: 30  (1 Hz matching at 30 fps)
#   - max_points: 150 (lighter tracker)

camera:
  device_id: 0
  width: 1280
  height: 720
  fps: 30
  fx: 0.0
  fy: 0.0
  cx: 0.0
  cy: 0.0
  distortion_coeffs: [0.0, 0.0, 0.0, 0.0, 0.0]
  cam_to_imu_q: [1.0, 0.0, 0.0, 0.0]
  cam_to_imu_t: [0.0, 0.0, 0.0]
  fov_deg: 90.0

imu:
  port: "/dev/ttyUSB0"
  baud: 921600
  rate_hz: 200
  accel_noise_density: 0.003
  gyro_noise_density: 0.0001
  accel_random_walk: 0.0001
  gyro_random_walk: 0.000001
  gravity_ms2: 9.81
  time_offset_s: 0.0

tracker:
  max_points: 150
  min_points: 50
  fast_threshold: 20
  lk_window_size: 21
  lk_max_level: 3
  fb_error_threshold: 1.0
  min_point_distance: 20
  quality_threshold: 0.5
  high_motion_threshold: 15.0

matcher:
  superpoint_weights: "weights/superpoint_v1.pth"
  lightglue_weights: "weights/lightglue_v0.1_disk.pth"
  lightglue_min_confidence: 0.5
  min_inliers: 10
  ransac_threshold: 4.0
  min_match_interval_frames: 30
  use_gpu: false

fix_quality:
  base_vision_noise_m: 5.0
  inlier_scale: 20
  mahal_gate: 5.0
  max_fix_jump_m: 50.0

region_map:
  mosaic_path: "region/satellite.png"
  metadata_path: "region/metadata.json"
  min_altitude_m: 5.0
  max_altitude_m: 200.0

eskf:
  init_pos_std_m: 10.0
  init_vel_std_ms: 1.0
  init_att_std_rad: 0.1
  init_accel_bias_std: 0.1
  init_gyro_bias_std: 0.01
  max_pos_std_m: 500.0
  max_vel_std_ms: 50.0
  max_accel_bias: 0.5
  max_gyro_bias: 0.05
  fix_timeout_s: 10.0

mavlink:
  host: "127.0.0.1"
  port: 14550
  system_id: 1
  component_id: 195
  mode: 1
  ev_delay_ms: 50
  send_rate_hz: 30

logging:
  log_dir: "logs"
  log_full_state: true
  flush_interval_s: 1.0
EOF
    echo "    Created $RPI5_CFG"
fi

# ── 11. Quick smoke test ──────────────────────────────────────────────────────
echo "==> Running unit tests (no hardware required)..."
cd "$REPO_DIR"
python3 -m pytest tests/ -q --tb=short || echo "  WARN: some tests failed — check above"

echo ""
echo "==> RPi5 setup complete."
echo "    Activate venv:   source $VENV/bin/activate"
echo "    Edit config:     nano config/params_rpi5.yaml"
echo "    Prepare mosaic:  python tools/prepare_region.py --help"
echo "    Run (display):   python main.py --config config/params_rpi5.yaml"
echo "    Run (headless):  python main.py --config config/params_rpi5.yaml --headless"
