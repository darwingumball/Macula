import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrackResult:
    points: np.ndarray       # shape (N, 2), current tracked points
    flow_magnitude: float    # mean optical flow in pixels
    track_quality: float     # 0.0 to 1.0
    needs_reinit: bool       # True if point count below threshold


class Tracker:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._prev_frame: np.ndarray | None = None
        self._prev_points: np.ndarray | None = None

        self._lk_params = dict(
            winSize=(config['lk_window_size'], config['lk_window_size']),
            maxLevel=config['lk_max_level'],
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )

    def update(self, frame: np.ndarray) -> TrackResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        if self._prev_frame is None or self._prev_points is None or len(self._prev_points) == 0:
            self._prev_frame = gray
            self._prev_points = self._detect(gray)
            return TrackResult(
                points=self._prev_points,
                flow_magnitude=0.0,
                track_quality=1.0 if len(self._prev_points) >= self._cfg['min_points'] else 0.0,
                needs_reinit=len(self._prev_points) < self._cfg['min_points'],
            )

        pts_fwd, status_fwd, _ = cv2.calcOpticalFlowPyrLK(
            self._prev_frame, gray, self._prev_points, None, **self._lk_params
        )

        if pts_fwd is None or status_fwd is None:
            self._prev_frame = gray
            self._prev_points = self._detect(gray)
            return TrackResult(
                points=self._prev_points,
                flow_magnitude=0.0,
                track_quality=0.0,
                needs_reinit=True,
            )

        pts_bwd, status_bwd, _ = cv2.calcOpticalFlowPyrLK(
            gray, self._prev_frame, pts_fwd, None, **self._lk_params
        )

        fb_error = np.linalg.norm(self._prev_points - pts_bwd, axis=2).squeeze()
        good = (
            (status_fwd.squeeze() == 1)
            & (status_bwd.squeeze() == 1)
            & (fb_error < self._cfg['fb_error_threshold'])
        )

        good_pts = pts_fwd[good].reshape(-1, 2)
        prev_pts_good = self._prev_points[good].reshape(-1, 2)

        flow_vecs = good_pts - prev_pts_good
        flow_magnitude = float(np.mean(np.linalg.norm(flow_vecs, axis=1))) if len(flow_vecs) else 0.0

        good_pts = self._filter_by_distance(good_pts, self._cfg['min_point_distance'])

        needs_reinit = len(good_pts) < self._cfg['min_points']
        if needs_reinit:
            new_pts = self._detect(gray, existing=good_pts)
            good_pts = np.vstack([good_pts, new_pts]) if len(good_pts) else new_pts
            good_pts = good_pts[:self._cfg['max_points']]

        track_quality = float(np.clip(len(good_pts) / self._cfg['max_points'], 0.0, 1.0))

        self._prev_frame = gray
        self._prev_points = good_pts.reshape(-1, 1, 2).astype(np.float32)

        return TrackResult(
            points=good_pts,
            flow_magnitude=flow_magnitude,
            track_quality=track_quality,
            needs_reinit=needs_reinit,
        )

    def _detect(self, gray: np.ndarray, existing: np.ndarray | None = None) -> np.ndarray:
        corners = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=self._cfg['max_points'],
            qualityLevel=0.01,
            minDistance=self._cfg['min_point_distance'],
            blockSize=7,
            useHarrisDetector=False,
        )
        if corners is None:
            return np.empty((0, 2), dtype=np.float32)

        pts = corners.reshape(-1, 2)

        if existing is not None and len(existing) > 0:
            pts = self._filter_by_distance(pts, self._cfg['min_point_distance'], mask=existing)

        return pts.astype(np.float32)

    @staticmethod
    def _filter_by_distance(
        pts: np.ndarray,
        min_dist: float,
        mask: np.ndarray | None = None,
    ) -> np.ndarray:
        if len(pts) == 0:
            return pts

        keep = []
        accepted = list(mask) if mask is not None and len(mask) else []

        for p in pts:
            if accepted:
                dists = np.linalg.norm(np.array(accepted) - p, axis=1)
                if dists.min() < min_dist:
                    continue
            keep.append(p)
            accepted.append(p)

        return np.array(keep, dtype=np.float32) if keep else np.empty((0, 2), dtype=np.float32)
