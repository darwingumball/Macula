"""
Camera intrinsic calibration using a checkerboard pattern.

Usage:
    python tools/calibrate.py \
        --device 0 \
        --board-size 9x6 \
        --square-size 0.025 \
        --output config/
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np


def parse_board_size(s: str) -> tuple[int, int]:
    parts = s.lower().split("x")
    return int(parts[0]), int(parts[1])


def collect_frames(
    cap: cv2.VideoCapture,
    board_size: tuple[int, int],
    square_size: float,
    min_frames: int = 20,
) -> tuple[list, list, tuple[int, int]]:
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    cols, rows = board_size

    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_size

    obj_points = []
    img_points = []
    img_size: tuple[int, int] | None = None
    captured = 0
    last_capture = 0.0

    print(f"Move checkerboard in front of camera. Need {min_frames} good captures.")
    print("Press 'q' to quit early if enough frames collected.")

    while captured < min_frames * 2:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed", file=sys.stderr)
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if img_size is None:
            img_size = (gray.shape[1], gray.shape[0])

        found, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
        display = frame.copy()

        if found:
            cv2.drawChessboardCorners(display, (cols, rows), corners, found)
            now = time.time()
            if now - last_capture > 0.5:
                corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                obj_points.append(objp)
                img_points.append(corners2)
                captured += 1
                last_capture = now
                print(f"  Captured frame {captured}", end="\r")

        cv2.putText(display, f"Captured: {captured}/{min_frames}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Calibration", display)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') and captured >= min_frames:
            break

    cv2.destroyAllWindows()
    return obj_points, img_points, img_size


def calibrate(
    obj_points: list,
    img_points: list,
    img_size: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, float]:
    ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, img_size, None, None
    )
    err_sum = 0.0
    for i, (op, ip) in enumerate(zip(obj_points, img_points)):
        proj, _ = cv2.projectPoints(op, rvecs[i], tvecs[i], K, dist)
        err_sum += float(np.sqrt(np.mean((ip - proj) ** 2)))
    rms = err_sum / len(obj_points)
    return K, dist, rms


def main() -> None:
    parser = argparse.ArgumentParser(description="Camera intrinsic calibration")
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--board-size", type=str, default="9x6",
                        help="Columns x Rows of inner corners, e.g. 9x6")
    parser.add_argument("--square-size", type=float, default=0.025,
                        help="Square size in meters")
    parser.add_argument("--output", type=str, default="config/")
    parser.add_argument("--min-frames", type=int, default=20)
    args = parser.parse_args()

    board_size = parse_board_size(args.board_size)
    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"Cannot open camera {args.device}", file=sys.stderr)
        sys.exit(1)

    try:
        obj_pts, img_pts, img_size = collect_frames(
            cap, board_size, args.square_size, args.min_frames
        )
    finally:
        cap.release()

    if len(obj_pts) < args.min_frames:
        print(f"Not enough frames ({len(obj_pts)} < {args.min_frames}). Aborting.")
        sys.exit(1)

    print(f"\nCalibrating with {len(obj_pts)} frames...")
    K, dist, rms = calibrate(obj_pts, img_pts, img_size)

    print(f"\nReprojection error: {rms:.4f} px", end="")
    if rms < 0.5:
        print(" [PASS]")
    else:
        print(" [FAIL — needs more/better images]")

    print("\nPaste into config/params.yaml camera section:")
    print(f"  fx: {K[0,0]:.4f}")
    print(f"  fy: {K[1,1]:.4f}")
    print(f"  cx: {K[0,2]:.4f}")
    print(f"  cy: {K[1,2]:.4f}")
    dist_list = [round(float(d), 8) for d in dist.flatten()[:5]]
    print(f"  distortion_coeffs: {dist_list}")


if __name__ == "__main__":
    main()
