# VPS Inertial — Architecture and Build Specification

**Author:** Evan Schneider  
**Purpose:** Complete system specification for Claude Code to implement  
**Target hardware:** NVIDIA Jetson Orin Nano + global shutter camera + IMU  
**Autopilot:** PX4 via MAVLink  
**Line budget:** < 3,000 lines of functional code  

---

## 1. System Definition

### What This System Does

A real-time visual-inertial positioning system for fast-moving UAVs (quadrotor and fixed-wing) that:

1. Captures frames from a downward-facing global shutter camera
2. Tracks features across frames using optical flow for high-rate relative motion
3. Matches frames against a pre-prepared georeferenced satellite mosaic for absolute position fixes
4. Fuses visual fixes with IMU measurements in an error-state Kalman filter
5. Outputs a georeferenced pose estimate over MAVLink to PX4

### What This System Does Not Do

- It is not a full SLAM system. There is no map building, loop closure, or global bundle adjustment.
- It is not a target tracking system. It estimates the host vehicle's own position only.
- It does not replace the PX4 flight controller. It feeds PX4 EKF2 as an external vision source.
- It does not use GPS at runtime. GPS is used only for ground-truth validation in evaluation.

### Design Constraints

- **Sub 3,000 lines** of functional code across all modules
- **Runs on Orin Nano** — ARM Cortex-A78AE CPU + Ampere GPU, CUDA 11.4+, 8GB RAM
- **PyTorch dependency** is acceptable for SuperPoint and LightGlue (runs on Orin GPU)
- **PX4 compatible** via MAVLink protocol, no ROS dependency in the core pipeline
- **Hardware-ready** — no simulation dependency, tested against real sensors from day one
- **Single estimator** with two operational modes, not two parallel estimators
- **All parameters** in `config/params.yaml`, never hardcoded in source files
- **Each module independently testable** with its own test file

---

## 2. Operational Modes

The system has two modes controlled by a single flag in `params.yaml`. The codebase is the same for both; only the output behavior of `mavlink_bridge.py` changes.

### Mode 1 — Validation Mode (start here)

```
Your pipeline produces a visual fix with covariance.
mavlink_bridge.py sends it to PX4 as VISION_POSITION_ESTIMATE.
PX4 EKF2 fuses it with its own IMU internally.
Your ESKF runs in parallel but its output is logged only, not sent to PX4.
```

Use this mode until Step 9 of the hardware validation sequence is complete. It lets you validate the visual frontend and MAVLink integration without trusting your own estimator with flight control.

### Mode 2 — Primary Mode (after validation)

```
Your ESKF fuses visual fixes with IMU pre-integration.
mavlink_bridge.py sends the fused pose to PX4 as ATT_POS_MOCAP.
PX4 EKF2 treats it as a pre-fused external pose estimate.
Your estimator is now the primary position source.
```

Switch to this mode only after offline replay validation confirms your ESKF matches or beats PX4 EKF2 on the same logged data.

---

## 3. Complete Data Flow

```
HARDWARE INPUTS
───────────────────────────────────────────────────────────────────
Camera (1080p, global shutter, 30+ fps)
  └── camera_source.py
        - Capture frame with hardware timestamp
        - Apply lens undistortion using calibrated intrinsics
        - Output: (frame: np.ndarray, timestamp_ns: int)

IMU (200-400 Hz, accelerometer + gyroscope)
  └── imu_preintegrator.py (runs continuously in background thread)
        - Integrate acceleration and angular velocity between camera frames
        - Estimate and subtract accelerometer and gyroscope bias
        - Compensate for gravity using current attitude from ESKF
        - Output: integrated delta_position, delta_velocity, delta_attitude
                  per camera frame interval, with timestamp

───────────────────────────────────────────────────────────────────
TRACKING LAYER  (runs every frame, ~30 Hz)
───────────────────────────────────────────────────────────────────
tracker.py
  Input:  current frame, previous frame, previous tracked points
  Process:
    1. If tracked point count drops below threshold, re-detect
       using FAST corner detector on current frame
    2. Track existing points to current frame using
       Lucas-Kanade pyramidal optical flow (cv2.calcOpticalFlowPyrLK)
    3. Filter by forward-backward error to reject bad tracks
    4. Filter by minimum distance to avoid point clustering
    5. Compute mean optical flow magnitude as motion estimate
  Output: (tracked_points: list, flow_magnitude: float,
           track_quality: float 0-1, needs_reinit: bool)

  Role in estimator:
    - track_quality feeds fix_quality.py confidence weighting
    - flow_magnitude used to adapt matcher update rate
      (high motion = more frequent absolute fix attempts)
    - needs_reinit triggers SuperPoint re-detection in matcher.py

───────────────────────────────────────────────────────────────────
MATCHING LAYER  (runs at 2-5 Hz, or when track quality drops)
───────────────────────────────────────────────────────────────────
matcher.py
  Input:  current frame, current altitude from ESKF state,
          current attitude quaternion from ESKF state,
          region_map reference
  Process:
    1. Use altitude and attitude to compute ground footprint
       of camera view (not assumed nadir — attitude-corrected)
    2. Extract corresponding crop from satellite mosaic at
       correct scale for current altitude (GSD matching)
    3. Run SuperPoint on both query frame and mosaic crop
       to extract keypoints and descriptors
    4. Run LightGlue to find correspondences between
       query and mosaic keypoints
    5. Filter matches by LightGlue per-match confidence score
       (threshold in params.yaml: lightglue_min_confidence)
    6. Run RANSAC homography estimation on remaining matches
    7. Compute georeferenced lat/lon fix from homography
       and mosaic metadata
  Output: (fix_latlon: tuple or None,
           fix_altitude: float or None,
           inlier_count: int,
           mean_match_confidence: float,
           match_count: int)

  Returns None if fewer than params.yaml min_inliers matches
  survive RANSAC.

───────────────────────────────────────────────────────────────────
FIX QUALITY  (runs when matcher produces a fix)
───────────────────────────────────────────────────────────────────
fix_quality.py
  Input:  matcher output, tracker track_quality, ESKF state covariance
  Process:
    1. Compute base position uncertainty from LightGlue
       mean_match_confidence:
         R_base = params.yaml base_vision_noise / mean_match_confidence
    2. Scale by inlier count:
         R_scaled = R_base * (params.yaml inlier_scale / inlier_count)
    3. Scale by track quality (low track quality = less trust in fix):
         R_final = R_scaled / track_quality
    4. Mahalanobis gate: compute innovation between fix and
       ESKF predicted position, reject if gate > params.yaml mahal_gate
    5. Absolute innovation gate: reject fix if distance from
       ESKF predicted position > params.yaml max_fix_jump_m
  Output: (accepted: bool, R_matrix: np.ndarray 3x3,
           innovation_magnitude: float)

───────────────────────────────────────────────────────────────────
REGION MAP
───────────────────────────────────────────────────────────────────
region_map.py
  Input:  params.yaml mosaic path, altitude, attitude
  Process:
    1. Load satellite mosaic and metadata.json at startup
    2. On query: compute expected ground footprint given
       current altitude and camera FOV from params.yaml
    3. Apply attitude rotation to footprint corners
       (non-nadir correction for fixed-wing banked turns)
    4. Extract and return correctly scaled mosaic crop
    5. Provide georef_to_latlon(pixel_x, pixel_y, metadata)
       conversion function for matcher output
  Output: mosaic crop (np.ndarray), georef conversion function

───────────────────────────────────────────────────────────────────
ESTIMATOR  (core loop)
───────────────────────────────────────────────────────────────────
eskf.py — Error-State Kalman Filter

  State vector (16 elements):
    p  [0:3]   position          (lat, lon, alt) in NED meters from origin
    v  [3:6]   velocity          (north, east, down) m/s
    q  [6:10]  attitude          quaternion (w, x, y, z)
    ba [10:13] accelerometer bias (m/s^2)
    bg [13:16] gyroscope bias     (rad/s)

  Error state (same dimension, represents deviation from nominal):
    δp, δv, δθ (rotation error vector, 3-element), δba, δbg

  Initialization:
    - Position from first accepted visual fix
    - Velocity zero
    - Attitude from IMU static alignment (gravity vector)
    - Biases zero (converge over first 30 seconds of flight)
    - Covariance from params.yaml initial_covariance values

  Predict (called at IMU rate, ~200 Hz):
    Input:  IMU pre-integrated delta from imu_preintegrator.py
    Process:
      1. Propagate nominal state through rigid body kinematics
         using IMU pre-integrated deltas
      2. Compute state transition matrix F from current state
      3. Propagate error state covariance: P = F*P*F' + Q
         where Q is process noise from IMU noise model in params.yaml
      4. Clamp covariance diagonal to prevent divergence
    Output: updated nominal state, updated covariance P

  Update (called when fix_quality.py accepts a visual fix):
    Input:  accepted fix (lat, lon, alt), R_matrix from fix_quality.py
    Process:
      1. Compute measurement residual: y = fix - H * nominal_state
      2. Compute innovation covariance: S = H*P*H' + R
      3. Compute Kalman gain: K = P*H' * inv(S)
      4. Compute error state correction: δx = K * y
      5. Inject error state into nominal state (reset step):
           p_new  = p + δp
           v_new  = v + δv
           q_new  = q ⊗ Exp(δθ)    (quaternion composition)
           ba_new = ba + δba
           bg_new = bg + δbg
      6. Update covariance: P = (I - K*H) * P
      7. Symmetrize P to prevent numerical drift
    Output: corrected nominal state, updated covariance P

  Output (at camera frame rate, ~30 Hz):
    position, velocity, attitude quaternion, position covariance 3x3

───────────────────────────────────────────────────────────────────
IMU PRE-INTEGRATOR
───────────────────────────────────────────────────────────────────
imu_preintegrator.py
  Runs in background thread at full IMU rate (200-400 Hz)
  Input:  raw IMU samples (accel xyz, gyro xyz, timestamp_ns)
  Process:
    1. Subtract current bias estimate from ESKF state
    2. Rotate acceleration from body to world frame using
       current attitude quaternion from ESKF
    3. Subtract gravity vector (params.yaml gravity_ms2)
    4. Integrate velocity: v += (a_world) * dt
    5. Integrate position: p += v * dt + 0.5 * a_world * dt^2
    6. Integrate attitude: q = q ⊗ Exp(gyro_corrected * dt)
    7. Accumulate delta_p, delta_v, delta_q since last camera frame
    8. On camera frame trigger: package accumulated deltas,
       reset accumulator, return package to ESKF predict()
  Output: IMUDelta(delta_p, delta_v, delta_q, dt_total, timestamp_ns)

───────────────────────────────────────────────────────────────────
MAVLINK BRIDGE
───────────────────────────────────────────────────────────────────
mavlink_bridge.py
  Input:  ESKF output pose, mode flag from params.yaml
  Process:
    Mode 1 — send raw visual fix:
      Build VISION_POSITION_ESTIMATE message from latest
      accepted fix position and fix_quality R_matrix diagonal
      Apply latency compensation: timestamp -= params.yaml ev_delay_ms * 1e6
      Send at fix rate (~2-5 Hz)

    Mode 2 — send fused ESKF pose:
      Build ATT_POS_MOCAP message from ESKF position + attitude
      Apply latency compensation
      Send at 30 Hz (camera frame rate)

    Both modes:
      Send HEARTBEAT at 1 Hz
      Monitor connection health, log warnings if PX4 stops responding
      Never block the main estimation loop (send in separate thread)
  Output: MAVLink UDP packets to PX4

───────────────────────────────────────────────────────────────────
MAIN LOOP
───────────────────────────────────────────────────────────────────
main.py
  1. Load params.yaml
  2. Initialize: region_map, camera_source, tracker, matcher,
                 fix_quality, imu_preintegrator (start thread),
                 eskf, mavlink_bridge (start thread)
  3. Loop at camera frame rate:
     a. Get frame and timestamp from camera_source
     b. Run tracker → track_quality, flow_magnitude
     c. Decide whether to run matcher this frame:
          run if: frames_since_last_match >= min_match_interval
               or track_quality < params.yaml quality_threshold
               or flow_magnitude > params.yaml high_motion_threshold
     d. If running matcher:
          run matcher → fix candidate
          if fix candidate returned:
            run fix_quality → accepted, R_matrix
            if accepted:
              eskf.update(fix, R_matrix)
              log fix acceptance
     e. eskf.predict() with latest IMU delta
     f. mavlink_bridge.send(eskf.state)
     g. Log full state to file for replay_eval.py
```

---

## 4. Repository Structure

```
vps_inertial/
│
├── shared/
│   ├── camera_source.py        # Frame capture, undistortion, timestamping
│   ├── tracker.py              # FAST detection + Lucas-Kanade optical flow
│   ├── matcher.py              # SuperPoint + LightGlue + RANSAC + georef
│   ├── fix_quality.py          # Adaptive covariance + Mahalanobis gate
│   └── region_map.py           # Mosaic load, altitude scaling, georef lookup
│
├── estimator/
│   ├── imu_preintegrator.py    # IMU integration thread, bias correction
│   ├── eskf.py                 # Error-state Kalman filter, 16-state
│   └── mavlink_bridge.py       # MAVLink output, Mode 1 and Mode 2
│
├── tools/
│   ├── prepare_region.py       # One-time mosaic prep from lat/lon bounds
│   ├── calibrate.py            # Camera intrinsic calibration (checkerboard)
│   ├── time_sync.py            # Camera-IMU temporal offset calibration
│   └── replay_eval.py          # Offline ESKF validation against flight logs
│
├── config/
│   └── params.yaml             # All parameters — see Section 6
│
├── tests/
│   ├── test_camera_source.py
│   ├── test_tracker.py
│   ├── test_matcher.py
│   ├── test_fix_quality.py
│   ├── test_region_map.py
│   ├── test_imu_preintegrator.py
│   ├── test_eskf.py
│   └── test_mavlink_bridge.py
│
├── logs/                       # Created at runtime, gitignored
│
├── main.py                     # Top-level loop, wires all modules
├── requirements.txt
└── README.md
```

### Line Budget

```
shared/                  530 lines
estimator/               500 lines
tools/                   480 lines
tests/                   340 lines
main.py + config         150 lines
─────────────────────────────────
Target total            ~2000 lines
Remaining budget        ~1000 lines
```

---

## 5. Module Interface Contracts

Every module must respect these interfaces exactly. Claude Code must not add parameters or return values not listed here without updating this document first.

### camera_source.py

```python
class CameraSource:
    def __init__(self, config: dict): ...
    def get_frame(self) -> tuple[np.ndarray, int]:
        # Returns (undistorted_frame_bgr, timestamp_nanoseconds)
        # Blocks until next frame is available
        # Never returns None; raises CameraError on hardware failure
    def release(self) -> None: ...
```

### tracker.py

```python
class Tracker:
    def __init__(self, config: dict): ...
    def update(self, frame: np.ndarray) -> TrackResult: ...

@dataclass
class TrackResult:
    points: np.ndarray          # shape (N, 2), current tracked points
    flow_magnitude: float       # mean optical flow in pixels
    track_quality: float        # 0.0 to 1.0
    needs_reinit: bool          # True if point count below threshold
```

### matcher.py

```python
class Matcher:
    def __init__(self, config: dict, region_map: RegionMap): ...
    def match(self,
              frame: np.ndarray,
              altitude_m: float,
              attitude_q: np.ndarray) -> MatchResult: ...

@dataclass
class MatchResult:
    fix_latlon: tuple[float, float] | None   # (lat, lon) or None
    fix_altitude: float | None
    inlier_count: int
    mean_confidence: float
    match_count: int
```

### fix_quality.py

```python
class FixQuality:
    def __init__(self, config: dict): ...
    def evaluate(self,
                 match: MatchResult,
                 track_quality: float,
                 eskf_state: ESKFState,
                 eskf_cov: np.ndarray) -> QualityResult: ...

@dataclass
class QualityResult:
    accepted: bool
    R_matrix: np.ndarray        # shape (3, 3) measurement noise covariance
    innovation_magnitude: float
    rejection_reason: str | None
```

### region_map.py

```python
class RegionMap:
    def __init__(self, config: dict): ...
    def get_crop(self,
                 altitude_m: float,
                 attitude_q: np.ndarray) -> tuple[np.ndarray, callable]: ...
    # Returns (mosaic_crop, georef_fn)
    # georef_fn(pixel_x, pixel_y) -> (lat, lon)
```

### imu_preintegrator.py

```python
class IMUPreintegrator:
    def __init__(self, config: dict): ...
    def start(self) -> None:                # starts background thread
    def push_sample(self,
                    accel: np.ndarray,      # shape (3,) m/s^2
                    gyro: np.ndarray,       # shape (3,) rad/s
                    timestamp_ns: int) -> None: ...
    def get_delta(self) -> IMUDelta:        # blocks briefly if needed
    def update_bias(self,
                    accel_bias: np.ndarray,
                    gyro_bias: np.ndarray) -> None: ...
    def stop(self) -> None: ...

@dataclass
class IMUDelta:
    delta_p: np.ndarray         # shape (3,) position delta meters NED
    delta_v: np.ndarray         # shape (3,) velocity delta m/s NED
    delta_q: np.ndarray         # shape (4,) attitude delta quaternion
    dt: float                   # total integration time seconds
    timestamp_ns: int           # end timestamp
```

### eskf.py

```python
class ESKF:
    def __init__(self, config: dict): ...
    def initialize(self,
                   initial_fix: tuple[float, float, float],
                   initial_attitude: np.ndarray) -> None: ...
    def predict(self, imu_delta: IMUDelta) -> None: ...
    def update(self,
               fix_latlon: tuple[float, float],
               fix_alt: float,
               R_matrix: np.ndarray) -> None: ...

    @property
    def state(self) -> ESKFState: ...
    @property
    def covariance(self) -> np.ndarray: ...  # shape (16, 16)

@dataclass
class ESKFState:
    position: np.ndarray        # shape (3,) NED meters from origin
    velocity: np.ndarray        # shape (3,) m/s NED
    attitude: np.ndarray        # shape (4,) quaternion w,x,y,z
    accel_bias: np.ndarray      # shape (3,) m/s^2
    gyro_bias: np.ndarray       # shape (3,) rad/s
    timestamp_ns: int
    initialized: bool
```

### mavlink_bridge.py

```python
class MAVLinkBridge:
    def __init__(self, config: dict): ...
    def start(self) -> None: ...
    def send(self,
             state: ESKFState,
             R_matrix: np.ndarray | None,
             raw_fix: MatchResult | None) -> None: ...
    # Internally selects Mode 1 or Mode 2 from config
    # send() is non-blocking; queues message for send thread
    def stop(self) -> None: ...
```

---

## 6. Configuration File

`config/params.yaml` — complete with all parameters and their purpose.
Claude Code must load this file at startup and pass relevant subsections
to each module constructor. No hardcoded values anywhere in source files.

```yaml
# ── Camera ────────────────────────────────────────────────────────────────
camera:
  device_id: 0                  # /dev/video0 or CSI index
  width: 1920
  height: 1080
  fps: 30
  # Intrinsics from calibrate.py output — fill before first flight
  fx: 0.0
  fy: 0.0
  cx: 0.0
  cy: 0.0
  distortion_coeffs: [0.0, 0.0, 0.0, 0.0, 0.0]
  # Extrinsics: camera body frame relative to IMU body frame
  # Rotation as quaternion w,x,y,z and translation in meters
  cam_to_imu_q: [1.0, 0.0, 0.0, 0.0]
  cam_to_imu_t: [0.0, 0.0, 0.0]
  # Horizontal field of view in degrees
  fov_deg: 90.0

# ── IMU ───────────────────────────────────────────────────────────────────
imu:
  port: "/dev/ttyUSB0"          # serial port or "mavlink" to read from PX4
  baud: 921600
  rate_hz: 200
  # IMU noise model — from datasheet or Allan variance analysis
  accel_noise_density: 0.003    # m/s^2/sqrt(Hz)
  gyro_noise_density: 0.0001    # rad/s/sqrt(Hz)
  accel_random_walk: 0.0001     # m/s^3/sqrt(Hz)
  gyro_random_walk: 0.000001    # rad/s^2/sqrt(Hz)
  gravity_ms2: 9.81
  # Camera-IMU time offset in seconds (positive = camera lags IMU)
  # Measure with time_sync.py before first flight
  time_offset_s: 0.0

# ── Tracker ───────────────────────────────────────────────────────────────
tracker:
  max_points: 300               # maximum tracked points
  min_points: 80                # reinitialize if below this
  fast_threshold: 20            # FAST detector threshold
  lk_window_size: 21            # Lucas-Kanade window size
  lk_max_level: 3               # pyramid levels
  fb_error_threshold: 1.0       # forward-backward error reject threshold px
  min_point_distance: 20        # minimum pixels between tracked points
  # track_quality below this triggers forced matcher run
  quality_threshold: 0.5
  # flow magnitude above this (pixels) triggers more frequent matching
  high_motion_threshold: 15.0

# ── Matcher ───────────────────────────────────────────────────────────────
matcher:
  # SuperPoint model weights path
  superpoint_weights: "weights/superpoint_v1.pth"
  # LightGlue model weights path
  lightglue_weights: "weights/lightglue_v0.1_disk.pth"
  # Minimum LightGlue per-match confidence to keep a match
  lightglue_min_confidence: 0.5
  # Minimum inliers after RANSAC to accept a fix
  min_inliers: 12
  # RANSAC reprojection threshold in pixels
  ransac_threshold: 4.0
  # Minimum frames between matcher runs (at 30 fps, 6 = 5 Hz)
  min_match_interval_frames: 6
  # Run on GPU
  use_gpu: true

# ── Fix Quality ───────────────────────────────────────────────────────────
fix_quality:
  # Base position measurement noise in meters (1-sigma)
  # Scaled by confidence and inlier count
  base_vision_noise_m: 5.0
  # Inlier count scaling reference (noise halves at this count)
  inlier_scale: 20
  # Mahalanobis gate in sigma (reject if innovation > this)
  mahal_gate: 5.0
  # Absolute position jump gate in meters
  # Reject fix if further than this from predicted position
  max_fix_jump_m: 50.0

# ── Region Map ────────────────────────────────────────────────────────────
region_map:
  mosaic_path: "region/satellite.png"
  metadata_path: "region/metadata.json"
  # Altitude limits for mosaic scaling
  min_altitude_m: 5.0
  max_altitude_m: 200.0

# ── ESKF ──────────────────────────────────────────────────────────────────
eskf:
  # Initial state covariance diagonal values
  init_pos_std_m: 10.0
  init_vel_std_ms: 1.0
  init_att_std_rad: 0.1
  init_accel_bias_std: 0.1
  init_gyro_bias_std: 0.01
  # Covariance diagonal clamp to prevent divergence
  max_pos_std_m: 500.0
  max_vel_std_ms: 50.0
  # Bias drift limits
  max_accel_bias: 0.5
  max_gyro_bias: 0.05
  # Maximum time since last fix before warning
  fix_timeout_s: 10.0

# ── MAVLink ───────────────────────────────────────────────────────────────
mavlink:
  # UDP target for PX4 (companion computer to flight controller)
  host: "127.0.0.1"
  port: 14550
  # System and component IDs
  system_id: 1
  component_id: 195             # MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY
  # Operational mode:
  #   1 = send raw visual fix as VISION_POSITION_ESTIMATE
  #   2 = send fused ESKF pose as ATT_POS_MOCAP
  mode: 1
  # Pipeline latency in milliseconds — measure with time_sync.py
  # This value is subtracted from the message timestamp
  ev_delay_ms: 50
  # Send rate for Mode 2 in Hz
  send_rate_hz: 30

# ── Logging ───────────────────────────────────────────────────────────────
logging:
  log_dir: "logs"
  # Log fields per frame: timestamp, eskf_state, fix_accepted,
  # innovation, track_quality, match_count, inlier_count
  log_full_state: true
  # Flush interval in seconds
  flush_interval_s: 1.0

# ── PX4 EKF2 parameter recommendations ───────────────────────────────────
# Set these on the PX4 flight controller before first flight.
# These are not read by this software; they are here as documentation.
px4_ekf2_params:
  EKF2_AID_MASK: 24             # external vision position + yaw
  EKF2_HGT_MODE: 3              # external vision altitude
  EKF2_EV_DELAY: 50             # match mavlink.ev_delay_ms
  EKF2_EV_NOISE_MD: 0           # use covariance from message
  EKF2_EV_POS_X: 0.1
  EKF2_EV_POS_Y: 0.1
  EKF2_EV_POS_Z: 0.15
  EKF2_EV_GATE: 5               # innovation gate in sigma
```

---

## 7. Key Implementation Details

Claude Code must implement these correctly. They are not obvious from the interface contracts alone.

### Quaternion convention

Use scalar-first convention throughout: q = [w, x, y, z]. This matches PX4 and MAVLink. The error state attitude uses a 3-element rotation vector δθ (not a quaternion). The injection step is:

```python
# Error injection for attitude
delta_q = Exp(delta_theta)   # rotation vector to quaternion
q_new = quaternion_multiply(q_nominal, delta_q)
q_new = q_new / np.linalg.norm(q_new)   # renormalize
```

### Coordinate frames

- **NED body frame**: x forward, y right, z down — used by PX4 and IMU
- **Camera frame**: x right, y down, z forward (standard OpenCV)
- **World frame**: NED, fixed to takeoff point as origin
- All ESKF state is in world NED frame
- Mosaic coordinates are in geographic lat/lon; convert to NED meters
  from origin using a local flat-earth approximation:
  ```python
  # At mid-latitudes this is accurate to <1m over 10km
  north = (lat - origin_lat) * 111320.0
  east  = (lon - origin_lon) * 111320.0 * cos(radians(origin_lat))
  ```

### IMU thread safety

The IMU pre-integrator runs in a background thread. The ESKF predict() and update() methods run in the main loop thread. Use a threading.Lock around the accumulated delta state. The bias update from ESKF to IMU pre-integrator must also be locked.

### Timestamp handling

All timestamps are in nanoseconds as Python int (not float, to avoid floating-point precision loss). MAVLink `time_usec` fields are microseconds; convert with `timestamp_ns // 1000`. PX4 uses its own boot-time clock; the `ev_delay_ms` parameter compensates for this by backdating message timestamps.

### SuperPoint and LightGlue on Orin

Use the `kornia` or `hloc` implementations. Run both models on CUDA. The mosaic crop should be resized to 640x480 before being passed to SuperPoint to keep inference time under 30ms. The full resolution query frame can be used for SuperPoint keypoint detection since the Orin GPU handles it, but benchmark this and fall back to 640x480 if latency exceeds your frame budget.

### Attitude-corrected ground footprint

This is critical for fixed-wing correctness. Given current attitude quaternion q and camera FOV:

```python
# Rotate camera boresight (0, 0, 1) in camera frame
# through camera-to-body and body-to-world transforms
# to get the actual ground-pointing direction
# Then compute where the camera frustum corners intersect
# the ground plane at current altitude
# Use these corners to extract the correct mosaic crop
```

Do not assume the camera is pointing straight down. At a 30-degree bank angle the nadir error is significant at operational altitudes.

### Fix rate adaptation

The main loop decides whether to run the matcher each frame. The logic is:

```python
frames_since_match += 1
run_matcher = (
    frames_since_match >= config['min_match_interval_frames']
    or track_result.track_quality < config['quality_threshold']
    or track_result.flow_magnitude > config['high_motion_threshold']
)
```

This means during high-speed flight or when tracking degrades, the matcher runs more frequently to compensate for faster drift between fixes.

---

## 8. Tools Specification

### prepare_region.py

CLI tool, run once before flight.

```
Usage: python tools/prepare_region.py \
         --lat-min 37.75 --lat-max 37.80 \
         --lon-min -122.45 --lon-max -122.40 \
         --zoom 17 \
         --output region/

Output:
  region/satellite.png    — georeferenced satellite mosaic
  region/metadata.json    — origin lat/lon, GSD m/px, image size
```

`metadata.json` format:
```json
{
  "origin_lat": 37.75,
  "origin_lon": -122.45,
  "gsd_m_per_px": 0.597,
  "width_px": 4096,
  "height_px": 4096,
  "zoom": 17
}
```

### calibrate.py

CLI tool, run once per camera or if camera is remounted.

```
Usage: python tools/calibrate.py \
         --device 0 \
         --board-size 9x6 \
         --square-size 0.025 \
         --output config/

Output: prints fx, fy, cx, cy, distortion_coeffs
        to paste into config/params.yaml
        reprojection error must be < 0.5px to pass
```

### time_sync.py

CLI tool, run once per hardware configuration.

```
Usage: python tools/time_sync.py \
         --camera-device 0 \
         --imu-port /dev/ttyUSB0

Process: flashes an LED or displays a bright frame,
         measures timestamp difference between camera
         detection and IMU vibration signature
Output: prints time_offset_s to paste into params.yaml
```

### replay_eval.py

Offline validation tool. Takes a flight log from `logs/` and replays IMU and visual fix data through the ESKF, comparing the output against PX4 EKF2 state or GPS ground truth if available.

```
Usage: python tools/replay_eval.py \
         --log logs/flight_001.log \
         --ground-truth logs/flight_001_gps.csv \
         --output logs/flight_001_eval/

Output:
  - Position error vs time plot
  - RMS, P90, P95 error
  - Map update acceptance rate
  - ESKF vs EKF2 comparison if PX4 log provided
```

---

## 9. Hardware Validation Sequence

Complete all steps in order. Do not skip steps. Each step has a clear pass/fail condition.

```
STEP 1 — Software build and unit tests
  Run: pytest tests/
  Pass: all tests pass
  Common failure: SuperPoint/LightGlue import error
    Fix: pip install kornia, check CUDA availability

STEP 2 — Camera calibration
  Run: python tools/calibrate.py
  Pass: reprojection error < 0.5 pixels
  Common failure: poor board detection
    Fix: better lighting, slower board movement, more images

STEP 3 — Time synchronization
  Run: python tools/time_sync.py
  Pass: time_offset_s measured and set in params.yaml
  Common failure: IMU not detected
    Fix: check serial port, baud rate in params.yaml

STEP 4 — Region preparation
  Run: python tools/prepare_region.py for test area
  Pass: satellite.png and metadata.json created
        mosaic visually correct for target area

STEP 5 — Bench end-to-end run
  Run: python main.py (drone stationary on desk over mosaic printout)
  Pass: MAVLink messages visible in QGroundControl
        VISION_POSITION_ESTIMATE fields non-zero and stable
        Position error < 5m from known desk position

STEP 6 — Bench hand-carry test
  Carry drone slowly over mosaic printout on floor
  Pass: position estimate tracks motion in QGroundControl
        No fix jumps > max_fix_jump_m
        Track quality stays above 0.4

STEP 7 — PX4 EKF2 parameter configuration
  Set all px4_ekf2_params from params.yaml on flight controller
  Set EKF2_EV_DELAY to measured latency from Step 3
  Pass: QGroundControl shows estimator_status.vision_pos_valid = true
        EKF2 innovations stay small (< 2 sigma)

STEP 8 — Offline replay validation
  Run: python tools/replay_eval.py on Step 6 log
  Pass: ESKF RMS within 20% of EKF2 on same data
        No filter divergence events in log

STEP 9 — Tethered hover (quadrotor only, safety pilot required)
  Physical tether attached, 5m altitude, 60 second hold
  Pass: position hold stable, no toilet bowling
        ESKF log RMS within 20% of EKF2
        No fix rejection rate above 30%

STEP 10 — Free hover (quadrotor, safety pilot ready)
  Same area as Step 9, no tether
  Pass: position hold stable, comparable to GPS hold
        Pilot can release sticks without drift

STEP 11 — Square pattern flight (quadrotor, 3-5 m/s)
  Fly a 20m square at low altitude
  Pass: position error stays bounded during turns
        No growing drift over multiple laps
        Logs show consistent fix acceptance

STEP 12 — Switch to Mode 2
  Set mavlink.mode: 2 in params.yaml
  Repeat Step 10
  Pass: equivalent stability to Mode 1
        ESKF estimate visible in QGroundControl via custom MAVLink

STEP 13 — Speed and altitude envelope expansion
  Gradually increase speed and altitude
  Log max_reliable_speed_ms for each altitude
  Update params.yaml accordingly

STEP 14 — Fixed-wing integration
  Attitude-corrected footprint active (verify in logs)
  Altitude scaling verified across altitude range
  Pass: stable fix acceptance through banked turns
        No systematic position error correlated with bank angle
```

---

## 10. Dependencies

```
# requirements.txt

# Core
numpy>=1.24
opencv-python>=4.8
scipy>=1.11
PyYAML>=6.0

# Feature matching
torch>=2.0           # SuperPoint and LightGlue
kornia>=0.7          # or use hloc for SuperPoint/LightGlue
# Alternative: pip install lightglue (standalone package)

# MAVLink
pymavlink>=2.4.37

# Evaluation tools only
matplotlib>=3.7
pandas>=2.0

# Testing
pytest>=7.4
```

Model weights (not pip installable — download separately):
```
weights/superpoint_v1.pth
weights/lightglue_v0.1_disk.pth

Source: https://github.com/cvg/LightGlue
        python -m lightglue.download
```

---

## 11. Instructions for Claude Code

Read this entire document before writing any code. Then follow these rules:

**Build order:**
1. `config/params.yaml` — complete file, all fields
2. `shared/region_map.py` — needed by everything else
3. `shared/camera_source.py`
4. `shared/tracker.py`
5. `shared/matcher.py`
6. `shared/fix_quality.py`
7. `estimator/imu_preintegrator.py`
8. `estimator/eskf.py`
9. `estimator/mavlink_bridge.py`
10. `main.py`
11. `tools/prepare_region.py`
12. `tools/calibrate.py`
13. `tools/time_sync.py`
14. `tools/replay_eval.py`
15. All test files, one per module

**Rules:**
- No hardcoded values. Every numeric parameter comes from `params.yaml`.
- No abstraction layers not in this document. Do not invent base classes or plugin systems.
- Each module must be importable and testable independently without hardware.
- Use type hints throughout. Every function has a return type annotation.
- Use `@dataclass` for all data transfer objects (TrackResult, MatchResult, etc.).
- Log at DEBUG level inside modules, INFO level in main.py only.
- All file paths in config are relative to the project root.
- Thread safety: use `threading.Lock` wherever shared state exists between threads.
- The ESKF must handle uninitialized state gracefully — `state.initialized = False` until first fix is accepted.
- Do not import torch at module level in files that do not use it — it is slow to import and should not delay startup of non-GPU modules.
- Write one test per public method minimum. Tests must run without camera or IMU hardware using mocked inputs.
- Total line count across all source files must stay under 3,000. If a module is approaching its budget, simplify rather than expand.

