import time

import numpy as np
import pytest

from estimator.imu_preintegrator import IMUDelta, IMUPreintegrator

IMU_CFG = {
    'port': '/dev/ttyUSB0',
    'baud': 921600,
    'rate_hz': 200,
    'accel_noise_density': 0.003,
    'gyro_noise_density': 0.0001,
    'accel_random_walk': 0.0001,
    'gyro_random_walk': 0.000001,
    'gravity_ms2': 9.81,
    'time_offset_s': 0.0,
}


def push_n_samples(imu: IMUPreintegrator, n: int, dt_ns: int = 5_000_000) -> None:
    accel = np.array([0.0, 0.0, 9.81])  # gravity, stationary
    gyro = np.zeros(3)
    ts = int(time.time_ns())
    for i in range(n):
        imu.push_sample(accel, gyro, ts + i * dt_ns)


def test_start_and_stop():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    imu.stop()


def test_get_delta_returns_imu_delta():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    push_n_samples(imu, 10)
    delta = imu.get_delta()
    assert isinstance(delta, IMUDelta)
    imu.stop()


def test_delta_shapes():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    push_n_samples(imu, 20)
    delta = imu.get_delta()
    assert delta.delta_p.shape == (3,)
    assert delta.delta_v.shape == (3,)
    assert delta.delta_q.shape == (4,)
    imu.stop()


def test_delta_q_is_unit_quaternion():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    push_n_samples(imu, 20)
    delta = imu.get_delta()
    norm = np.linalg.norm(delta.delta_q)
    assert abs(norm - 1.0) < 1e-6
    imu.stop()


def test_get_delta_resets_accumulator():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    push_n_samples(imu, 20)
    delta1 = imu.get_delta()
    delta2 = imu.get_delta()
    assert delta2.dt == 0.0
    assert np.allclose(delta2.delta_p, 0.0)
    imu.stop()


def test_update_bias():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    imu.update_bias(np.array([0.01, 0.02, 0.03]), np.array([0.001, 0.002, 0.003]))
    imu.stop()


def test_stationary_small_delta():
    imu = IMUPreintegrator(IMU_CFG)
    imu.start()
    # Push gravity-aligned accel — gravity should be subtracted
    accel = np.array([0.0, 0.0, 9.81])
    gyro = np.zeros(3)
    ts = int(time.time_ns())
    dt_ns = 5_000_000
    for i in range(40):
        imu.push_sample(accel, gyro, ts + i * dt_ns)
    delta = imu.get_delta()
    # With perfect gravity subtraction, net accel in world = 0 => small delta
    assert np.linalg.norm(delta.delta_v) < 1.0
    imu.stop()
