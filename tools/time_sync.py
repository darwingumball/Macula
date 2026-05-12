"""
Camera-IMU temporal offset calibration.

Displays a bright flash frame on screen, simultaneously records the camera
timestamp when the bright frame is detected, and the IMU timestamp when the
associated vibration/motion signature is detected.

Usage:
    python tools/time_sync.py \
        --camera-device 0 \
        --imu-port /dev/ttyUSB0
"""

import argparse
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np


class IMUReader:
    def __init__(self, port: str, baud: int = 921600) -> None:
        self._port = port
        self._baud = baud
        self._samples: deque = deque(maxlen=1000)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import serial
            self._ser = serial.Serial(self._port, self._baud, timeout=0.01)
        except Exception as e:
            print(f"IMU serial open failed: {e}", file=sys.stderr)
            self._ser = None
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        while self._running:
            try:
                line = self._ser.readline()
                if line:
                    parts = line.decode(errors='ignore').strip().split(',')
                    if len(parts) >= 7:
                        ts_ns = time.time_ns()
                        accel = np.array([float(parts[1]), float(parts[2]), float(parts[3])])
                        self._samples.append((ts_ns, accel))
            except Exception:
                pass

    def get_samples(self) -> list:
        return list(self._samples)

    def stop(self) -> None:
        self._running = False
        if hasattr(self, '_ser') and self._ser:
            self._ser.close()


def detect_camera_flash(cap: cv2.VideoCapture, threshold: float = 200.0) -> int | None:
    prev_mean = None
    for _ in range(300):
        ret, frame = cap.read()
        if not ret:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        if prev_mean is not None and mean - prev_mean > threshold:
            return time.time_ns()
        prev_mean = mean
    return None


def detect_imu_impulse(samples_before: list, samples_after: list) -> int | None:
    if not samples_after:
        return None
    accels_before = np.array([s[1] for s in samples_before[-20:]]) if samples_before else None
    baseline = float(np.mean(np.linalg.norm(accels_before, axis=1))) if accels_before is not None else 10.0
    for ts_ns, accel in samples_after:
        mag = float(np.linalg.norm(accel))
        if mag > baseline + 1.0:
            return ts_ns
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Camera-IMU time offset calibration")
    parser.add_argument("--camera-device", type=int, default=0)
    parser.add_argument("--imu-port", type=str, default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera_device)
    if not cap.isOpened():
        print(f"Cannot open camera {args.camera_device}", file=sys.stderr)
        sys.exit(1)

    imu = IMUReader(args.imu_port, args.baud)
    imu.start()

    offsets = []

    for trial in range(args.trials):
        print(f"\nTrial {trial+1}/{args.trials} — place camera to see screen flash")
        time.sleep(1.0)

        samples_before = imu.get_samples()

        cv2.namedWindow("Flash", cv2.WINDOW_NORMAL)
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        white = np.ones((480, 640, 3), dtype=np.uint8) * 255

        cv2.imshow("Flash", black)
        cv2.waitKey(500)
        flash_host_ts = time.time_ns()
        cv2.imshow("Flash", white)
        cv2.waitKey(1)

        cam_ts = detect_camera_flash(cap)
        time.sleep(0.5)
        samples_after = [s for s in imu.get_samples() if s[0] > flash_host_ts]
        imu_ts = detect_imu_impulse(samples_before, samples_after)

        cv2.imshow("Flash", black)
        cv2.waitKey(100)
        cv2.destroyWindow("Flash")

        if cam_ts is not None and imu_ts is not None:
            offset_s = (cam_ts - imu_ts) * 1e-9
            offsets.append(offset_s)
            print(f"  Offset this trial: {offset_s*1000:.2f} ms")
        else:
            print("  Detection failed — skipping this trial")

    cap.release()
    imu.stop()

    if not offsets:
        print("\nNo valid measurements. Check connections and lighting.")
        sys.exit(1)

    mean_offset = float(np.mean(offsets))
    std_offset = float(np.std(offsets))
    print(f"\nTime offset: {mean_offset*1000:.2f} ms  std={std_offset*1000:.2f} ms")
    print("\nPaste into config/params.yaml imu section:")
    print(f"  time_offset_s: {mean_offset:.4f}")


if __name__ == "__main__":
    main()
