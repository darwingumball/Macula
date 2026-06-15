# VPS Inertial — Claude Code Project Guide

## What This Is

Real-time visual-inertial positioning for UAVs. Matches downward camera frames against a pre-prepared satellite mosaic, fuses visual fixes with IMU via an Error-State Kalman Filter, outputs MAVLink to PX4.

**Not SLAM. Not target tracking. No ROS. No GPS at runtime.**

Full spec: `VPS_INERTIAL_ARCHITECTURE.md`

---

## Hard Constraints

- **< 3,000 lines** of functional Python (only .py files count)
- **No hardcoded values** — every numeric parameter comes from `config/params.yaml`
- **No interfaces not in the spec** — adding a parameter or return value requires updating the architecture doc
- **Each module independently testable** without camera/IMU hardware

---

## Module Map

```
shared/
  camera_source.py    CameraSource — frame capture + undistortion
  tracker.py          Tracker — FAST + Lucas-Kanade optical flow
  vo_estimator.py     VOEstimator — pixel flow → NED velocity (alternative odometry)
  matcher.py          Matcher — SuperPoint + LightGlue + RANSAC + georef
  fix_quality.py      FixQuality — adaptive covariance, Mahalanobis gate
  region_map.py       RegionMap — mosaic load, altitude scaling, crop

estimator/
  imu_preintegrator.py  IMUPreintegrator — background thread, bias correction
  eskf.py               ESKF — 16-state error-state Kalman filter
  mavlink_bridge.py     MAVLinkBridge — Mode 1 (raw fix) / Mode 2 (fused pose)

tools/
  display.py            VPSDisplay — live overlay window, headless flag
  prepare_region.py     mosaic download CLI
  calibrate.py          camera intrinsic calibration CLI
  time_sync.py          camera-IMU temporal offset CLI
  replay_eval.py        offline ESKF validation

main.py               top-level loop, wires everything
config/params.yaml    all parameters (Orin Nano defaults)
config/params_rpi5.yaml  RPi5 overrides (CPU-only, lower res)
```

---

## Interface Contracts (do not change without updating arch doc)

| Class | Key method | Return |
|---|---|---|
| `CameraSource` | `get_frame()` | `(ndarray, int)` frame + timestamp_ns |
| `Tracker` | `update(frame)` | `TrackResult` (includes `flow_curr`, `flow_prev`) |
| `VOEstimator` | `estimate(flow_curr, flow_prev, alt, q, dt)` | `VOResult` |
| `Matcher` | `match(frame, alt, q)` | `MatchResult` |
| `FixQuality` | `evaluate(match, tq, state, cov)` | `QualityResult` |
| `RegionMap` | `get_crop(alt, q)` | `(crop, georef_fn)` |
| `IMUPreintegrator` | `get_delta()` | `IMUDelta` |
| `ESKF` | `predict(delta)`, `update(fix, alt, R)` | — |
| `MAVLinkBridge` | `send(state, R, raw_fix)` | — |
| `VPSDisplay` | `update(frame, track, match, state, fix, vo_result=None)` | `bool` (quit?) |

---

## Key Implementation Rules

**Quaternion**: scalar-first `[w, x, y, z]`. Error state uses 3-element `δθ`.

**Coordinates**: ESKF state in NED meters from takeoff origin. Lat/lon → NED:
```python
north = (lat - origin_lat) * 111320.0
east  = (lon - origin_lon) * 111320.0 * cos(radians(origin_lat))
```

**Thread safety**: `threading.Lock` on all shared state between IMU thread and main loop.

**Timestamps**: always `int` nanoseconds. Convert for MAVLink: `ts_ns // 1000`.

**GPU**: Matcher lazy-loads torch. `use_gpu: false` in params → CPU fallback. Never import torch at module level outside matcher/display.

**Uninit guard**: `eskf.state.initialized = False` until first accepted fix. Main loop checks before using state.

---

## Two Operational Modes

Set `mavlink.mode` in params.yaml:
- **Mode 1** (default, validate first): sends raw visual fix as `VISION_POSITION_ESTIMATE`. ESKF runs but output is log-only.
- **Mode 2** (after validation): sends fused ESKF pose as `ATT_POS_MOCAP`. Switch only after `replay_eval.py` confirms ESKF within 20% of EKF2.

---

## Platform Differences

| | Orin Nano | RPi5 |
|---|---|---|
| Config | `config/params.yaml` | `config/params_rpi5.yaml` |
| GPU | CUDA (torch from NVIDIA wheel) | CPU-only (torch from pytorch.org/cpu) |
| Match rate | 5 Hz (`min_match_interval_frames: 6`) | 1 Hz (`min_match_interval_frames: 30`) |
| Camera res | 1920×1080 | 1280×720 |
| CSI camera | GStreamer nvarguscamerasrc string as `device_id` | libcamerasrc GStreamer string |
| USB camera | `device_id: 0` | `device_id: 0` |
| Display | `python main.py` | `python main.py --config config/params_rpi5.yaml` |
| Headless | `--headless` flag | `--headless` flag |
| Setup | `./setup_orin.sh` | `./setup_rpi5.sh` |

---

## Running

```bash
# Windowed display
python main.py
python main.py --config config/params_rpi5.yaml

# Headless
python main.py --headless
python main.py --config config/params_rpi5.yaml --headless

# Tests (no hardware)
pytest tests/ -q

# Tools
python tools/prepare_region.py --lat-min ... --lat-max ... --lon-min ... --lon-max ... --zoom 17 --output region/
python tools/calibrate.py --device 0 --board-size 9x6 --square-size 0.025 --output config/
python tools/replay_eval.py --log logs/flight_001.log --output logs/eval/
```

---

## Validation Order (SETUP.md has full detail)

1. `pytest tests/` — all pass
2. Calibrate camera (< 0.5 px reproj error)
3. Time sync camera-IMU
4. Prepare region mosaic
5. Bench stationary run — MAVLink visible in QGC, error < 5 m
6. Hand-carry tracking test
7. PX4 EKF2 params configured
8. Offline replay eval — ESKF within 20% of EKF2
9. Tethered hover
10. Free hover → Mode 2

---

## Line Budget Status

```
shared/          ~590  (added vo_estimator.py ~55 lines)
estimator/       ~500
tools/           ~600  (display.py +20 lines)
tests/           ~390  (added test_vo_estimator.py ~50 lines)
main.py          ~215
─────────────────────
Estimated total  ~2,295
Remaining        ~705
```

When a module nears its budget: simplify, don't expand.
