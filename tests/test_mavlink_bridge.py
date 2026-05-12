import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from estimator.mavlink_bridge import MAVLinkBridge
from estimator.eskf import ESKFState
from shared.matcher import MatchResult

MAVLINK_CFG = {
    'host': '127.0.0.1',
    'port': 14550,
    'system_id': 1,
    'component_id': 195,
    'mode': 1,
    'ev_delay_ms': 50,
    'send_rate_hz': 30,
}


def uninit_state() -> ESKFState:
    return ESKFState(
        position=np.zeros(3),
        velocity=np.zeros(3),
        attitude=np.array([1.0, 0.0, 0.0, 0.0]),
        accel_bias=np.zeros(3),
        gyro_bias=np.zeros(3),
        timestamp_ns=int(time.time_ns()),
        initialized=False,
    )


def init_state() -> ESKFState:
    return ESKFState(
        position=np.array([10.0, 5.0, -50.0]),
        velocity=np.zeros(3),
        attitude=np.array([1.0, 0.0, 0.0, 0.0]),
        accel_bias=np.zeros(3),
        gyro_bias=np.zeros(3),
        timestamp_ns=int(time.time_ns()),
        initialized=True,
    )


def good_fix() -> MatchResult:
    return MatchResult(
        fix_latlon=(37.75, -122.45),
        fix_altitude=50.0,
        inlier_count=15,
        mean_confidence=0.85,
        match_count=30,
    )


@patch('pymavlink.mavutil.mavlink_connection', side_effect=ImportError("pymavlink not installed"))
def test_start_without_pymavlink(mock_conn):
    bridge = MAVLinkBridge(MAVLINK_CFG)
    bridge.start()
    bridge.stop()


def test_send_is_nonblocking():
    bridge = MAVLinkBridge(MAVLINK_CFG)
    with patch('pymavlink.mavutil.mavlink_connection', side_effect=ImportError):
        bridge.start()

    R = np.diag([25.0, 25.0, 100.0])
    t0 = time.time()
    for _ in range(100):
        bridge.send(init_state(), R, good_fix())
    elapsed = time.time() - t0
    assert elapsed < 0.5, "send() should be near-instantaneous"
    bridge.stop()


def test_send_mode_1_does_not_crash():
    bridge = MAVLinkBridge(MAVLINK_CFG)
    mock_mav = MagicMock()
    bridge._conn = mock_mav
    bridge._running = True

    R = np.diag([25.0, 25.0, 100.0])
    bridge._send_vision_position(good_fix(), R)
    mock_mav.mav.vision_position_estimate_send.assert_called_once()


def test_send_mode_2_skips_uninit():
    cfg = dict(MAVLINK_CFG)
    cfg['mode'] = 2
    bridge = MAVLinkBridge(cfg)
    mock_mav = MagicMock()
    bridge._conn = mock_mav

    bridge._send_att_pos_mocap(uninit_state(), None)
    mock_mav.mav.att_pos_mocap_send.assert_not_called()


def test_send_mode_2_sends_when_initialized():
    cfg = dict(MAVLINK_CFG)
    cfg['mode'] = 2
    bridge = MAVLinkBridge(cfg)
    mock_mav = MagicMock()
    bridge._conn = mock_mav

    R = np.diag([25.0, 25.0, 100.0])
    bridge._send_att_pos_mocap(init_state(), R)
    mock_mav.mav.att_pos_mocap_send.assert_called_once()
