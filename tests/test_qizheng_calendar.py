"""Tests for Qi Zheng Si Yu structural calendar calculations."""

import pytest

from tools.qizheng.calendar import (
    body_lord,
    body_palace,
    dayun_list,
    five_element_pattern,
    life_palace,
    liunian_list,
    nayin,
    start_age_from_pattern,
    structural_profile,
    twelve_palaces,
    yearly_relations,
)


@pytest.mark.parametrize(
    "month_branch, hour_branch, expected",
    [
        ("寅", "子", "寅"),   # 正月子时，命宫寅
        ("寅", "丑", "丑"),   # 正月丑时，命宫丑
        ("午", "午", "子"),   # 五月午时
        ("未", "申", "亥"),   # 癸未八字：未月申时
    ],
)
def test_life_palace(month_branch, hour_branch, expected):
    assert life_palace(month_branch, hour_branch) == expected


@pytest.mark.parametrize(
    "month_branch, hour_branch, expected",
    [
        ("寅", "子", "寅"),
        ("寅", "丑", "卯"),
        ("午", "午", "子"),
        ("未", "申", "卯"),
    ],
)
def test_body_palace(month_branch, hour_branch, expected):
    assert body_palace(month_branch, hour_branch) == expected


@pytest.mark.parametrize(
    "year_branch, expected",
    [
        ("子", "火星"),
        ("午", "太阳"),
        ("卯", "太阴"),
        ("未", "水星"),
    ],
)
def test_body_lord(year_branch, expected):
    assert body_lord(year_branch) == expected


@pytest.mark.parametrize(
    "year_pillar, expected",
    [
        ("癸未", "杨柳木"),
        ("甲子", "海中金"),
        ("丙寅", "炉中火"),
    ],
)
def test_nayin(year_pillar, expected):
    assert nayin(year_pillar) == expected


@pytest.mark.parametrize(
    "year_pillar, expected",
    [
        ("癸未", "木"),
        ("甲子", "金"),
        ("丙寅", "火"),
    ],
)
def test_five_element_pattern(year_pillar, expected):
    assert five_element_pattern(year_pillar) == expected


def test_twelve_palaces():
    palaces = twelve_palaces("子")
    assert palaces["命宫"] == "子"
    assert palaces["财帛"] == "亥"
    assert palaces["夫妻"] == "午"


def test_structural_profile():
    chart = "癸未 己未 甲申 壬申"
    profile = structural_profile(chart)
    assert profile is not None
    assert profile["day_master"] == "甲"
    assert profile["life_palace"] == "亥"
    assert profile["body_palace"] == "卯"
    assert profile["body_lord"] == "水星"
    assert profile["five_element_pattern"] == "木"
    assert profile["twelve_palaces"]["命宫"] == "亥"


def test_structural_profile_invalid():
    assert structural_profile("不是八字") is None


@pytest.mark.parametrize(
    "element,expected",
    [
        ("水", 2),
        ("木", 3),
        ("金", 4),
        ("土", 5),
        ("火", 6),
        ("未知", 3),
    ],
)
def test_start_age_from_pattern(element, expected):
    assert start_age_from_pattern(element) == expected


def test_dayun_list_forward():
    # 甲子年 男命 -> 阳男，顺行
    chart = "甲子 丙寅 戊辰 庚午"
    dayun = dayun_list(chart, "male", until_age=40)
    assert len(dayun) >= 3
    assert dayun[0]["palace"] == "命宫"
    assert dayun[0]["start_age"] == 4  # 金四局
    assert dayun[1]["palace"] == "财帛"


def test_dayun_list_backward():
    # 甲子年 女命 -> 阳女，逆行
    chart = "甲子 丙寅 戊辰 庚午"
    dayun = dayun_list(chart, "female", until_age=40)
    assert dayun[0]["palace"] == "命宫"
    # 逆行时第二宫应为相貌
    assert dayun[1]["palace"] == "相貌"


def test_dayun_list_invalid_chart():
    assert dayun_list("不是八字", "male") == []


def test_liunian_list():
    liunian = liunian_list(2024, 2026)
    assert len(liunian) == 3
    assert liunian[0]["year"] == 2024
    assert liunian[0]["pillar"] == "甲辰"


def test_yearly_relations():
    chart = "甲子 丙寅 戊辰 庚午"
    rel = yearly_relations(chart, "子", "甲辰")
    assert rel is not None
    assert rel["dayun_pillar"] == "子"
    assert rel["liunian_pillar"] == "甲辰"
    assert rel["dayun_branch"] == "子"
    assert rel["liunian_branch"] == "辰"
