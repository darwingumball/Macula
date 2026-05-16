import logging
import time
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

if TYPE_CHECKING:
    from estimator.eskf import ESKFState
    from shared.matcher import MatchResult
    from shared.tracker import TrackResult

logger = logging.getLogger(__name__)

_W, _H = 960, 540


class VPSDisplay:
    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._win = "VPS Inertial"
        self._t: list[float] = []
        if not headless:
            cv2.namedWindow(self._win, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self._win, _W, _H)
            logger.info("Display window initialized (%dx%d)", _W, _H)
        else:
            logger.info("Headless mode — display disabled")

    def update(
        self,
        frame: np.ndarray,
        track: "TrackResult",
        match: Optional["MatchResult"],
        state: "ESKFState",
        fix_accepted: bool,
    ) -> bool:
        """Render frame with overlays. Returns True if quit requested (q/Esc)."""
        now = time.monotonic()
        self._t.append(now)
        self._t = [t for t in self._t if now - t < 2.0]
        fps = len(self._t) / 2.0

        if self._headless:
            logger.debug(
                "fps=%.1f tq=%.2f flow=%.1f fix=%s init=%s",
                fps, track.track_quality, track.flow_magnitude,
                fix_accepted, state.initialized,
            )
            return False

        disp = cv2.resize(frame.copy(), (_W, _H))
        sx, sy = _W / frame.shape[1], _H / frame.shape[0]

        for pt in track.points:
            cv2.circle(disp, (int(pt[0] * sx), int(pt[1] * sy)), 3, (0, 255, 0), -1)

        border = (0, 200, 0) if fix_accepted else (0, 0, 200)
        cv2.rectangle(disp, (0, 0), (_W - 1, _H - 1), border, 3)

        hud = [f"FPS {fps:.0f}  TQ {track.track_quality:.2f}  Flow {track.flow_magnitude:.0f}px"]
        if match is not None:
            hud.append(
                f"Matches {match.match_count}  Inliers {match.inlier_count}  "
                f"Conf {match.mean_confidence:.2f}"
            )
        if state.initialized:
            p = state.position
            hud.append(f"NED  N {p[0]:.1f}  E {p[1]:.1f}  D {p[2]:.1f} m")
        else:
            hud.append("ESKF: waiting for first fix")

        for i, line in enumerate(hud):
            cv2.putText(disp, line, (8, 22 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1, cv2.LINE_AA)

        label, lcolor = ("FIX OK", (0, 200, 0)) if fix_accepted else ("NO FIX", (0, 50, 220))
        cv2.putText(disp, label, (_W - 110, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, lcolor, 2, cv2.LINE_AA)

        bw = int(track.track_quality * 140)
        bar_color = (0, 190, 0) if track.track_quality > 0.5 else (0, 100, 230)
        cv2.rectangle(disp, (8, _H - 18), (148, _H - 8), (60, 60, 60), -1)
        cv2.rectangle(disp, (8, _H - 18), (8 + bw, _H - 8), bar_color, -1)
        cv2.putText(disp, "TQ", (153, _H - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

        cv2.imshow(self._win, disp)
        key = cv2.waitKey(1) & 0xFF
        return key in (ord('q'), 27)

    def close(self) -> None:
        if not self._headless:
            cv2.destroyAllWindows()
