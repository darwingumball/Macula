import logging
import threading
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IMUDelta:
    delta_p: np.ndarray    # shape (3,) position delta meters NED
    delta_v: np.ndarray    # shape (3,) velocity delta m/s NED
    delta_q: np.ndarray    # shape (4,) attitude delta quaternion w,x,y,z
    dt: float              # total integration time seconds
    timestamp_ns: int      # end timestamp


def _quat_multiply(q: np.ndarray, r: np.ndarray) -> np.ndarray:
    w0, x0, y0, z0 = q
    w1, x1, y1, z1 = r
    return np.array([
        w0*w1 - x0*x1 - y0*y1 - z0*z1,
        w0*x1 + x0*w1 + y0*z1 - z0*y1,
        w0*y1 - x0*z1 + y0*w1 + z0*x1,
        w0*z1 + x0*y1 - y0*x1 + z0*w1,
    ])


def _exp_map(omega: np.ndarray) -> np.ndarray:
    angle = np.linalg.norm(omega)
    if angle < 1e-10:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = omega / angle
    s = np.sin(angle / 2.0)
    return np.array([np.cos(angle / 2.0), axis[0]*s, axis[1]*s, axis[2]*s])


def _rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    w, x, y, z = q / np.linalg.norm(q)
    t = 2.0 * np.cross(np.array([x, y, z]), v)
    return v + w * t + np.cross(np.array([x, y, z]), t)


class IMUPreintegrator:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._gravity = np.array([0.0, 0.0, config['gravity_ms2']])  # NED: +z is down

        self._lock = threading.Lock()
        self._accel_bias = np.zeros(3)
        self._gyro_bias = np.zeros(3)

        self._attitude_q = np.array([1.0, 0.0, 0.0, 0.0])
        self._delta_p = np.zeros(3)
        self._delta_v = np.zeros(3)
        self._delta_q = np.array([1.0, 0.0, 0.0, 0.0])
        self._dt_accum = 0.0
        self._last_ts_ns: int | None = None
        self._end_ts_ns: int = 0

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        logger.debug("IMUPreintegrator started (inline integration mode)")

    def push_sample(
        self,
        accel: np.ndarray,
        gyro: np.ndarray,
        timestamp_ns: int,
    ) -> None:
        with self._lock:
            if self._last_ts_ns is None:
                self._last_ts_ns = timestamp_ns
                return

            dt = (timestamp_ns - self._last_ts_ns) * 1e-9
            self._last_ts_ns = timestamp_ns
            self._end_ts_ns = timestamp_ns

            if dt <= 0 or dt > 0.1:
                return

            accel_corrected = accel - self._accel_bias
            gyro_corrected = gyro - self._gyro_bias

            a_world = _rotate_vector(self._attitude_q, accel_corrected) - self._gravity

            self._delta_p += self._delta_v * dt + 0.5 * a_world * dt * dt
            self._delta_v += a_world * dt

            dq = _exp_map(gyro_corrected * dt)
            self._attitude_q = _quat_multiply(self._attitude_q, dq)
            self._attitude_q /= np.linalg.norm(self._attitude_q)

            self._delta_q = _quat_multiply(self._delta_q, dq)
            self._delta_q /= np.linalg.norm(self._delta_q)

            self._dt_accum += dt

    def get_delta(self) -> IMUDelta:
        with self._lock:
            delta = IMUDelta(
                delta_p=self._delta_p.copy(),
                delta_v=self._delta_v.copy(),
                delta_q=self._delta_q.copy(),
                dt=self._dt_accum,
                timestamp_ns=self._end_ts_ns,
            )
            self._delta_p = np.zeros(3)
            self._delta_v = np.zeros(3)
            self._delta_q = np.array([1.0, 0.0, 0.0, 0.0])
            self._dt_accum = 0.0
        return delta

    def update_bias(self, accel_bias: np.ndarray, gyro_bias: np.ndarray) -> None:
        with self._lock:
            self._accel_bias = accel_bias.copy()
            self._gyro_bias = gyro_bias.copy()

    def update_attitude(self, attitude_q: np.ndarray) -> None:
        with self._lock:
            self._attitude_q = attitude_q.copy()

    def stop(self) -> None:
        self._running = False
        logger.debug("IMUPreintegrator stopped")
