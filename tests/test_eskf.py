import numpy as np
import pytest

from estimator.eskf import ESKF, ESKFState
from estimator.imu_preintegrator import IMUDelta

ESKF_CFG = {
    'init_pos_std_m': 10.0,
    'init_vel_std_ms': 1.0,
    'init_att_std_rad': 0.1,
    'init_accel_bias_std': 0.1,
    'init_gyro_bias_std': 0.01,
    'max_pos_std_m': 500.0,
    'max_vel_std_ms': 50.0,
    'max_accel_bias': 0.5,
    'max_gyro_bias': 0.05,
    'fix_timeout_s': 10.0,
}

IMU_CFG = {
    'accel_noise_density': 0.003,
    'gyro_noise_density': 0.0001,
    'accel_random_walk': 0.0001,
    'gyro_random_walk': 0.000001,
    'rate_hz': 200,
    'gravity_ms2': 9.81,
}


def zero_delta(dt: float = 0.033) -> IMUDelta:
    return IMUDelta(
        delta_p=np.zeros(3),
        delta_v=np.zeros(3),
        delta_q=np.array([1.0, 0.0, 0.0, 0.0]),
        dt=dt,
        timestamp_ns=int(1e9),
    )


def test_initial_state_not_initialized():
    eskf = ESKF(ESKF_CFG)
    assert not eskf.state.initialized


def test_state_is_eskfstate():
    eskf = ESKF(ESKF_CFG)
    state = eskf.state
    assert isinstance(state, ESKFState)


def test_predict_no_op_before_init():
    eskf = ESKF(ESKF_CFG)
    eskf.predict(zero_delta())
    assert not eskf.state.initialized


def test_initialize_sets_initialized():
    eskf = ESKF(ESKF_CFG)
    eskf.set_imu_noise(IMU_CFG)
    eskf.initialize((37.75, -122.45, 50.0), np.array([1.0, 0.0, 0.0, 0.0]))
    assert eskf.state.initialized


def test_state_position_zero_after_init():
    eskf = ESKF(ESKF_CFG)
    eskf.initialize((37.75, -122.45, 50.0), np.array([1.0, 0.0, 0.0, 0.0]))
    assert np.allclose(eskf.state.position, 0.0)


def test_predict_updates_covariance():
    eskf = ESKF(ESKF_CFG)
    eskf.set_imu_noise(IMU_CFG)
    eskf.initialize((37.75, -122.45, 0.0), np.array([1.0, 0.0, 0.0, 0.0]))
    P_before = eskf.covariance_15.copy()
    eskf.predict(zero_delta())
    P_after = eskf.covariance_15
    assert not np.allclose(P_before, P_after)


def test_update_does_not_crash():
    eskf = ESKF(ESKF_CFG)
    eskf.set_imu_noise(IMU_CFG)
    eskf.initialize((37.75, -122.45, 0.0), np.array([1.0, 0.0, 0.0, 0.0]))
    R = np.diag([25.0, 25.0, 100.0])
    eskf.update((37.75, -122.45), 0.0, R)


def test_covariance_shape():
    eskf = ESKF(ESKF_CFG)
    assert eskf.covariance.shape == (16, 16)
    assert eskf.covariance_15.shape == (15, 15)


def test_attitude_normalized_after_predict():
    eskf = ESKF(ESKF_CFG)
    eskf.set_imu_noise(IMU_CFG)
    eskf.initialize((37.75, -122.45, 0.0), np.array([1.0, 0.0, 0.0, 0.0]))
    for _ in range(10):
        eskf.predict(zero_delta())
    norm = np.linalg.norm(eskf.state.attitude)
    assert abs(norm - 1.0) < 1e-6


def test_multiple_predict_update_cycle():
    eskf = ESKF(ESKF_CFG)
    eskf.set_imu_noise(IMU_CFG)
    eskf.initialize((37.75, -122.45, 0.0), np.array([1.0, 0.0, 0.0, 0.0]))
    R = np.diag([25.0, 25.0, 100.0])
    for _ in range(5):
        eskf.predict(zero_delta())
        eskf.update((37.75, -122.45), 0.0, R)
    state = eskf.state
    assert np.isfinite(state.position).all()
    assert np.isfinite(state.velocity).all()
