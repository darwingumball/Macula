import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


CAMERA_CFG = {
    'device_id': 0,
    'width': 640,
    'height': 480,
    'fps': 30,
    'fx': 0.0,
    'fy': 0.0,
    'cx': 0.0,
    'cy': 0.0,
    'distortion_coeffs': [0.0, 0.0, 0.0, 0.0, 0.0],
    'cam_to_imu_q': [1.0, 0.0, 0.0, 0.0],
    'cam_to_imu_t': [0.0, 0.0, 0.0],
    'fov_deg': 90.0,
}


@pytest.fixture
def mock_cap():
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (True, fake_frame)
    cap.get.return_value = 640
    return cap


def test_get_frame_returns_ndarray_and_timestamp(mock_cap):
    with patch('cv2.VideoCapture', return_value=mock_cap):
        from shared.camera_source import CameraSource
        cam = CameraSource(CAMERA_CFG)
        frame, ts = cam.get_frame()

    assert isinstance(frame, np.ndarray)
    assert frame.shape == (480, 640, 3)
    assert isinstance(ts, int)
    assert ts > 0


def test_get_frame_timestamp_is_nanoseconds(mock_cap):
    with patch('cv2.VideoCapture', return_value=mock_cap):
        from shared.camera_source import CameraSource
        cam = CameraSource(CAMERA_CFG)
        _, ts = cam.get_frame()

    now_ns = time.time_ns()
    assert abs(ts - now_ns) < 5_000_000_000  # within 5 seconds


def test_camera_error_on_failed_read(mock_cap):
    mock_cap.read.return_value = (False, None)
    with patch('cv2.VideoCapture', return_value=mock_cap):
        from shared.camera_source import CameraError, CameraSource
        cam = CameraSource(CAMERA_CFG)
        with pytest.raises(CameraError):
            cam.get_frame()


def test_camera_error_on_open_failure():
    bad_cap = MagicMock()
    bad_cap.isOpened.return_value = False
    with patch('cv2.VideoCapture', return_value=bad_cap):
        from shared.camera_source import CameraError, CameraSource
        with pytest.raises(CameraError):
            CameraSource(CAMERA_CFG)


def test_release_closes_cap(mock_cap):
    with patch('cv2.VideoCapture', return_value=mock_cap):
        from shared.camera_source import CameraSource
        cam = CameraSource(CAMERA_CFG)
        cam.release()

    mock_cap.release.assert_called_once()
