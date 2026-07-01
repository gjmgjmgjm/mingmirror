"""Tests for tools/bazi_ai/bazi_validator.py."""

import pytest

from tools.bazi_ai.bazi_validator import (
    extract_pillars,
    is_valid_pillar,
    month_branch,
    normalize_bazi,
    validate_bazi,
)


class TestIsValidPillar:
    @pytest.mark.parametrize("pillar, expected", [
        ("甲子", True),
        ("癸亥", True),
        ("甲寅", True),
        ("甲卯", False),
        ("丁寅", False),
        ("XX", False),
        ("", False),
    ])
    def test_is_valid_pillar(self, pillar, expected):
        assert is_valid_pillar(pillar) == expected


class TestNormalizeBazi:
    @pytest.mark.parametrize("raw, expected", [
        ("乙卯 戊寅 庚子 丙子", "乙卯 戊寅 庚子 丙子"),
        ("乙卯戊寅庚子丙子", "乙卯 戊寅 庚子 丙子"),
        ("我的八字是乙卯戊寅庚子丙子", "乙卯 戊寅 庚子 丙子"),
        ("甲子 丙寅 戊辰 庚午", "甲子 丙寅 戊辰 庚午"),
    ])
    def test_normalize_valid(self, raw, expected):
        assert normalize_bazi(raw) == expected

    @pytest.mark.parametrize("raw", [
        "",
        None,
        "不是八字",
        "甲卯 丁丑 辛卯 辛卯",  # invalid pillar 甲卯
        "丁寅 辛亥 己丑 丙寅",  # invalid pillar 丁寅
    ])
    def test_normalize_invalid(self, raw):
        assert normalize_bazi(raw) is None


class TestValidateBazi:
    def test_validate_valid(self):
        assert validate_bazi("甲子 丙寅 戊辰 庚午") is True

    def test_validate_invalid(self):
        assert validate_bazi("甲卯 丁丑 辛卯 辛卯") is False


class TestExtractPillars:
    def test_extract_pillars(self):
        assert extract_pillars("乙卯 戊寅 庚子 丙子") == ["乙卯", "戊寅", "庚子", "丙子"]

    def test_extract_pillars_invalid(self):
        with pytest.raises(ValueError):
            extract_pillars("甲卯 丁丑 辛卯 辛卯")


class TestDayMasterAndMonthBranch:
    def test_month_branch(self):
        assert month_branch("乙卯 戊寅 庚子 丙子") == "寅"

    def test_month_branch_invalid(self):
        assert month_branch("甲卯 丁丑 辛卯 辛卯") is None
