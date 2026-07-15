"""Cross-reference qizheng calculations against an external open-source project.

The reference implementation lives at:
    https://github.com/xiadazhuang/qizheng-tool

It is cloned on demand into ``research/qizheng-ref/``.  These tests skip
automatically when the reference is unavailable.

The reference uses a different mansion tradition (simplified 28-mansion table
starting from 角宿) and a different 紫气 algorithm (授时历-based).  We therefore
only assert equality on the parts that should agree: the seven governors and
three of the four remainders (罗睺/计都/月孛), all of which are derived directly
from pyswisseph.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REF_DIR = Path("research/qizheng-ref/src")
DATA_PATH = Path("tools/qizheng/benchmark_data/celebrity_charts.jsonl")

pytestmark = [
    pytest.mark.skipif(not REF_DIR.exists(), reason="reference project not cloned"),
]


@pytest.fixture
def ref_modules():
    import sys

    path = str(REF_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    from four_remnants import (
        calculate_jitu,
        calculate_luohou,
        calculate_yuebo,
        calculate_ziqi,
    )
    from seven_planets import calculate_seven_planets

    return {
        "calculate_seven_planets": calculate_seven_planets,
        "calculate_luohou": calculate_luohou,
        "calculate_jitu": calculate_jitu,
        "calculate_yuebo": calculate_yuebo,
        "calculate_ziqi": calculate_ziqi,
    }


def _load_cases():
    cases = []
    if not DATA_PATH.exists():
        return cases
    with DATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


CASES = _load_cases()


@pytest.fixture
def sample_jd():
    import swisseph as swe

    return swe.julday(1990, 5, 15, 0.0)


def test_seven_governors_match_reference(ref_modules, sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    mapping = {
        "sun": "太阳",
        "moon": "太阴",
        "mercury": "水星",
        "venus": "金星",
        "mars": "火星",
        "jupiter": "木星",
        "saturn": "土星",
    }
    ref_planets = ref_modules["calculate_seven_planets"](sample_jd)
    for ref_name, body in mapping.items():
        lon, _ = _compute_body_longitude(sample_jd, body)
        assert abs(lon - ref_planets[ref_name]) < 1e-4


def test_luohou_jitu_yuebo_match_reference(ref_modules, sample_jd):
    from tools.qizheng.astronomy import _compute_body_longitude

    lon_rahu, _ = _compute_body_longitude(sample_jd, "罗睺")
    lon_ketu, _ = _compute_body_longitude(sample_jd, "计都")
    lon_yuebo, _ = _compute_body_longitude(sample_jd, "月孛")

    assert abs(lon_rahu - ref_modules["calculate_luohou"](sample_jd)) < 1e-4
    assert abs(lon_ketu - ref_modules["calculate_jitu"](sample_jd)) < 1e-4
    assert abs(lon_yuebo - ref_modules["calculate_yuebo"](sample_jd)) < 1e-4


def test_mansion_differences_are_documented(ref_modules, sample_jd):
    """Different projects use different 28-mansion tables; record the diff."""
    from tools.qizheng.astronomy import _compute_body_longitude
    from tools.qizheng.star_tables import mansion_for_degree

    ref_planets = ref_modules["calculate_seven_planets"](sample_jd)
    differences = []
    for ref_name, body in {
        "sun": "太阳",
        "moon": "太阴",
        "mercury": "水星",
        "venus": "金星",
        "mars": "火星",
        "jupiter": "木星",
        "saturn": "土星",
    }.items():
        lon, _ = _compute_body_longitude(sample_jd, body)
        our_mansion = mansion_for_degree(lon)
        from mansions import map_to_mansion

        ref_mansion, _ = map_to_mansion(ref_planets[ref_name])
        if our_mansion != ref_mansion:
            differences.append((body, our_mansion, ref_mansion))

    # We expect differences because the reference uses a simplified mansion table.
    assert differences
    for body, our_mansion, ref_mansion in differences:
        assert isinstance(our_mansion, str)
        assert isinstance(ref_mansion, str)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_seven_governors_match_reference_with_timezone(ref_modules, case):
    """参考项目无时区处理；传入 UTC 时间后七政黄经应完全一致。"""
    import swisseph as swe

    from tools.qizheng.astronomy import _compute_body_longitude

    dt = datetime.fromisoformat(case["birth_datetime"])
    offset = timedelta(hours=case["timezone_offset"])
    dt_utc = (dt.replace(tzinfo=timezone(offset)) - offset).replace(tzinfo=None)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                    dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)

    mapping = {
        "sun": "太阳",
        "moon": "太阴",
        "mercury": "水星",
        "venus": "金星",
        "mars": "火星",
        "jupiter": "木星",
        "saturn": "土星",
    }
    ref_planets = ref_modules["calculate_seven_planets"](jd)
    for ref_name, body in mapping.items():
        lon, _ = _compute_body_longitude(jd, body)
        assert abs(lon - ref_planets[ref_name]) < 1e-4


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_luohou_jitu_yuebo_match_reference_with_timezone(ref_modules, case):
    """参考项目无时区处理；传入 UTC 时间后罗计孛黄经应完全一致。"""
    import swisseph as swe

    from tools.qizheng.astronomy import _compute_body_longitude

    dt = datetime.fromisoformat(case["birth_datetime"])
    offset = timedelta(hours=case["timezone_offset"])
    dt_utc = (dt.replace(tzinfo=timezone(offset)) - offset).replace(tzinfo=None)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                    dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)

    lon_rahu, _ = _compute_body_longitude(jd, "罗睺")
    lon_ketu, _ = _compute_body_longitude(jd, "计都")
    lon_yuebo, _ = _compute_body_longitude(jd, "月孛")

    assert abs(lon_rahu - ref_modules["calculate_luohou"](jd)) < 1e-4
    assert abs(lon_ketu - ref_modules["calculate_jitu"](jd)) < 1e-4
    assert abs(lon_yuebo - ref_modules["calculate_yuebo"](jd)) < 1e-4


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_mansion_differences_and_ziqi_match(ref_modules, case):
    """二十八宿因宿表不同仍有差异；紫气已对齐参考项目。"""
    import swisseph as swe

    from tools.qizheng.astronomy import _compute_body_longitude
    from tools.qizheng.star_tables import mansion_for_degree

    dt = datetime.fromisoformat(case["birth_datetime"])
    offset = timedelta(hours=case["timezone_offset"])
    dt_utc = (dt.replace(tzinfo=timezone(offset)) - offset).replace(tzinfo=None)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                    dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)

    mapping = {
        "sun": "太阳",
        "moon": "太阴",
        "mercury": "水星",
        "venus": "金星",
        "mars": "火星",
        "jupiter": "木星",
        "saturn": "土星",
    }
    ref_planets = ref_modules["calculate_seven_planets"](jd)

    mansion_diffs = []
    for ref_name, body in mapping.items():
        lon, _ = _compute_body_longitude(jd, body)
        our_mansion = mansion_for_degree(lon)
        from mansions import map_to_mansion

        ref_mansion, _ = map_to_mansion(ref_planets[ref_name])
        if our_mansion != ref_mansion:
            mansion_diffs.append((body, our_mansion, ref_mansion))

    # 参考用简化宿表，必然存在差异。
    assert mansion_diffs

    # 紫气现在使用与参考项目一致的授时历算法。
    lon_ziqi, _ = _compute_body_longitude(jd, "紫气")
    ref_ziqi = ref_modules["calculate_ziqi"](jd)
    ziqi_diff = abs((lon_ziqi - ref_ziqi + 180) % 360 - 180)
    assert ziqi_diff < 1e-4
