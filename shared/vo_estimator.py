import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VOResult:
    vel_ned: np.ndarray  # [vn, ve, vd] m/s
    speed_ms: float      # horizontal speed magnitude
    valid: bool          # False when uncalibrated or insufficient flow data


class VOEstimator:
    def __init__(self, camera_cfg: dict) -> None:
        self._fx = float(camera_cfg['fx'])
        self._fy = float(camera_cfg['fy'])

    def estimate(
        self,
        flow_curr: np.ndarray,  # (N, 2) current pixel positions
        flow_prev: np.ndarray,  # (N, 2) previous positions, aligned with flow_curr
        altitude_m: float,
        attitude_q: np.ndarray,  # body-to-NED quaternion [w, x, y, z]
        dt_s: float,
    ) -> VOResult:
        _invalid = VOResult(vel_ned=np.zeros(3), speed_ms=0.0, valid=False)

        if len(flow_curr) < 4 or len(flow_prev) < 4:
            return _invalid
        if dt_s <= 0 or altitude_m <= 0 or self._fx <= 0 or self._fy <= 0:
            return _invalid

        flow_px = flow_curr - flow_prev  # (N, 2) pixel displacements

        # Median rejects outlier tracks more robustly than mean
        dx = float(np.median(flow_px[:, 0]))
        dy = float(np.median(flow_px[:, 1]))

        # Nadir camera: image +X = body right (+Y), image +Y = body forward (+X)
        # UAV moving forward → ground shifts backward → features shift up → flow_y < 0
        scale = altitude_m / dt_s
        v_body_x =  dy * scale / self._fy   # forward (North when level)
        v_body_y =  dx * scale / self._fx   # rightward (East when level)
        vel_body = np.array([-v_body_x, v_body_y, 0.0])

        vel_ned = _rotate_vec(attitude_q, vel_body)
        speed = float(np.linalg.norm(vel_ned[:2]))

        logger.debug("VO vel_ned=(%.2f, %.2f) speed=%.2f m/s", vel_ned[0], vel_ned[1], speed)
        return VOResult(vel_ned=vel_ned, speed_ms=speed, valid=True)


def _rotate_vec(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    q = q / np.linalg.norm(q)
    w, x, y, z = q
    t = 2.0 * np.cross(np.array([x, y, z]), v)
    return v + w * t + np.cross(np.array([x, y, z]), t)
