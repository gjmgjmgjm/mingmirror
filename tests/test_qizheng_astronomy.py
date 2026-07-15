"""Tests for Qi Zheng Si Yu astronomical calculations.

These tests require ``pyswisseph`` (listed in ``requirements-qizheng.txt``).
They are skipped automatically when the optional dependency is missing.
"""

from datetime import datetime

import pytest

try:
    import swisseph  # noqa: F401

    _SWISSEPH_AVAILABLE = True
except Exception:  # pragma: no cover
    _SWISSEPH_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _SWISSEPH_AVAILABLE, reason="pyswisseph is not installed"
)


@pytest.fixture
def beijing_1990_05_15():
    """1990-05-15 08:00 in Beijing (UTC+8)."""
    return datetime(1990, 5, 15, 8, 0), 39.9042, 116.4074, 8.0


def test_astro_profile_structure(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)

    assert "birth_datetime_local" in profile
    assert "birth_datetime_utc" in profile
    assert profile["location"] == {"latitude": lat, "longitude": lon}
    assert isinstance(profile["julian_day_ut"], float)
    assert "ascendant" in profile
    assert "midheaven" in profile
    assert len(profile["houses"]) == 12
    assert set(profile["bodies"].keys()) == {
        "太阳",
        "太阴",
        "木星",
        "火星",
        "土星",
        "金星",
        "水星",
        "罗睺",
        "计都",
        "月孛",
        "紫气",
    }


def test_ascendant_and_midheaven(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)

    # Around 1990-05-15 08:00 Beijing the ascendant should be in Cancer
    # and the midheaven in Pisces for this location.
    assert 85.0 <= profile["ascendant"] <= 115.0
    assert profile["ascendant_zodiac"] == "巨蟹"
    assert profile["ascendant_mansion"] == "鬼"

    assert 330.0 <= profile["midheaven"] <= 360.0
    assert profile["midheaven_zodiac"] == "双鱼"


def test_body_positions(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)
    bodies = profile["bodies"]

    # Sun in Taurus around 54° on this date.
    sun = bodies["太阳"]
    assert 45.0 <= sun["longitude"] <= 65.0
    assert sun["zodiac"] == "金牛"
    assert sun["element"] == "火"
    assert sun["speed_state"] == "顺行"

    # Moon in Capricorn around 291°.
    moon = bodies["太阴"]
    assert 280.0 <= moon["longitude"] <= 305.0
    assert moon["zodiac"] == "摩羯"
    assert moon["mansion"] == "女"

    # 罗睺 and 计都 are always 180° apart.
    rahu = bodies["罗睺"]["longitude"]
    ketu = bodies["计都"]["longitude"]
    diff = (rahu - ketu) % 360.0
    angular_gap = diff if diff <= 180.0 else 360.0 - diff
    assert abs(angular_gap - 180.0) < 0.1


def test_house_info(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)

    houses = profile["houses"]
    assert houses[0]["palace"] == "命宫"
    assert houses[0]["index"] == 1
    # 此盘上升在巨蟹，命宫对应未，未宫主星为太阴。
    assert houses[0]["lord"] == "太阴"
    for key in ("index", "cusp", "zodiac", "mansion", "palace", "lord"):
        assert key in houses[0]


def test_mansion_mapping():
    from tools.qizheng.star_tables import mansion_for_degree

    # Boundaries are based on the Zheng'an ancient mansion table.
    assert mansion_for_degree(0.0) == "娄"
    assert mansion_for_degree(10.0) == "娄"
    assert mansion_for_degree(15.0) == "胃"
    assert mansion_for_degree(358.44) == "娄"
    assert mansion_for_degree(359.99) == "娄"
    assert mansion_for_degree(360.0) == "娄"


def test_mansion_mapping_with_precession():
    from tools.qizheng.star_tables import mansion_for_degree

    # With a 30° ayanamsha offset, 30° tropical maps to 0° sidereal -> 娄宿.
    assert mansion_for_degree(30.0, precession_offset=30.0) == "娄"
    # 15° tropical with 30° offset -> 345° sidereal -> 壁宿.
    assert mansion_for_degree(15.0, precession_offset=30.0) == "壁"
    # 45° tropical with 30° offset -> 15° sidereal -> 胃宿.
    assert mansion_for_degree(45.0, precession_offset=30.0) == "胃"


def test_dignity():
    from tools.qizheng.star_tables import MIAO_WANG_YANG, body_dignity

    # 默认表（单地支庙旺）
    assert body_dignity("太阳", "戌") == "庙"
    assert body_dignity("太阳", "午") == "旺"
    assert body_dignity("太阳", "辰") == "陷"
    assert body_dignity("太阳", "寅") == "得地"
    assert body_dignity("太阳", "子") == "平"

    # 杨国正派表（多地支庙旺，含「乐」）
    assert body_dignity("太阳", "午", MIAO_WANG_YANG) == "庙"
    assert body_dignity("太阳", "巳", MIAO_WANG_YANG) == "旺"
    assert body_dignity("太阳", "辰", MIAO_WANG_YANG) == "乐"
    assert body_dignity("太阴", "戌", MIAO_WANG_YANG) == "庙"
    assert body_dignity("木星", "亥", MIAO_WANG_YANG) == "庙"
    assert body_dignity("土星", "丑", MIAO_WANG_YANG) == "庙"


def test_rulership_and_exaltation():
    from tools.qizheng.star_tables import body_exaltation, body_rulership, body_strength

    # 入垣
    assert body_rulership("太阳", "午") == "入垣"
    assert body_rulership("太阳", "子") == "不入垣"
    assert body_rulership("水星", "巳") == "入垣"
    assert body_rulership("土星", "丑") == "入垣"

    # 升殿
    assert body_exaltation("太阳", "星") == "升殿"
    assert body_exaltation("太阴", "心") == "升殿"
    assert body_exaltation("木星", "角") == "升殿"

    # 综合强弱
    assert body_strength("太阳", "戌", "娄") == "庙"
    assert body_strength("太阳", "子", "星") == "升殿"  # 平+升殿
    assert body_strength("太阳", "午", "星") == "旺"  # 旺优先于升殿
    assert body_strength("太阳", "子", "娄") == "平"  # 平+不入垣+不升殿


def test_aspects_and_patterns(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.patterns import compute_aspects, detect_patterns

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)
    positions = {name: info["longitude"] for name, info in profile["bodies"].items()}
    houses = {name: info["house"] for name, info in profile["bodies"].items()}

    aspects = compute_aspects(positions)
    assert isinstance(aspects, list)
    if aspects:
        aspect = aspects[0]
        assert set(aspect.keys()) == {"bodies", "aspect", "angle", "orb", "auspicious"}

    patterns = detect_patterns(houses, positions)
    names = {p["name"] for p in patterns}
    # 太阳 and 太阴 form a trine for this chart.
    assert "日月拱照" in names


def test_enhanced_patterns(beijing_1990_05_15):
    """验证新增格局检测可用，且返回的格局名均在目录中。"""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.patterns import detect_patterns
    from tools.qizheng.star_tables import PATTERN_CATALOG

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_profile(dt, lat, lon, tz)
    positions = {name: info["longitude"] for name, info in profile["bodies"].items()}
    houses = {name: info["house"] for name, info in profile["bodies"].items()}
    strengths = {name: info["strength"] for name, info in profile["bodies"].items()}

    from tools.qizheng.star_tables import ZODIAC_TO_BRANCH, twelve_palaces
    asc_branch = ZODIAC_TO_BRANCH[profile["ascendant_zodiac"]]
    palace_branches = twelve_palaces(asc_branch)

    patterns = detect_patterns(
        houses,
        positions,
        body_strengths=strengths,
        palace_branches=palace_branches,
    )
    names = {p["name"] for p in patterns}
    assert all(p["name"] in PATTERN_CATALOG for p in patterns)
    # 该盘日月三合，应触发日月拱照；紫气入命/官禄则可能触发紫气朝垣。
    assert "日月拱照" in names


def test_astro_profile_precession_modes(beijing_1990_05_15):
    from tools.qizheng.astronomy import astro_profile

    dt, lat, lon, tz = beijing_1990_05_15
    tropical = astro_profile(dt, lat, lon, tz, precession_mode="tropical")
    sidereal = astro_profile(dt, lat, lon, tz, precession_mode="sidereal_lahiri")

    assert tropical["precession_mode"] == "tropical"
    assert tropical["precession_offset_degrees"] == 0.0
    assert sidereal["precession_mode"] == "sidereal_lahiri"
    assert sidereal["precession_offset_degrees"] > 20.0

    # Tropical and sidereal mansions should differ for this chart.
    assert tropical["bodies"]["太阳"]["mansion"] != sidereal["bodies"]["太阳"]["mansion"]


def test_astro_structural_profile_merges_chart_and_astro(beijing_1990_05_15):
    from tools.qizheng.calendar import astro_structural_profile

    dt, lat, lon, tz = beijing_1990_05_15
    profile = astro_structural_profile(
        birth_datetime=dt,
        latitude=lat,
        longitude=lon,
        timezone_offset_hours=tz,
        precession_mode="sidereal_lahiri",
    )

    assert profile is not None
    assert "chart" in profile
    assert "astro" in profile
    assert "aspects" in profile
    assert "patterns" in profile
    assert profile["day_master"] == "庚"
    assert profile["astro"]["precession_mode"] == "sidereal_lahiri"


def test_astro_structural_profile_chart_only():
    from tools.qizheng.calendar import astro_structural_profile

    profile = astro_structural_profile(chart="甲子 丙寅 戊辰 庚午")
    assert profile is not None
    assert profile["chart"] == "甲子 丙寅 戊辰 庚午"
    assert profile["day_master"] == "戊"
    # No datetime/location, so astro data is absent.
    assert "astro" not in profile


def test_astro_structural_profile_invalid():
    from tools.qizheng.calendar import astro_structural_profile

    assert astro_structural_profile() is None
    assert astro_structural_profile(chart="不是八字") is None
