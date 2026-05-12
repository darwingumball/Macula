import numpy as np
import pytest

from shared.fix_quality import FixQuality, QualityResult
from shared.matcher import MatchResult
from estimator.eskf import ESKFState


FQ_CFG = {
    'base_vision_noise_m': 5.0,
    'inlier_scale': 20,
    'mahal_gate': 5.0,
    'max_fix_jump_m': 50.0,
}


def uninitialized_state() -> ESKFState:
    return ESKFState(
        position=np.zeros(3),
        velocity=np.zeros(3),
        attitude=np.array([1.0, 0.0, 0.0, 0.0]),
        accel_bias=np.zeros(3),
        gyro_bias=np.zeros(3),
        timestamp_ns=0,
        initialized=False,
    )


def initialized_state(pos=None) -> ESKFState:
    return ESKFState(
        position=np.zeros(3) if pos is None else np.array(pos),
        velocity=np.zeros(3),
        attitude=np.array([1.0, 0.0, 0.0, 0.0]),
        accel_bias=np.zeros(3),
        gyro_bias=np.zeros(3),
        timestamp_ns=0,
        initialized=True,
    )


def good_match() -> MatchResult:
    return MatchResult(
        fix_latlon=(37.75, -122.45),
        fix_altitude=50.0,
        inlier_count=20,
        mean_confidence=0.9,
        match_count=40,
    )


def test_returns_quality_result():
    fq = FixQuality(FQ_CFG)
    result = fq.evaluate(good_match(), 0.8, uninitialized_state(), np.eye(15))
    assert isinstance(result, QualityResult)


def test_none_fix_is_rejected():
    fq = FixQuality(FQ_CFG)
    bad = MatchResult(None, None, 0, 0.0, 0)
    result = fq.evaluate(bad, 0.8, uninitialized_state(), np.eye(15))
    assert not result.accepted
    assert result.rejection_reason == "no_fix"


def test_uninit_state_accepts_first_fix():
    fq = FixQuality(FQ_CFG)
    result = fq.evaluate(good_match(), 0.8, uninitialized_state(), np.eye(15))
    assert result.accepted


def test_r_matrix_shape():
    fq = FixQuality(FQ_CFG)
    result = fq.evaluate(good_match(), 0.8, uninitialized_state(), np.eye(15))
    assert result.R_matrix.shape == (3, 3)


def test_low_confidence_increases_r():
    fq = FixQuality(FQ_CFG)
    low = MatchResult((37.75, -122.45), 50.0, 20, 0.1, 40)
    high = MatchResult((37.75, -122.45), 50.0, 20, 0.9, 40)
    r_low = fq.evaluate(low, 0.8, uninitialized_state(), np.eye(15)).R_matrix
    r_high = fq.evaluate(high, 0.8, uninitialized_state(), np.eye(15)).R_matrix
    assert r_low[0, 0] > r_high[0, 0]


def test_innovation_magnitude_is_nonnegative():
    fq = FixQuality(FQ_CFG)
    result = fq.evaluate(good_match(), 0.8, uninitialized_state(), np.eye(15))
    assert result.innovation_magnitude >= 0.0
