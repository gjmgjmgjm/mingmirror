"""Product year-timing surface: display modes and honesty constraints."""
from __future__ import annotations

from tools.bazi_ai.year_timing_surface import (
    format_product_block,
    resolve_year_timing,
)


class TestYearTimingSurface:
    def test_missing_birth_unavailable(self):
        s = resolve_year_timing("甲午 丁卯 癸酉 庚申", "哪年结婚？", ["2010", "2011"])
        assert s.display_mode == "unavailable"
        assert s.assert_single_year is False

    def test_status_mcq_trend_only(self):
        # Status question must not inject year shortlist display.
        s = resolve_year_timing(
            "丁未 戊申 癸亥 庚申",
            "截至2017年9月，哪项符合命主感情与婚姻状况？",
            ["已婚美满", "离婚", "未婚", "波折"],
            gender="female",
            birth_date="1984-07-05",
            birth_time="12:00",
        )
        assert s.display_mode == "trend_only"
        assert s.candidates == []
        assert s.assert_single_year is False

    def test_parent_death_year_has_candidates(self):
        s = resolve_year_timing(
            "甲午 丁卯 癸酉 庚申",
            "命主父亲于哪年去世?",
            [
                "A 1959 己亥年",
                "B 1963 癸卯年",
                "C 1964 甲辰年",
                "D 1969 己酉年",
            ],
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
        )
        assert s.display_mode in ("hard_shortlist", "soft_hint")
        assert s.assert_single_year is False
        assert len(s.candidates) >= 1
        assert s.disclaimer
        block = format_product_block(s)
        assert "应期" in block
        assert "非确定性" in block or "不是" in s.disclaimer or "非" in s.disclaimer

    def test_open_ended_year_trend_only(self):
        s = resolve_year_timing(
            "甲午 丁卯 癸酉 庚申",
            "命主哪年结婚？",
            options=None,
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
        )
        assert s.display_mode == "trend_only"
        assert s.candidates == []

    def test_open_ended_generic_hidden(self):
        """Non-year free-form questions must not spam the UI panel."""
        s = resolve_year_timing(
            "甲午 丁卯 癸酉 庚申",
            "综合运势",
            options=None,
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
        )
        assert s.display_mode == "unavailable"

    def test_to_dict_serializable(self):
        s = resolve_year_timing(
            "癸亥 壬戌 庚辰 辛巳",
            "命主已经离婚，第二婚是哪一年？",
            ["2017", "2018", "2019", "2020"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
        )
        d = s.to_dict()
        assert "display_mode" in d
        assert d["assert_single_year"] is False

    def test_structural_critic_in_meta_when_shortlist(self):
        s = resolve_year_timing(
            "甲午 丁卯 癸酉 庚申",
            "命主父亲于哪年去世?",
            [
                "A 1959 己亥年",
                "B 1963 癸卯年",
                "C 1964 甲辰年",
                "D 1969 己酉年",
            ],
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
        )
        assert s.display_mode in ("hard_shortlist", "soft_hint")
        assert s.assert_single_year is False
        critic = (s.meta or {}).get("structural_critic") or {}
        # Critic may pick a letter or explain keep_top1; never elevates assert_single_year
        assert critic.get("assert_single_year") is False
        if critic.get("letter"):
            assert critic["letter"] in "ABCD"
            letters = {c.option_letter for c in s.candidates}
            assert critic["letter"] in letters
            preferred = [c for c in s.candidates if c.critic_prefer]
            assert preferred, "critic_prefer flag should mark preferred candidate"
            assert preferred[0].option_letter == critic["letter"]
            d = s.to_dict()
            assert any(
                c.get("critic_prefer") for c in (d.get("candidates") or [])
            )
