#!/usr/bin/env bash
# VPS Inertial — Jetson Orin Nano setup script
# Tested on JetPack 6.0 / Ubuntu 22.04 (L4T r36)
# Run as normal user (not root). Uses sudo where needed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"
JP_VERSION="${JP_VERSION:-60}"   # JetPack major+minor, e.g. 60 = JetPack 6.0

echo "==> VPS Inertial: Orin Nano setup (JetPack ${JP_VERSION})"
echo "    Repo: $REPO_DIR"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "==> Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev \
    libopencv-dev python3-opencv \
    git wget curl \
    libhdf5-dev libhdf5-serial-dev \
    libatlas-base-dev gfortran \
    v4l-utils

# ── 2. Serial port permissions (for IMU) ─────────────────────────────────────
echo "==> Configuring serial port access..."
sudo usermod -aG dialout "$USER"
echo "    NOTE: log out and back in for serial group to take effect"

# ── 3. Python virtual environment ────────────────────────────────────────────
echo "==> Creating Python venv at $VENV..."
python3 -m venv --system-site-packages "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip wheel

# ── 4. PyTorch for Jetson (NVIDIA wheel index) ────────────────────────────────
# JetPack 6.x ships torch 2.x compatible with CUDA 12.x on Orin
# The NVIDIA index URL covers JP60/JP61; update if your JP version differs.
echo "==> Installing PyTorch for Jetson (JetPack ${JP_VERSION})..."
JP_TORCH_URL="https://developer.download.nvidia.com/compute/redist/jp/v${JP_VERSION}/pytorch"
pip install --no-cache \
    --extra-index-url "$JP_TORCH_URL" \
    "torch>=2.1" torchvision

# Verify CUDA is visible
python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA not found'; \
    print('  torch', torch.__version__, '| CUDA', torch.version.cuda, \
    '| device:', torch.cuda.get_device_name(0))"

# ── 5. LightGlue (SuperPoint + LightGlue) ────────────────────────────────────
echo "==> Installing LightGlue..."
pip install lightglue

# ── 6. Project requirements ───────────────────────────────────────────────────
echo "==> Installing project requirements..."
pip install \
    "numpy>=1.24" \
    "opencv-python>=4.8" \
    "scipy>=1.11" \
    "PyYAML>=6.0" \
    "kornia>=0.7" \
    "pymavlink>=2.4.37" \
    "matplotlib>=3.7" \
    "pandas>=2.0" \
    "pytest>=7.4"

# ── 7. Model weights ──────────────────────────────────────────────────────────
echo "==> Downloading SuperPoint + LightGlue weights..."
mkdir -p "$REPO_DIR/weights"
python3 -c "
from lightglue import SuperPoint, LightGlue
import torch
sp = SuperPoint(max_num_keypoints=1024).eval()
lg = LightGlue(features='superpoint').eval()
torch.save(sp.state_dict(), 'weights/superpoint_v1.pth')
torch.save(lg.state_dict(), 'weights/lightglue_v0.1_disk.pth')
print('  Weights saved to weights/')
"

# ── 8. Runtime directories ────────────────────────────────────────────────────
mkdir -p "$REPO_DIR/region" "$REPO_DIR/logs"

# ── 9. Verify camera ─────────────────────────────────────────────────────────
echo "==> Checking camera devices..."
v4l2-ctl --list-devices 2>/dev/null || echo "    (v4l2-ctl not found — install v4l-utils)"
echo ""
echo "    USB camera:  set camera.device_id: 0 in config/params.yaml"
echo "    CSI camera:  set camera.device_id to GStreamer string — see SETUP.md"

# ── 10. Quick smoke test ──────────────────────────────────────────────────────
echo "==> Running unit tests (no hardware required)..."
cd "$REPO_DIR"
python3 -m pytest tests/ -q --tb=short || echo "  WARN: some tests failed — check above"

echo ""
echo "==> Orin Nano setup complete."
echo "    Activate venv:  source $VENV/bin/activate"
echo "    Edit config:    nano config/params.yaml"
echo "    Prepare mosaic: python tools/prepare_region.py --help"
echo "    Run (display):  python main.py"
echo "    Run (headless): python main.py --headless"
