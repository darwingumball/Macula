from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from shared.matcher import MatchResult, Matcher

MATCHER_CFG = {
    'superpoint_weights': 'weights/superpoint_v1.pth',
    'lightglue_weights': 'weights/lightglue_v0.1_disk.pth',
    'lightglue_min_confidence': 0.5,
    'min_inliers': 12,
    'ransac_threshold': 4.0,
    'min_match_interval_frames': 6,
    'use_gpu': False,
}


def make_mock_region_map():
    rm = MagicMock()
    crop = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

    def georef_fn(px, py):
        return (37.75 + px * 1e-6, -122.45 + py * 1e-6)

    rm.get_crop.return_value = (crop, georef_fn)
    return rm


def test_match_returns_match_result_on_import_error():
    rm = make_mock_region_map()
    matcher = Matcher(MATCHER_CFG, rm)

    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    attitude = np.array([1.0, 0.0, 0.0, 0.0])

    with patch.object(matcher, '_load_models', side_effect=ImportError("lightglue not installed")):
        with pytest.raises(ImportError):
            matcher.match(frame, 50.0, attitude)


def test_match_returns_none_fix_when_region_map_fails():
    rm = MagicMock()
    rm.get_crop.side_effect = Exception("outside bounds")
    matcher = Matcher(MATCHER_CFG, rm)

    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    attitude = np.array([1.0, 0.0, 0.0, 0.0])

    with patch.object(matcher, '_load_models'):
        result = matcher.match(frame, 50.0, attitude)

    assert isinstance(result, MatchResult)
    assert result.fix_latlon is None
    assert result.inlier_count == 0


def test_match_result_dataclass_fields():
    mr = MatchResult(
        fix_latlon=(37.75, -122.45),
        fix_altitude=50.0,
        inlier_count=15,
        mean_confidence=0.85,
        match_count=30,
    )
    assert mr.fix_latlon == (37.75, -122.45)
    assert mr.inlier_count == 15
    assert mr.mean_confidence == 0.85


def test_to_gray_resized():
    color = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    gray = Matcher._to_gray_resized(color, size=640)
    assert gray.ndim == 2
    assert max(gray.shape) == 640
