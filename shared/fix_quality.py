import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from estimator.eskf import ESKFState
    from shared.matcher import MatchResult

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    accepted: bool
    R_matrix: np.ndarray         # shape (3, 3) measurement noise covariance
    innovation_magnitude: float
    rejection_reason: str | None


class FixQuality:
    def __init__(self, config: dict) -> None:
        self._cfg = config

    def evaluate(
        self,
        match: "MatchResult",
        track_quality: float,
        eskf_state: "ESKFState",
        eskf_cov: np.ndarray,
    ) -> QualityResult:
        if match.fix_latlon is None:
            return QualityResult(False, np.eye(3), 0.0, "no_fix")

        conf = max(match.mean_confidence, 1e-6)
        inliers = max(match.inlier_count, 1)
        tq = max(track_quality, 1e-6)

        base = self._cfg['base_vision_noise_m']
        r_base = base / conf
        r_scaled = r_base * (self._cfg['inlier_scale'] / inliers)
        r_final = r_scaled / tq

        R = np.diag([r_final ** 2, r_final ** 2, (r_final * 2.0) ** 2])

        innovation_mag = 0.0
        if not eskf_state.initialized:
            return QualityResult(True, R, 0.0, None)

        lat, lon = match.fix_latlon
        fix_ned = self._latlon_to_ned(lat, lon, match.fix_altitude or 0.0, eskf_state)
        pred_pos = eskf_state.position
        innovation = fix_ned - pred_pos
        innovation_mag = float(np.linalg.norm(innovation))

        if innovation_mag > self._cfg['max_fix_jump_m']:
            logger.debug("Fix rejected: jump %.1f m > %.1f m", innovation_mag, self._cfg['max_fix_jump_m'])
            return QualityResult(False, R, innovation_mag, "max_fix_jump")

        H = np.zeros((3, 15))
        H[0:3, 0:3] = np.eye(3)
        P = eskf_cov
        S = H @ P @ H.T + R
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return QualityResult(False, R, innovation_mag, "singular_S")

        mahal = float(np.sqrt(innovation @ S_inv @ innovation))
        if mahal > self._cfg['mahal_gate']:
            logger.debug("Fix rejected: Mahalanobis %.2f > %.2f", mahal, self._cfg['mahal_gate'])
            return QualityResult(False, R, innovation_mag, "mahalanobis_gate")

        logger.debug("Fix accepted: inliers=%d conf=%.3f innov=%.2f m", inliers, conf, innovation_mag)
        return QualityResult(True, R, innovation_mag, None)

    @staticmethod
    def _latlon_to_ned(
        lat: float,
        lon: float,
        alt: float,
        eskf_state: "ESKFState",
    ) -> np.ndarray:
        from estimator.eskf import ORIGIN_LAT, ORIGIN_LON, ORIGIN_ALT
        north = (lat - ORIGIN_LAT) * 111320.0
        east = (lon - ORIGIN_LON) * 111320.0 * math.cos(math.radians(ORIGIN_LAT))
        down = -(alt - ORIGIN_ALT)
        return np.array([north, east, down])
