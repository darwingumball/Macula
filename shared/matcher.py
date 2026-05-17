import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shared.region_map import RegionMap

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    fix_latlon: tuple[float, float] | None
    fix_altitude: float | None
    inlier_count: int
    mean_confidence: float
    match_count: int


class Matcher:
    def __init__(self, config: dict, region_map: "RegionMap") -> None:
        self._cfg = config
        self._region_map = region_map
        self._device = self._resolve_device()
        self._extractor = None
        self._lightglue = None
        self._fov_deg: float = 90.0

    def _resolve_device(self) -> str:
        if not self._cfg.get('use_gpu', True):
            return 'cpu'
        try:
            import torch
            return 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            return 'cpu'

    def _load_models(self) -> None:
        if self._extractor is not None:
            return
        try:
            import torch
            from lightglue import LightGlue, SuperPoint
            kp = self._cfg.get('max_keypoints', 512)
            self._extractor = SuperPoint(max_num_keypoints=kp).eval().to(self._device)
            self._lightglue = LightGlue(features='superpoint').eval().to(self._device)
            logger.debug("SuperPoint and LightGlue loaded on %s", self._device)
        except ImportError as e:
            raise ImportError(
                "lightglue package not installed. Run: pip install lightglue"
            ) from e

    def set_fov(self, fov_deg: float) -> None:
        self._fov_deg = fov_deg

    def match(
        self,
        frame: np.ndarray,
        altitude_m: float,
        attitude_q: np.ndarray,
    ) -> MatchResult:
        self._load_models()

        try:
            mosaic_crop, georef_fn = self._region_map.get_crop(
                altitude_m, attitude_q, fov_deg=self._fov_deg
            )
        except Exception as e:
            logger.debug("region_map.get_crop failed: %s", e)
            return MatchResult(None, None, 0, 0.0, 0)

        size = self._cfg.get('resize_px', 640)
        query_gray = self._to_gray_resized(frame, size)
        ref_gray = self._to_gray_resized(mosaic_crop, size)

        try:
            import torch
            from lightglue.utils import rbd

            query_t = self._to_tensor(query_gray)
            ref_t = self._to_tensor(ref_gray)

            with torch.no_grad():
                feats0 = self._extractor.extract(query_t.to(self._device))
                feats1 = self._extractor.extract(ref_t.to(self._device))
                matches01 = self._lightglue({'image0': feats0, 'image1': feats1})

            feats0, feats1, matches01 = rbd(feats0), rbd(feats1), rbd(matches01)
            kp0 = feats0['keypoints'].cpu().numpy()
            kp1 = feats1['keypoints'].cpu().numpy()
            m_idx = matches01['matches'].cpu().numpy()
            scores = matches01['matching_scores0'].cpu().numpy()

        except Exception as e:
            logger.debug("Feature extraction/matching failed: %s", e)
            return MatchResult(None, None, 0, 0.0, 0)

        if len(m_idx) < self._cfg['min_inliers']:
            return MatchResult(None, None, 0, 0.0, len(m_idx))

        min_conf = self._cfg['lightglue_min_confidence']
        conf_mask = scores[m_idx[:, 0]] >= min_conf if len(m_idx) else np.array([], dtype=bool)
        m_idx = m_idx[conf_mask]
        conf_scores = scores[m_idx[:, 0]] if len(m_idx) else np.array([])

        if len(m_idx) < self._cfg['min_inliers']:
            return MatchResult(None, None, 0, float(np.mean(conf_scores)) if len(conf_scores) else 0.0, len(m_idx))

        pts0 = kp0[m_idx[:, 0]].astype(np.float32)
        pts1 = kp1[m_idx[:, 1]].astype(np.float32)

        H, inlier_mask = cv2.findHomography(
            pts0, pts1,
            cv2.RANSAC,
            self._cfg['ransac_threshold'],
        )

        if H is None or inlier_mask is None:
            return MatchResult(None, None, 0, float(np.mean(conf_scores)), len(m_idx))

        inliers = inlier_mask.squeeze().astype(bool)
        inlier_count = int(inliers.sum())
        mean_confidence = float(np.mean(conf_scores[inliers])) if inlier_count else 0.0

        if inlier_count < self._cfg['min_inliers']:
            return MatchResult(None, None, inlier_count, mean_confidence, len(m_idx))

        h, w = query_gray.shape[:2]
        center = np.array([[[w / 2.0, h / 2.0]]], dtype=np.float32)
        center_ref = cv2.perspectiveTransform(center, H)
        ref_x, ref_y = center_ref[0, 0]

        lat, lon = georef_fn(float(ref_x), float(ref_y))

        logger.debug(
            "Match: %d/%d inliers conf=%.3f fix=(%.6f,%.6f)",
            inlier_count, len(m_idx), mean_confidence, lat, lon,
        )

        return MatchResult(
            fix_latlon=(lat, lon),
            fix_altitude=altitude_m,
            inlier_count=inlier_count,
            mean_confidence=mean_confidence,
            match_count=len(m_idx),
        )

    @staticmethod
    def _to_gray_resized(img: np.ndarray, size: int = 640) -> np.ndarray:
        if img.ndim == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        h, w = gray.shape[:2]
        if max(h, w) != size:
            scale = size / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        return gray

    @staticmethod
    def _to_tensor(gray: np.ndarray):
        import torch
        t = torch.from_numpy(gray).float() / 255.0
        return t.unsqueeze(0).unsqueeze(0)


class AsyncMatcher:
    """Wraps Matcher to run match() in a background thread.

    submit() is non-blocking and silently drops requests while a match is
    already in progress — the main loop keeps running at camera FPS.
    pop_result() returns and clears the latest finished result, or None.
    """

    def __init__(self, matcher: Matcher) -> None:
        self._matcher = matcher
        self._lock = threading.Lock()
        self._pending: MatchResult | None = None
        self._busy = False

    def submit(self, frame: np.ndarray, altitude_m: float, attitude_q: np.ndarray) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True
        threading.Thread(
            target=self._run,
            args=(frame.copy(), altitude_m, attitude_q),
            daemon=True,
            name="matcher",
        ).start()

    def _run(self, frame: np.ndarray, altitude_m: float, attitude_q: np.ndarray) -> None:
        result = self._matcher.match(frame, altitude_m, attitude_q)
        with self._lock:
            self._pending = result
            self._busy = False

    def pop_result(self) -> MatchResult | None:
        with self._lock:
            r = self._pending
            self._pending = None
            return r

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy
