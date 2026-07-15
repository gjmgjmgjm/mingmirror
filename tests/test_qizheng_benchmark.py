"""Benchmark/consistency tests for Qi Zheng Si Yu using celebrity charts.

The dataset lives in ``tools/qizheng/benchmark_data/celebrity_charts.jsonl``.
These tests verify that:

1. The datetime → bazi conversion matches the recorded expected bazi.
2. The astronomical profile can be computed for every entry.
3. The tropical and sidereal mansion mappings are internally consistent.
4. Patterns/aspects are produced in a stable shape.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from tools.qizheng.star_tables import MIAO_WANG, MIAO_WANG_YANG

try:
    import swisseph  # noqa: F401

    _SWISSEPH_AVAILABLE = True
except Exception:  # pragma: no cover
    _SWISSEPH_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _SWISSEPH_AVAILABLE, reason="pyswisseph is not installed"
)

DATA_PATH = Path("tools/qizheng/benchmark_data/celebrity_charts.jsonl")


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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_datetime_to_bazi_matches_expected(case):
    from tools.bazi_ai.calendar import pillars_for_datetime

    dt = datetime.fromisoformat(case["birth_datetime"])
    pillars = pillars_for_datetime(dt)
    chart = f"{pillars['year']} {pillars['month']} {pillars['day']} {pillars['hour']}"
    assert chart == case["expected_bazi"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_astro_profile_completeness(case):
    from tools.qizheng.astronomy import astro_profile

    dt = datetime.fromisoformat(case["birth_datetime"])
    profile = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
    )

    assert profile["location"]["latitude"] == case["latitude"]
    assert profile["location"]["longitude"] == case["longitude"]
    assert len(profile["bodies"]) == 11
    assert len(profile["houses"]) == 12
    assert profile["ascendant"] is not None
    assert profile["midheaven"] is not None


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_ascendant_life_palace_mapping(case):
    """上升点星座必须正确映射到命宫地支与宫主星。"""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.star_tables import PALACE_LORD, ZODIAC_TO_BRANCH

    dt = datetime.fromisoformat(case["birth_datetime"])
    profile = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
    )

    asc_zodiac = profile["ascendant_zodiac"]
    expected_branch = ZODIAC_TO_BRANCH[asc_zodiac]
    first_house = profile["houses"][0]
    assert first_house["palace"] == "命宫"
    assert first_house["lord"] == PALACE_LORD[expected_branch]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_sun_moon_dignity_valid(case):
    """太阳、太阴的庙旺落陷结果必须在合法集合内。"""
    from tools.qizheng.astronomy import astro_profile

    dt = datetime.fromisoformat(case["birth_datetime"])
    profile = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
    )

    for body in ("太阳", "太阴"):
        dignity = profile["bodies"][body]["dignity"]
        assert dignity in {"庙", "旺", "乐", "陷", "得地", "平"}


def _collect_dignity_rows(dignity_table=None):
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.star_tables import ZODIAC_TO_BRANCH

    rows = []
    for case in CASES:
        dt = datetime.fromisoformat(case["birth_datetime"])
        profile = astro_profile(
            dt,
            case["latitude"],
            case["longitude"],
            case["timezone_offset"],
            dignity_table=dignity_table,
        )
        bodies = profile["bodies"]
        houses = profile["houses"]
        asc_branch = ZODIAC_TO_BRANCH[profile["ascendant_zodiac"]]
        rows.append(
            {
                "name": case["name"],
                "ascendant_zodiac": profile["ascendant_zodiac"],
                "life_palace_branch": asc_branch,
                "life_palace_lord": houses[0]["lord"],
                "sun_dignity": bodies["太阳"]["dignity"],
                "sun_house": bodies["太阳"]["house"],
                "moon_dignity": bodies["太阴"]["dignity"],
                "moon_house": bodies["太阴"]["house"],
            }
        )
    return rows


def test_celebrity_dignity_summary():
    """汇总 50 例名人盘的太阳/太阴庙旺分布，供人工准确率审查。"""
    from tools.qizheng.star_tables import MIAO_WANG_YANG

    default_rows = _collect_dignity_rows()
    yang_rows = _collect_dignity_rows(dignity_table=MIAO_WANG_YANG)

    def _counts(rows):
        return Counter(r["sun_dignity"] for r in rows), Counter(r["moon_dignity"] for r in rows)

    default_sun, default_moon = _counts(default_rows)
    yang_sun, yang_moon = _counts(yang_rows)

    print("\n【Celebrity50 七政庙旺统计】")
    print("默认表:")
    print(f"  太阳 dignity 分布: {dict(default_sun)}")
    print(f"  太阴 dignity 分布: {dict(default_moon)}")
    print("杨国正派:")
    print(f"  太阳 dignity 分布: {dict(yang_sun)}")
    print(f"  太阴 dignity 分布: {dict(yang_moon)}")
    print("\n太阳/太阴详细（默认 vs 杨国正）:\n")
    for d, y in zip(default_rows, yang_rows):
        marker = "*" if d["sun_dignity"] != y["sun_dignity"] or d["moon_dignity"] != y["moon_dignity"] else " "
        print(
            f"{marker} {d['name']:8s} 上升{d['ascendant_zodiac']:3s}(命{d['life_palace_branch']:3s}) "
            f"日[{d['sun_dignity']:3s}->{y['sun_dignity']:3s}@{d['sun_house']:2d}宫] "
            f"月[{d['moon_dignity']:3s}->{y['moon_dignity']:3s}@{d['moon_house']:2d}宫]"
        )

    # 至少要有庙旺和平的分布；不能全部相同（否则映射可能退化）。
    assert len(default_sun) >= 2
    assert len(default_moon) >= 2
    assert len(yang_sun) >= 2
    assert len(yang_moon) >= 2


def test_celebrity_strength_summary():
    """汇总 50 例名人盘的综合强弱（庙旺+入垣+升殿），评估默认表合理性。"""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.star_tables import RU_YUAN, SHENG_DIAN, ZODIAC_TO_BRANCH

    SEVEN = ["太阳", "太阴", "木星", "火星", "土星", "金星", "水星"]

    def _palace_branch(profile, house):
        from tools.qizheng.star_tables import PALACE_NAMES, twelve_palaces

        asc_branch = ZODIAC_TO_BRANCH[profile["ascendant_zodiac"]]
        palace_branches = twelve_palaces(asc_branch)
        return palace_branches[PALACE_NAMES[house - 1]]

    ru_yuan_count = 0
    sheng_dian_count = 0
    strong_count = 0
    strength_counts = Counter()
    for case in CASES:
        dt = datetime.fromisoformat(case["birth_datetime"])
        profile = astro_profile(dt, case["latitude"], case["longitude"], case["timezone_offset"])
        for body in SEVEN:
            info = profile["bodies"][body]
            branch = _palace_branch(profile, info["house"])
            strength_counts[info["strength"]] += 1
            if info["strength"] in ("庙", "旺", "乐"):
                strong_count += 1
                if branch in RU_YUAN[body]:
                    ru_yuan_count += 1
                if info["mansion"] in SHENG_DIAN[body]:
                    sheng_dian_count += 1

    print("\n【Celebrity50 综合强弱统计（默认表）】")
    print(f"综合强弱分布: {dict(strength_counts)}")
    print(f"强状态（庙/旺/乐）数: {strong_count}")
    if strong_count:
        print(f"强状态下入垣一致率: {ru_yuan_count}/{strong_count} = {ru_yuan_count/strong_count*100:.1f}%")
        print(f"强状态下升殿一致率: {sheng_dian_count}/{strong_count} = {sheng_dian_count/strong_count*100:.1f}%")

    # 默认表评估：入垣一致率应明显高于随机水平，证明默认表与传统宫主规则自洽。
    assert strong_count > 0
    assert ru_yuan_count / strong_count >= 0.5


def _evaluate_dignity_table(table, name):
    """Return quantitative metrics for a dignity table on Celebrity50."""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.star_tables import (
        ALL_BODIES,
        PALACE_NAMES,
        RU_YUAN,
        SHENG_DIAN,
        ZODIAC_TO_BRANCH,
        body_strength,
        twelve_palaces,
    )

    KEY_PALACES = {"命宫", "官禄", "财帛", "福德", "迁移"}

    total = 0
    strong_count = 0
    strong_ru_yuan = 0
    strong_sheng_dian = 0
    strong_in_key_palace = 0
    xian_count = 0
    strength_counts: Counter = Counter()
    key_palace_strong_count: Counter = Counter()

    for case in CASES:
        dt = datetime.fromisoformat(case["birth_datetime"])
        profile = astro_profile(
            dt,
            case["latitude"],
            case["longitude"],
            case["timezone_offset"],
            dignity_table=table,
        )
        asc_branch = ZODIAC_TO_BRANCH[profile["ascendant_zodiac"]]
        palace_branches = twelve_palaces(asc_branch)

        for body in ALL_BODIES:
            info = profile["bodies"][body]
            palace = PALACE_NAMES[(info["house"] - 1) % 12]
            branch = palace_branches[palace]
            mansion = info["mansion"]

            strength = body_strength(body, branch, mansion, dignity_table=table)
            strength_counts[strength] += 1
            total += 1

            if strength in ("庙", "旺", "乐", "入垣升殿"):
                strong_count += 1
                if branch in RU_YUAN.get(body, set()):
                    strong_ru_yuan += 1
                if mansion in SHENG_DIAN.get(body, set()):
                    strong_sheng_dian += 1
                if palace in KEY_PALACES:
                    strong_in_key_palace += 1
                    key_palace_strong_count[palace] += 1
            if strength == "陷":
                xian_count += 1

    def _rate(numerator, denominator):
        return numerator / denominator if denominator else 0.0

    metrics = {
        "name": name,
        "total": total,
        "strong": strong_count,
        "strong_rate": _rate(strong_count, total),
        "ru_yuan_rate": _rate(strong_ru_yuan, strong_count),
        "sheng_dian_rate": _rate(strong_sheng_dian, strong_count),
        "key_palace_rate": _rate(strong_in_key_palace, strong_count),
        "xian_rate": _rate(xian_count, total),
        "strength_counts": dict(strength_counts),
        "key_palace_strong": dict(key_palace_strong_count),
    }
    return metrics


def test_dignity_table_quantitative_comparison():
    """量化比较默认 dignity 表与杨国正派在 Celebrity50 上的表现。"""
    default_metrics = _evaluate_dignity_table(MIAO_WANG, "默认表")
    yang_metrics = _evaluate_dignity_table(MIAO_WANG_YANG, "杨国正派")

    print("\n【Celebrity50 dignity 表量化对比】")
    print(
        f"{'指标':<14} {'默认表':>12} {'杨国正派':>12}"
    )
    print("-" * 40)
    for key in ("strong_rate", "ru_yuan_rate", "sheng_dian_rate", "key_palace_rate", "xian_rate"):
        print(
            f"{key:<14} {default_metrics[key]*100:>11.1f}% {yang_metrics[key]*100:>11.1f}%"
        )
    print(f"\n默认表强弱分布: {default_metrics['strength_counts']}")
    print(f"杨国正派强弱分布: {yang_metrics['strength_counts']}")
    print(f"\n默认表关键宫强星: {default_metrics['key_palace_strong']}")
    print(f"杨国正派关键宫强星: {yang_metrics['key_palace_strong']}")

    # 自洽分：入垣/升殿一致率越高，且落陷率越低，越自洽。
    def score(m):
        return (
            m["ru_yuan_rate"] * 0.45
            + m["sheng_dian_rate"] * 0.25
            + m["key_palace_rate"] * 0.20
            - m["xian_rate"] * 0.10
        )

    default_score = score(default_metrics)
    yang_score = score(yang_metrics)
    winner = "默认表" if default_score > yang_score else "杨国正派"
    print(f"\n自洽得分：默认表 {default_score:.3f}，杨国正派 {yang_score:.3f}")
    print(f"结论：在 Celebrity50 上，{winner} 与传统宫主/宿度规则自洽性更高。")

    # 两张表都应产生非退化的分布。
    assert default_metrics["strong"] > 0
    assert yang_metrics["strong"] > 0
    assert len(default_metrics["strength_counts"]) >= 3
    assert len(yang_metrics["strength_counts"]) >= 3


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_precession_modes_differ(case):
    from tools.qizheng.astronomy import astro_profile

    dt = datetime.fromisoformat(case["birth_datetime"])
    tropical = astro_profile(
        dt, case["latitude"], case["longitude"], case["timezone_offset"], "tropical"
    )
    sidereal = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
        "sidereal_lahiri",
    )

    assert tropical["precession_offset_degrees"] == 0.0
    # Ayanamsha is historically variable; just ensure a non-trivial offset is applied.
    assert sidereal["precession_offset_degrees"] > 10.0
    # At least one body should shift mansion between the two modes.
    mansions_tropical = {n: i["mansion"] for n, i in tropical["bodies"].items()}
    mansions_sidereal = {n: i["mansion"] for n, i in sidereal["bodies"].items()}
    assert mansions_tropical != mansions_sidereal


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_structural_profile_with_astro(case):
    from tools.qizheng.calendar import astro_structural_profile

    dt = datetime.fromisoformat(case["birth_datetime"])
    profile = astro_structural_profile(
        birth_datetime=dt,
        latitude=case["latitude"],
        longitude=case["longitude"],
        timezone_offset_hours=case["timezone_offset"],
    )

    assert profile is not None
    assert profile["chart"] == case["expected_bazi"]
    assert profile.get("astro")
    assert profile.get("aspects")
    assert profile.get("patterns") is not None


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_aspects_stable_across_precession_modes(case):
    """Aspects are geometric and should not depend on precession mode."""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.patterns import compute_aspects

    dt = datetime.fromisoformat(case["birth_datetime"])
    tropical = astro_profile(
        dt, case["latitude"], case["longitude"], case["timezone_offset"], "tropical"
    )
    sidereal = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
        "sidereal_lahiri",
    )

    def _key(asp):
        return (
            tuple(sorted(asp["bodies"])),
            asp["aspect"],
            round(asp["angle"], 2),
        )

    tropical_aspects = compute_aspects(
        {n: i["longitude"] for n, i in tropical["bodies"].items()}
    )
    sidereal_aspects = compute_aspects(
        {n: i["longitude"] for n, i in sidereal["bodies"].items()}
    )

    assert sorted(_key(a) for a in tropical_aspects) == sorted(
        _key(a) for a in sidereal_aspects
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_patterns_stable_across_precession_modes(case):
    """Patterns are geometric/house-based and should not depend on precession mode."""
    from tools.qizheng.astronomy import astro_profile
    from tools.qizheng.patterns import detect_patterns

    dt = datetime.fromisoformat(case["birth_datetime"])
    tropical = astro_profile(
        dt, case["latitude"], case["longitude"], case["timezone_offset"], "tropical"
    )
    sidereal = astro_profile(
        dt,
        case["latitude"],
        case["longitude"],
        case["timezone_offset"],
        "sidereal_lahiri",
    )

    def _patterns(profile):
        positions = {n: i["longitude"] for n, i in profile["bodies"].items()}
        houses = {n: i["house"] for n, i in profile["bodies"].items()}
        return {p["name"] for p in detect_patterns(houses, positions)}

    assert _patterns(tropical) == _patterns(sidereal)


def test_benchmark_dataset_is_not_empty():
    assert CASES
    assert len(CASES) >= 50
