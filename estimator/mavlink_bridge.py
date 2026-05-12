import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from estimator.eskf import ESKFState
    from shared.matcher import MatchResult

logger = logging.getLogger(__name__)


class MAVLinkBridge:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._mode = config['mode']
        self._queue: queue.Queue = queue.Queue(maxsize=10)
        self._thread: threading.Thread | None = None
        self._running = False
        self._conn = None
        self._last_heartbeat = 0.0

    def start(self) -> None:
        try:
            from pymavlink import mavutil
            conn_str = f"udpout:{self._cfg['host']}:{self._cfg['port']}"
            self._conn = mavutil.mavlink_connection(
                conn_str,
                source_system=self._cfg['system_id'],
                source_component=self._cfg['component_id'],
            )
            logger.info("MAVLink connection established to %s:%d", self._cfg['host'], self._cfg['port'])
        except ImportError:
            logger.warning("pymavlink not installed — MAVLink output disabled")
            self._conn = None
        except Exception as e:
            logger.warning("MAVLink connection failed: %s — output disabled", e)
            self._conn = None

        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True, name="mavlink-send")
        self._thread.start()

    def send(
        self,
        state: "ESKFState",
        R_matrix: "np.ndarray | None",
        raw_fix: "MatchResult | None",
    ) -> None:
        try:
            self._queue.put_nowait((state, R_matrix, raw_fix))
        except queue.Full:
            pass  # drop frame if send thread is falling behind

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _send_loop(self) -> None:
        while self._running:
            self._send_heartbeat_if_due()
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            state, R_matrix, raw_fix = item
            if self._conn is None:
                continue

            try:
                if self._mode == 1:
                    self._send_vision_position(raw_fix, R_matrix)
                else:
                    self._send_att_pos_mocap(state, R_matrix)
            except Exception as e:
                logger.debug("MAVLink send error: %s", e)

    def _send_heartbeat_if_due(self) -> None:
        if self._conn is None:
            return
        now = time.time()
        if now - self._last_heartbeat >= 1.0:
            try:
                from pymavlink import mavutil
                self._conn.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                    0, 0, 0,
                )
                self._last_heartbeat = now
            except Exception as e:
                logger.debug("Heartbeat send failed: %s", e)

    def _send_vision_position(
        self,
        raw_fix: "MatchResult | None",
        R_matrix: "np.ndarray | None",
    ) -> None:
        if raw_fix is None or raw_fix.fix_latlon is None:
            return

        from estimator.eskf import ORIGIN_LAT, ORIGIN_LON, ORIGIN_ALT
        import math

        lat, lon = raw_fix.fix_latlon
        alt = raw_fix.fix_altitude or ORIGIN_ALT

        north = (lat - ORIGIN_LAT) * 111320.0
        east = (lon - ORIGIN_LON) * 111320.0 * math.cos(math.radians(ORIGIN_LAT))
        down = -(alt - ORIGIN_ALT)

        ev_delay_us = int(self._cfg['ev_delay_ms'] * 1000)
        time_usec = int(time.time() * 1e6) - ev_delay_us

        cov = [0.0] * 21
        if R_matrix is not None:
            cov[0] = float(R_matrix[0, 0])
            cov[6] = float(R_matrix[1, 1])
            cov[11] = float(R_matrix[2, 2])

        self._conn.mav.vision_position_estimate_send(
            time_usec,
            float(north),
            float(east),
            float(down),
            0.0, 0.0, 0.0,  # roll, pitch, yaw (not estimated here)
            cov,
        )
        logger.debug("Sent VISION_POSITION_ESTIMATE NED=(%.1f,%.1f,%.1f)", north, east, down)

    def _send_att_pos_mocap(
        self,
        state: "ESKFState",
        R_matrix: "np.ndarray | None",
    ) -> None:
        if not state.initialized:
            return

        ev_delay_us = int(self._cfg['ev_delay_ms'] * 1000)
        time_usec = int(time.time() * 1e6) - ev_delay_us

        q = state.attitude  # w,x,y,z
        cov = [0.0] * 21
        if R_matrix is not None:
            cov[0] = float(R_matrix[0, 0])
            cov[6] = float(R_matrix[1, 1])
            cov[11] = float(R_matrix[2, 2])

        self._conn.mav.att_pos_mocap_send(
            time_usec,
            [float(q[0]), float(q[1]), float(q[2]), float(q[3])],
            float(state.position[0]),
            float(state.position[1]),
            float(state.position[2]),
            cov,
        )
        logger.debug("Sent ATT_POS_MOCAP pos=(%.1f,%.1f,%.1f)", *state.position)
