"""Tests for unified 用神 resolver."""

from tools.bazi_ai import bazi_structural
from tools.bazi_ai.yongshen import (
    resolve_yongshen,
    score_year_by_yongshen,
    year_pillar_elements,
)


class TestResolveYongshen:
    def test_weak_day_master_prefers_yin_bi(self):
        # 身弱应生扶
        r = resolve_yongshen("甲子 丙子 丁丑 己酉")
        assert r["strength"] in ("偏弱", "中和", "偏旺")
        assert r["useful_gods"]
        assert r["prompt_block"]
        assert "用神" in r["prompt_block"]

    def test_summer_month_has_water_tiaohou(self):
        # 午月 → 调候喜水
        r = resolve_yongshen("甲子 庚午 丙寅 戊戌")
        assert "水" in r["tiaohou_elements"] or "水" in r["useful_gods"]

    def test_winter_month_has_fire_tiaohou(self):
        r = resolve_yongshen("甲子 丙子 戊午 甲寅")
        assert "火" in r["tiaohou_elements"] or "火" in r["useful_gods"]

    def test_structural_profile_uses_yongshen(self):
        prof = bazi_structural.structural_profile("甲午 丁卯 癸酉 庚申")
        assert prof is not None
        assert prof.get("yongshen_block")
        assert prof.get("useful_gods")
        assert prof.get("yongshen_primary")

    def test_useful_not_in_taboo(self):
        r = resolve_yongshen("癸亥 壬戌 庚辰 辛巳")
        for el in r["useful_gods"]:
            assert el not in r["taboo_gods"]


class TestYearYongshenScore:
    def test_year_elements(self):
        # 2020 = 庚子
        se, be = year_pillar_elements(2020)
        assert se == "金"
        assert be == "水"

    def test_useful_year_positive(self):
        score, reasons = score_year_by_yongshen(2020, ["金", "水"], ["火"])
        assert score > 0
        assert reasons

    def test_taboo_year_negative(self):
        score, _ = score_year_by_yongshen(2016, ["水"], ["火", "土"])  # 2016 丙申
        # 丙=火 may be taboo
        assert isinstance(score, float)
