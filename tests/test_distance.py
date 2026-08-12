"""Tests for openaq_survey.distance — offline, no API key required."""

import numpy as np
import pytest

from openaq_survey.distance import (
    haversine_km,
    nearest_reference_km,
    nearest_reference_km_naive,
)


def test_known_distance_london_paris():
    # Reference value ~343.9 km (city-centre coordinates)
    d = haversine_km(51.5074, -0.1278, 48.8575, 2.3514)
    assert d == pytest.approx(343.9, abs=1.0)


def test_zero_distance():
    assert haversine_km(60.17, 24.94, 60.17, 24.94) == pytest.approx(0.0, abs=1e-9)


def test_antimeridian_wraparound():
    # Points at lon +179.9 and -179.9 are ~22 km apart at the equator,
    # not ~40,000 km. Haversine must handle the wrap.
    d = haversine_km(0.0, 179.9, 0.0, -179.9)
    assert d < 30


def test_nearest_picks_the_closer_reference():
    # Query in Helsinki; references in Espoo (~16 km) and Stockholm (~400 km)
    d = nearest_reference_km(
        [60.17], [24.94],
        [60.21, 59.33], [24.66, 18.07],
    )
    assert d.shape == (1,)
    assert 10 < d[0] < 25


def test_chunked_matches_naive_oracle():
    rng = np.random.default_rng(42)
    qlat = rng.uniform(-90, 90, 40)
    qlon = rng.uniform(-180, 180, 40)
    rlat = rng.uniform(-90, 90, 60)
    rlon = rng.uniform(-180, 180, 60)
    fast = nearest_reference_km(qlat, qlon, rlat, rlon, chunk_size=7)
    slow = nearest_reference_km_naive(qlat, qlon, rlat, rlon)
    np.testing.assert_allclose(fast, slow, rtol=1e-12)


def test_chunk_size_does_not_change_result():
    rng = np.random.default_rng(0)
    qlat = rng.uniform(-60, 60, 25)
    qlon = rng.uniform(-180, 180, 25)
    rlat = rng.uniform(-60, 60, 30)
    rlon = rng.uniform(-180, 180, 30)
    a = nearest_reference_km(qlat, qlon, rlat, rlon, chunk_size=1)
    b = nearest_reference_km(qlat, qlon, rlat, rlon, chunk_size=1000)
    np.testing.assert_allclose(a, b)


def test_empty_reference_raises():
    with pytest.raises(ValueError, match="empty"):
        nearest_reference_km([60.0], [24.0], [], [])


def test_nan_coordinates_raise_with_count():
    with pytest.raises(ValueError, match="non-finite"):
        nearest_reference_km([60.0, np.nan], [24.0, 25.0], [61.0], [24.0])


def test_swapped_latlon_raises():
    # A longitude passed as latitude (e.g. 139.7 for Tokyo) must fail loudly.
    with pytest.raises(ValueError, match="swapped"):
        nearest_reference_km([139.7], [35.7], [61.0], [24.0])


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="different shapes"):
        nearest_reference_km([60.0, 61.0], [24.0], [61.0], [24.0])