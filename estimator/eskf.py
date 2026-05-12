import logging
import math
from dataclasses import dataclass, field

import numpy as np

from estimator.imu_preintegrator import IMUDelta

logger = logging.getLogger(__name__)

# World-frame origin (set on first fix, used by fix_quality for NED conversion)
ORIGIN_LAT: float = 0.0
ORIGIN_LON: float = 0.0
ORIGIN_ALT: float = 0.0


@dataclass
class ESKFState:
    position: np.ndarray     # shape (3,) NED meters from origin
    velocity: np.ndarray     # shape (3,) m/s NED
    attitude: np.ndarray     # shape (4,) quaternion w,x,y,z
    accel_bias: np.ndarray   # shape (3,) m/s^2
    gyro_bias: np.ndarray    # shape (3,) rad/s
    timestamp_ns: int
    initialized: bool


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


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([
        [0, -v[2], v[1]],
        [v[2], 0, -v[0]],
        [-v[1], v[0], 0],
    ])


def _quat_to_rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1-2*(y*y+z*z),   2*(x*y-w*z),   2*(x*z+w*y)],
        [  2*(x*y+w*z), 1-2*(x*x+z*z),   2*(y*z-w*x)],
        [  2*(x*z-w*y),   2*(y*z+w*x), 1-2*(x*x+y*y)],
    ])


class ESKF:
    _STATE_DIM = 16
    _ERR_DIM = 15  # δp(3) δv(3) δθ(3) δba(3) δbg(3)

    def __init__(self, config: dict) -> None:
        self._cfg = config

        self._pos = np.zeros(3)
        self._vel = np.zeros(3)
        self._att = np.array([1.0, 0.0, 0.0, 0.0])
        self._ba = np.zeros(3)
        self._bg = np.zeros(3)
        self._ts_ns: int = 0
        self._initialized = False

        self._P = self._init_covariance()
        self._Q = self._build_process_noise(config)

    def _init_covariance(self) -> np.ndarray:
        cfg = self._cfg
        diag = np.concatenate([
            np.full(3, cfg['init_pos_std_m'] ** 2),
            np.full(3, cfg['init_vel_std_ms'] ** 2),
            np.full(3, cfg['init_att_std_rad'] ** 2),
            np.full(3, cfg['init_accel_bias_std'] ** 2),
            np.full(3, cfg['init_gyro_bias_std'] ** 2),
        ])
        return np.diag(diag)

    @staticmethod
    def _build_process_noise(config: dict) -> np.ndarray:
        # Build Q from params in the parent 'imu' section
        # config here is eskf section; imu noise passed separately
        Q = np.zeros((15, 15))
        return Q

    def set_imu_noise(self, imu_config: dict) -> None:
        an = imu_config['accel_noise_density']
        gn = imu_config['gyro_noise_density']
        aw = imu_config['accel_random_walk']
        gw = imu_config['gyro_random_walk']
        rate = imu_config['rate_hz']
        dt = 1.0 / rate

        Q = np.zeros((15, 15))
        Q[0:3, 0:3] = np.eye(3) * (an * dt) ** 2
        Q[3:6, 3:6] = np.eye(3) * (an * dt) ** 2
        Q[6:9, 6:9] = np.eye(3) * (gn * dt) ** 2
        Q[9:12, 9:12] = np.eye(3) * (aw * dt) ** 2
        Q[12:15, 12:15] = np.eye(3) * (gw * dt) ** 2
        self._Q = Q

    def initialize(
        self,
        initial_fix: tuple[float, float, float],
        initial_attitude: np.ndarray,
    ) -> None:
        global ORIGIN_LAT, ORIGIN_LON, ORIGIN_ALT
        ORIGIN_LAT, ORIGIN_LON, ORIGIN_ALT = initial_fix

        self._pos = np.zeros(3)
        self._vel = np.zeros(3)
        self._att = initial_attitude / np.linalg.norm(initial_attitude)
        self._ba = np.zeros(3)
        self._bg = np.zeros(3)
        self._P = self._init_covariance()
        self._initialized = True
        logger.info(
            "ESKF initialized at (%.6f, %.6f, %.1f m)",
            ORIGIN_LAT, ORIGIN_LON, ORIGIN_ALT,
        )

    def predict(self, imu_delta: IMUDelta) -> None:
        if not self._initialized:
            return

        dt = imu_delta.dt
        if dt <= 0:
            return

        dp = imu_delta.delta_p
        dv = imu_delta.delta_v
        dq = imu_delta.delta_q

        self._pos += dp
        self._vel += dv
        self._att = _quat_multiply(self._att, dq)
        self._att /= np.linalg.norm(self._att)
        self._ts_ns = imu_delta.timestamp_ns

        R_body = _quat_to_rot(self._att)
        F = np.eye(15)
        F[0:3, 3:6] = np.eye(3) * dt
        F[3:6, 6:9] = -R_body @ _skew(dv / dt) * dt
        F[3:6, 9:12] = -R_body * dt
        F[6:9, 12:15] = -np.eye(3) * dt

        self._P = F @ self._P @ F.T + self._Q * dt
        self._clamp_covariance()

        self._ba = np.clip(self._ba, -self._cfg['max_accel_bias'], self._cfg['max_accel_bias'])
        self._bg = np.clip(self._bg, -self._cfg['max_gyro_bias'], self._cfg['max_gyro_bias'])

    def update(
        self,
        fix_latlon: tuple[float, float],
        fix_alt: float,
        R_matrix: np.ndarray,
    ) -> None:
        lat, lon = fix_latlon
        north = (lat - ORIGIN_LAT) * 111320.0
        east = (lon - ORIGIN_LON) * 111320.0 * math.cos(math.radians(ORIGIN_LAT))
        down = -(fix_alt - ORIGIN_ALT)
        z = np.array([north, east, down])

        H = np.zeros((3, 15))
        H[0:3, 0:3] = np.eye(3)

        y = z - self._pos

        S = H @ self._P @ H.T + R_matrix
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            logger.warning("ESKF update: singular S matrix, skipping")
            return

        K = self._P @ H.T @ S_inv

        dx = K @ y

        self._pos += dx[0:3]
        self._vel += dx[3:6]
        dtheta = dx[6:9]
        dq = _exp_map(dtheta)
        self._att = _quat_multiply(self._att, dq)
        self._att /= np.linalg.norm(self._att)
        self._ba += dx[9:12]
        self._bg += dx[12:15]

        I_KH = np.eye(15) - K @ H
        self._P = I_KH @ self._P @ I_KH.T + K @ R_matrix @ K.T
        self._P = 0.5 * (self._P + self._P.T)
        self._clamp_covariance()

        logger.debug("ESKF updated pos=(%.1f, %.1f, %.1f)", *self._pos)

    def _clamp_covariance(self) -> None:
        max_p = self._cfg['max_pos_std_m'] ** 2
        max_v = self._cfg['max_vel_std_ms'] ** 2
        for i in range(3):
            self._P[i, i] = min(self._P[i, i], max_p)
            self._P[3+i, 3+i] = min(self._P[3+i, 3+i], max_v)
        self._P = np.maximum(self._P, 0)
        np.fill_diagonal(self._P, np.maximum(np.diag(self._P), 1e-12))

    @property
    def state(self) -> ESKFState:
        return ESKFState(
            position=self._pos.copy(),
            velocity=self._vel.copy(),
            attitude=self._att.copy(),
            accel_bias=self._ba.copy(),
            gyro_bias=self._bg.copy(),
            timestamp_ns=self._ts_ns,
            initialized=self._initialized,
        )

    @property
    def covariance(self) -> np.ndarray:
        # Return 16x16 covariance with dummy row/col for quaternion vs rotation vector
        P16 = np.zeros((16, 16))
        P16[:6, :6] = self._P[:6, :6]
        P16[6:9, 6:9] = self._P[6:9, 6:9]
        P16[10:16, 10:16] = self._P[9:15, 9:15]
        return P16

    @property
    def covariance_15(self) -> np.ndarray:
        return self._P.copy()
