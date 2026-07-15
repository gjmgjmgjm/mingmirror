"""Validation of qizheng astronomy against raw pyswisseph values.

These tests ensure that our wrappers around Swiss Ephemeris do not introduce
rounding or sign errors when computing Julian Days, house cusps, ascendant/MC,
and planetary longitudes.
"""

from datetime import datetime, timezone

import pytest

try:
    import swisseph as swe

    _SWISSEPH_AVAILABLE = True
except Exception:  # pragma: no cover
    _SWISSEPH_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _SWISSEPH_AVAILABLE, reason="pyswisseph is not installed"
)


@pytest.fixture
def sample_jd():
    """JD for 1990-05-15 00:00 UTC."""
    return swe.julday(1990, 5, 15, 0.0)


@pytest.fixture
def beijing_1990():
    return datetime(1990, 5, 15, 8, 0), 39.9042, 116.4074, 8.0


def test_julian_day_ut_matches_pyswisseph():
    from tools.qizheng.astronomy import julian_day_ut

    dt = datetime(1990, 5, 15, 0, 0, tzinfo=timezone.utc)
    expected = swe.julday(1990, 5, 15, 0.0)
    assert abs(julian_day_ut(dt) - expected) < 1e-6


def test_compute_asc_mc_matches_pyswisseph(beijing_1990):
    from tools.qizheng.astronomy import _to_utc, compute_asc_mc, julian_day_ut

    dt, lat, lon, tz = beijing_1990
    jd = julian_day_ut(_to_utc(dt, tz))
    asc, mc = compute_asc_mc(jd, lat, lon)

    _, ascmc = swe.houses(jd, lat, lon, b"P")
    expected_asc = ascmc[0] % 360.0
    expected_mc = ascmc[1] % 360.0

    assert abs(asc - expected_asc) < 1e-3
    assert abs(mc - expected_mc) < 1e-3


def test_compute_houses_matches_pyswisseph(beijing_1990):
    from tools.qizheng.astronomy import _to_utc, compute_houses, julian_day_ut

    dt, lat, lon, tz = beijing_1990
    jd = julian_day_ut(_to_utc(dt, tz))
    houses = compute_houses(jd, lat, lon)

    cusps, _ = swe.houses(jd, lat, lon, b"P")
    # swe.houses returns either 12 cusps directly, or 13+ values where
    # index 0 is unused and indices 1..12 hold the actual cusps.
    if len(cusps) >= 13:
        expected = [float(cusps[i]) % 360.0 for i in range(1, 13)]
    else:
        expected = [float(v) % 360.0 for v in cusps[:12]]

    assert len(houses) == 12
    for actual, exp in zip(houses, expected):
        assert abs(actual - exp) < 1e-3


@pytest.mark.parametrize(
    "body,swe_body",
    [
        ("太阳", swe.SUN),
        ("太阴", swe.MOON),
        ("水星", swe.MERCURY),
        ("金星", swe.VENUS),
        ("火星", swe.MARS),
        ("木星", swe.JUPITER),
        ("土星", swe.SATURN),
    ],
)
def test_seven_governor_longitudes_match_pyswisseph(body, swe_body, sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    lon, _ = _compute_body_longitude(sample_jd, body)
    expected = swe.calc_ut(sample_jd, swe_body)[0][0]

    assert abs(lon - expected) < 1e-4


def test_rahu_longitude_matches_true_node(sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    lon, _ = _compute_body_longitude(sample_jd, "罗睺")
    expected = swe.calc_ut(sample_jd, swe.TRUE_NODE)[0][0]
    assert abs(lon - expected) < 1e-4


def test_ketu_is_opposite_rahu(sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    rahu, _ = _compute_body_longitude(sample_jd, "罗睺")
    ketu, _ = _compute_body_longitude(sample_jd, "计都")
    diff = (ketu - rahu) % 360.0
    angular = diff if diff <= 180.0 else 360.0 - diff
    assert abs(angular - 180.0) < 1e-4


def test_lunar_apogee_matches_pyswisseph(sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    lon, _ = _compute_body_longitude(sample_jd, "月孛")
    expected = swe.calc_ut(sample_jd, swe.MEAN_APOG)[0][0]
    assert abs(lon - expected) < 1e-4


def test_timezone_offset_equivalence():
    """同一 UTC 时刻用不同时区表示，天文结果应完全一致。"""
    from tools.qizheng.astronomy import astro_profile

    # 1990-05-15 00:00 UTC = 1990-05-15 08:00 东八区 = 1990-05-14 19:00 西五区
    base_utc = datetime(1990, 5, 15, 0, 0, tzinfo=timezone.utc)
    beijing = datetime(1990, 5, 15, 8, 0)
    new_york = datetime(1990, 5, 14, 19, 0)

    profile_utc = astro_profile(base_utc, 39.9042, 116.4074, 0.0)
    profile_bj = astro_profile(beijing, 39.9042, 116.4074, 8.0)
    profile_ny = astro_profile(new_york, 39.9042, 116.4074, -5.0)

    for key in ("ascendant", "midheaven", "julian_day_ut"):
        assert abs(profile_utc[key] - profile_bj[key]) < 1e-6
        assert abs(profile_utc[key] - profile_ny[key]) < 1e-6

    for body in profile_utc["bodies"]:
        assert (
            abs(profile_utc["bodies"][body]["longitude"] - profile_bj["bodies"][body]["longitude"])
            < 1e-4
        )
        assert (
            abs(profile_utc["bodies"][body]["longitude"] - profile_ny["bodies"][body]["longitude"])
            < 1e-4
        )

    for h_utc, h_bj, h_ny in zip(profile_utc["houses"], profile_bj["houses"], profile_ny["houses"]):
        assert abs(h_utc["cusp"] - h_bj["cusp"]) < 1e-4
        assert abs(h_utc["cusp"] - h_ny["cusp"]) < 1e-4
