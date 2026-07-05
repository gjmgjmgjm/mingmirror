"""Tests for tools/bazi_ai/calendar.py."""

from datetime import date

from tools.bazi_ai.calendar import (
    daily_fortune,
    day_pillar,
    dayun_list,
    liunian_list,
    month_pillar,
    year_pillar,
)


def test_day_pillar_cycles_every_60_days():
    d1 = date(2024, 1, 1)
    d2 = date(2024, 3, 1)
    assert d2.toordinal() - d1.toordinal() == 60
    assert day_pillar(d1) == day_pillar(d2)


def test_year_pillar_approximation():
    # 2024 begins on Feb 4 (Li Chun approximation); before that it is still 2023.
    assert year_pillar(date(2024, 2, 3)) == "癸卯"
    assert year_pillar(date(2024, 2, 4)) == "甲辰"


def test_month_pillar_returns_valid_pillar():
    p = month_pillar(date(2024, 6, 15))
    assert len(p) == 2


def test_daily_fortune_structure():
    result = daily_fortune("甲子 丙寅 戊辰 庚午", date(2024, 6, 15))
    assert result["date"] == "2024-06-15"
    assert "today_pillars" in result
    assert "weather" in result
    assert "energy" in result
    assert "dos" in result
    assert "avoids" in result
    assert sum(result["energy"].values()) <= 100


def test_daily_fortune_rejects_invalid_bazi():
    result = daily_fortune("not a bazi")
    assert "error" in result


def test_dayun_list_structure_and_direction():
    # 1990-05-15, male, year stem 庚 (yang) -> forward from month pillar
    bazi = "庚午 辛巳 庚辰 丁丑"
    result = dayun_list(bazi, "male", "1990-05-15", until_age=30)
    assert len(result) > 0
    # 大运从月柱起排，第一步为月柱的下一步
    assert result[0]["pillar"] == "壬午"
    assert result[1]["pillar"] == "癸未"
    assert result[0]["start_age"] >= 0
    assert result[0]["end_age"] == result[0]["start_age"] + 10


def test_dayun_list_female_backward():
    # Same chart, female, yang year -> backward
    bazi = "庚午 辛巳 庚辰 丁丑"
    result = dayun_list(bazi, "female", "1990-05-15", until_age=30)
    assert result[0]["pillar"] == "庚辰"
    assert result[1]["pillar"] == "己卯"


def test_dayun_list_fallback_without_birth():
    bazi = "庚午 辛巳 庚辰 丁丑"
    result = dayun_list(bazi, "male", "", until_age=30)
    assert result[0]["start_age"] == 0
    # 无出生信息时默认顺行，第一步仍为月柱下一步
    assert result[0]["pillar"] == "壬午"


def test_liunian_list_structure():
    result = liunian_list(2024, 2026)
    assert len(result) == 3
    assert result[0]["year"] == 2024
    assert len(result[0]["pillar"]) == 2
    assert "stem" in result[0] and "branch" in result[0]
