import logging
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraError(Exception):
    pass


class CameraSource:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        fx = config['fx']
        fy = config['fy']
        cx = config['cx']
        cy = config['cy']
        dist = np.array(config['distortion_coeffs'], dtype=np.float64)

        self._K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
        self._dist = dist
        self._undistort_map: tuple | None = None

        self._cap = cv2.VideoCapture(config['device_id'])
        if not self._cap.isOpened():
            raise CameraError(f"Cannot open camera device {config['device_id']}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config['width'])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config['height'])
        self._cap.set(cv2.CAP_PROP_FPS, config['fps'])

        if fx > 0 and fy > 0:
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            new_K, _ = cv2.getOptimalNewCameraMatrix(self._K, self._dist, (w, h), 1)
            map1, map2 = cv2.initUndistortRectifyMap(
                self._K, self._dist, None, new_K, (w, h), cv2.CV_16SC2
            )
            self._undistort_map = (map1, map2)
            self._K = new_K
            logger.debug("Undistortion maps initialized")
        else:
            logger.debug("Camera intrinsics not set — skipping undistortion")

    def get_frame(self) -> tuple[np.ndarray, int]:
        ret, frame = self._cap.read()
        timestamp_ns = time.time_ns()

        if not ret or frame is None:
            raise CameraError("Failed to capture frame from camera")

        if self._undistort_map is not None:
            frame = cv2.remap(frame, self._undistort_map[0], self._undistort_map[1],
                              cv2.INTER_LINEAR)

        return frame, timestamp_ns

    def release(self) -> None:
        if self._cap.isOpened():
            self._cap.release()
        logger.debug("Camera released")

    @property
    def intrinsics(self) -> np.ndarray:
        return self._K.copy()
