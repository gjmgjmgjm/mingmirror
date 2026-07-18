"""Unit tests for tools.bazi_ai.report_template (可解释报告)."""
from __future__ import annotations

from tools.bazi_ai.report_template import build_report, render_report

SAMPLE_BAZI = "乙卯 戊寅 庚子 丙子"


class TestRenderReport:
    def test_zero_api_markdown(self):
        md = render_report(SAMPLE_BAZI, gender="male")
        assert "命盘解读报告" in md
        assert SAMPLE_BAZI in md
        assert "男命" in md
        assert "确定性" in md
        assert "用神" in md or "忌神" in md

    def test_female_label(self):
        md = render_report(SAMPLE_BAZI, gender="女")
        assert "女命" in md

    def test_sections_numbered(self):
        md = render_report(SAMPLE_BAZI, gender="male")
        assert "## 一、" in md
        assert "## 二、" in md


class TestBuildReport:
    def test_structure(self):
        report = build_report(SAMPLE_BAZI, gender="male")
        assert "meta" in report or "sections" in report
        sections = report["sections"]
        ids = [s["id"] for s in sections]
        assert "chart" in ids
        assert "yongshen" in ids
        for s in sections:
            assert s["trust"] in ("certain", "ai")
            assert "title" in s
            assert "data" in s

    def test_chart_pillars(self):
        report = build_report(SAMPLE_BAZI, gender="male")
        chart = next(s for s in report["sections"] if s["id"] == "chart")
        pillars = chart["data"]["pillars"]
        assert len(pillars) == 4
        assert pillars[2]["stem_shishen"] == "日主"
        assert chart["data"]["day_master"] == "庚"

    def test_yongshen_lists(self):
        report = build_report(SAMPLE_BAZI, gender="male")
        ys = next(s for s in report["sections"] if s["id"] == "yongshen")
        assert isinstance(ys["data"]["useful_gods"], list)
        assert isinstance(ys["data"]["taboo_gods"], list)

    def test_with_llm_result_adds_ai_sections(self):
        fake = {
            "domain_analysis": {
                "career": "事业平稳",
                "wealth": "财运一般",
                "marriage": "感情待缘",
                "health": "注意脾胃",
            },
            "personality": "果断刚毅",
            "summary": ["整体中平", "宜守不宜攻"],
            "quxiang": {"day_master": "刀剑之金"},
        }
        report = build_report(SAMPLE_BAZI, gender="male", result=fake)
        ids = [s["id"] for s in report["sections"]]
        assert "quxiang" in ids
        assert "life" in ids
        assert "summary" in ids

    def test_birth_info_passthrough(self):
        report = build_report(
            SAMPLE_BAZI,
            gender="male",
            birth_info={
                "birth_date": "1990-02-15",
                "birth_time": "12:00",
                "calendar_type": "solar",
            },
        )
        assert report["sections"]
