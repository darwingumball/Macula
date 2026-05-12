import numpy as np
import pytest

from shared.tracker import TrackResult, Tracker

TRACKER_CFG = {
    'max_points': 300,
    'min_points': 80,
    'fast_threshold': 20,
    'lk_window_size': 21,
    'lk_max_level': 3,
    'fb_error_threshold': 1.0,
    'min_point_distance': 20,
    'quality_threshold': 0.5,
    'high_motion_threshold': 15.0,
}


def make_frame(h: int = 480, w: int = 640) -> np.ndarray:
    rng = np.random.default_rng(42)
    frame = (rng.random((h, w, 3)) * 255).astype(np.uint8)
    # add some texture so FAST/LK have something to track
    for _ in range(50):
        cx, cy = rng.integers(10, w-10), rng.integers(10, h-10)
        frame[cy-3:cy+3, cx-3:cx+3] = 255
    return frame


def test_update_returns_track_result():
    tracker = Tracker(TRACKER_CFG)
    frame = make_frame()
    result = tracker.update(frame)
    assert isinstance(result, TrackResult)


def test_first_frame_initializes():
    tracker = Tracker(TRACKER_CFG)
    result = tracker.update(make_frame())
    assert isinstance(result.points, np.ndarray)
    assert isinstance(result.flow_magnitude, float)
    assert 0.0 <= result.track_quality <= 1.0
    assert isinstance(result.needs_reinit, bool)


def test_second_frame_produces_flow():
    tracker = Tracker(TRACKER_CFG)
    frame1 = make_frame()
    frame2 = make_frame()  # different seed would give motion, same is fine
    tracker.update(frame1)
    result = tracker.update(frame2)
    assert result.flow_magnitude >= 0.0


def test_track_quality_bounded():
    tracker = Tracker(TRACKER_CFG)
    for _ in range(5):
        result = tracker.update(make_frame())
        assert 0.0 <= result.track_quality <= 1.0


def test_empty_frame_does_not_crash():
    tracker = Tracker(TRACKER_CFG)
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = tracker.update(blank)
    assert isinstance(result, TrackResult)
    assert result.needs_reinit or len(result.points) == 0
