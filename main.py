import argparse
import csv
import logging
import signal
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from estimator.eskf import ESKF
from estimator.imu_preintegrator import IMUPreintegrator
from estimator.mavlink_bridge import MAVLinkBridge
from shared.camera_source import CameraSource
from shared.fix_quality import FixQuality
from shared.matcher import Matcher
from shared.region_map import RegionMap
from shared.tracker import Tracker
from tools.display import VPSDisplay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("main")

_SHUTDOWN = False


def _handle_signal(sig, frame) -> None:
    global _SHUTDOWN
    logger.info("Shutdown signal received")
    _SHUTDOWN = True


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VPS Inertial positioning system")
    p.add_argument("--headless", action="store_true", help="Disable display window")
    p.add_argument("--config", default="config/params.yaml", metavar="PATH",
                   help="Path to params.yaml (default: config/params.yaml)")
    return p.parse_args()


def load_config(path: str = "config/params.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def init_logger(log_cfg: dict) -> csv.writer:
    log_dir = Path(log_cfg['log_dir'])
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = log_dir / f"flight_{ts}.log"
    fh = open(log_path, "w", newline="")
    writer = csv.writer(fh)
    writer.writerow([
        "timestamp_ns", "pos_n", "pos_e", "pos_d",
        "vel_n", "vel_e", "vel_d",
        "q_w", "q_x", "q_y", "q_z",
        "fix_accepted", "innovation_m",
        "track_quality", "match_count", "inlier_count",
    ])
    logger.info("Logging to %s", log_path)
    return writer, fh


def main() -> None:
    args = _parse_args()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    cfg = load_config(args.config)

    region_map = RegionMap(cfg['region_map'])
    camera = CameraSource(cfg['camera'])
    tracker = Tracker(cfg['tracker'])
    matcher = Matcher(cfg['matcher'], region_map)
    matcher.set_fov(cfg['camera']['fov_deg'])
    fix_quality = FixQuality(cfg['fix_quality'])
    imu_pre = IMUPreintegrator(cfg['imu'])
    eskf = ESKF(cfg['eskf'])
    eskf.set_imu_noise(cfg['imu'])
    bridge = MAVLinkBridge(cfg['mavlink'])

    imu_pre.start()
    bridge.start()
    display = VPSDisplay(headless=args.headless)

    log_writer, log_fh = init_logger(cfg['logging'])

    frames_since_match = cfg['matcher']['min_match_interval_frames']
    last_flush = time.time()
    last_R: np.ndarray | None = None
    last_raw_fix = None

    logger.info("VPS Inertial main loop starting (mode %d)", cfg['mavlink']['mode'])

    try:
        while not _SHUTDOWN:
            frame, ts_ns = camera.get_frame()
            track_result = tracker.update(frame)

            imu_delta = imu_pre.get_delta()
            if eskf.state.initialized and imu_delta.dt > 0:
                eskf.predict(imu_delta)
                imu_pre.update_attitude(eskf.state.attitude)
                imu_pre.update_bias(eskf.state.accel_bias, eskf.state.gyro_bias)

            state = eskf.state
            altitude_m = float(-state.position[2]) if state.initialized else 50.0
            attitude_q = state.attitude

            frames_since_match += 1
            run_matcher = (
                frames_since_match >= cfg['matcher']['min_match_interval_frames']
                or track_result.track_quality < cfg['tracker']['quality_threshold']
                or track_result.flow_magnitude > cfg['tracker']['high_motion_threshold']
            )

            fix_accepted = False
            innovation_m = 0.0
            match_count = 0
            inlier_count = 0

            if run_matcher:
                frames_since_match = 0
                match_result = matcher.match(frame, altitude_m, attitude_q)
                last_raw_fix = match_result
                match_count = match_result.match_count
                inlier_count = match_result.inlier_count

                if match_result.fix_latlon is not None:
                    qr = fix_quality.evaluate(
                        match_result,
                        track_result.track_quality,
                        state,
                        eskf.covariance_15,
                    )
                    if qr.accepted:
                        if not state.initialized:
                            att = _gravity_align(imu_pre)
                            eskf.initialize(
                                (*match_result.fix_latlon, match_result.fix_altitude or 0.0),
                                att,
                            )
                        else:
                            eskf.update(
                                match_result.fix_latlon,
                                match_result.fix_altitude or 0.0,
                                qr.R_matrix,
                            )
                        fix_accepted = True
                        last_R = qr.R_matrix
                        innovation_m = qr.innovation_magnitude
                        logger.info(
                            "Fix accepted inliers=%d innov=%.1fm tq=%.2f",
                            inlier_count, innovation_m, track_result.track_quality,
                        )

            state = eskf.state
            bridge.send(state, last_R, last_raw_fix)

            if display.update(frame, track_result, last_raw_fix, state, fix_accepted):
                logger.info("Quit requested from display")
                break

            if cfg['logging']['log_full_state']:
                p = state.position
                v = state.velocity
                q = state.attitude
                log_writer.writerow([
                    ts_ns,
                    *p, *v, *q,
                    int(fix_accepted), innovation_m,
                    track_result.track_quality, match_count, inlier_count,
                ])

            now = time.time()
            if now - last_flush >= cfg['logging']['flush_interval_s']:
                log_fh.flush()
                last_flush = now

    finally:
        display.close()
        camera.release()
        imu_pre.stop()
        bridge.stop()
        log_fh.flush()
        log_fh.close()
        logger.info("VPS Inertial shutdown complete")


def _gravity_align(imu_pre: IMUPreintegrator) -> np.ndarray:
    """Return a quaternion that aligns the IMU body z-axis with gravity (nadir)."""
    return np.array([1.0, 0.0, 0.0, 0.0])


if __name__ == "__main__":
    main()
