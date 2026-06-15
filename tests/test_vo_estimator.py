import numpy as np
import pytest

from shared.vo_estimator import VOEstimator, VOResult

CAM_CFG = {'fx': 800.0, 'fy': 800.0, 'cx': 320.0, 'cy': 240.0}
ATTITUDE_LEVEL = np.array([1.0, 0.0, 0.0, 0.0])  # identity — level flight


def make_flow(n: int = 20, dx: float = 0.0, dy: float = 0.0):
    rng = np.random.default_rng(0)
    prev = rng.uniform(50, 590, (n, 2)).astype(np.float32)
    curr = prev + np.array([dx, dy], dtype=np.float32)
    return curr, prev


def test_returns_vo_result():
    vo = VOEstimator(CAM_CFG)
    curr, prev = make_flow()
    result = vo.estimate(curr, prev, 50.0, ATTITUDE_LEVEL, 1 / 30)
    assert isinstance(result, VOResult)


def test_zero_flow_gives_near_zero_velocity():
    vo = VOEstimator(CAM_CFG)
    curr, prev = make_flow(dx=0.0, dy=0.0)
    result = vo.estimate(curr, prev, 50.0, ATTITUDE_LEVEL, 1 / 30)
    assert result.valid
    assert result.speed_ms < 0.1


def test_forward_flow_gives_positive_north():
    # Upward image flow (negative dy) → UAV moving forward → positive North velocity
    vo = VOEstimator(CAM_CFG)
    curr, prev = make_flow(dy=-5.0)  # features shift up → UAV moving forward
    result = vo.estimate(curr, prev, 50.0, ATTITUDE_LEVEL, 1 / 30)
    assert result.valid
    assert result.vel_ned[0] > 0, "Forward flow should yield positive North velocity"


def test_uncalibrated_camera_returns_invalid():
    vo = VOEstimator({'fx': 0.0, 'fy': 0.0, 'cx': 0.0, 'cy': 0.0})
    curr, prev = make_flow()
    result = vo.estimate(curr, prev, 50.0, ATTITUDE_LEVEL, 1 / 30)
    assert not result.valid


def test_too_few_points_returns_invalid():
    vo = VOEstimator(CAM_CFG)
    curr = np.zeros((3, 2), dtype=np.float32)
    prev = np.zeros((3, 2), dtype=np.float32)
    result = vo.estimate(curr, prev, 50.0, ATTITUDE_LEVEL, 1 / 30)
    assert not result.valid


def test_speed_scales_with_altitude():
    vo = VOEstimator(CAM_CFG)
    curr, prev = make_flow(dy=-5.0)
    r_low = vo.estimate(curr, prev, 25.0, ATTITUDE_LEVEL, 1 / 30)
    r_high = vo.estimate(curr, prev, 100.0, ATTITUDE_LEVEL, 1 / 30)
    assert r_high.speed_ms > r_low.speed_ms
