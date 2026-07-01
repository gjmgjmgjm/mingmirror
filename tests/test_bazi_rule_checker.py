"""Tests for tools/bazi_ai/rule_checker.py."""


from tools.bazi_ai.rule_checker import (
    check_analysis,
    check_day_master_strength,
    check_useful_gods,
)


class TestCheckDayMasterStrength:
    def test_strong_season_claimed_weak(self):
        # 甲木生于寅月，身强季节，若标身弱则报警
        warnings = check_day_master_strength("甲寅 丙寅 甲子 甲子", "身弱")
        assert any("甲" in w and "木" in w and "寅月" in w for w in warnings)

    def test_weak_season_claimed_strong(self):
        # 甲木生于申月，身弱季节，若标身强则报警
        warnings = check_day_master_strength("甲申 壬申 甲子 甲子", "身强")
        assert any("甲" in w and "木" in w and "申月" in w for w in warnings)

    def test_no_claim(self):
        assert check_day_master_strength("甲寅 丙寅 甲子 甲子", None) == []


class TestCheckUsefulGods:
    def test_useful_god_conquers_day(self):
        # 甲木日主，用神为庚金（克木），应报警
        warnings = check_useful_gods("甲寅 丙寅 甲子 甲子", ["庚"], ["丙"])
        assert any("用神" in w and "庚" in w for w in warnings)

    def test_taboo_same_as_day(self):
        # 忌神与日主同五行，应报警
        warnings = check_useful_gods("甲寅 丙寅 甲子 甲子", ["丙"], ["甲"])
        assert any("忌神" in w and "甲" in w for w in warnings)


class TestCheckAnalysis:
    def test_valid_result(self):
        result = {
            "basic_info": {
                "bazi": "甲寅 丙寅 甲子 甲子",
                "day_master_strength": "身强",
                "useful_gods": ["丙"],
                "taboo_gods": ["庚"],
            }
        }
        out, warnings = check_analysis(result)
        assert "rule_warnings" not in out
        assert warnings == []

    def test_invalid_result_adds_warnings(self):
        result = {
            "basic_info": {
                "bazi": "甲寅 丙寅 甲子 甲子",
                "day_master_strength": "身弱",
                "useful_gods": ["庚"],
                "taboo_gods": ["甲"],
            }
        }
        out, warnings = check_analysis(result)
        assert "rule_warnings" in out
        assert len(warnings) >= 2
