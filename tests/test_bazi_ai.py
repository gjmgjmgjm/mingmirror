"""Tests for tools/bazi_ai/."""

import json
from pathlib import Path

import pytest

from tools.bazi_ai.case_builder import build_case_database, correct_text, extract_bazi
from tools.bazi_ai.engine import (
    _rule_based_yearly,
    _strip_confidence_annotations,
    retrieve_similar_cases,
)


class TestExtractBazi:
    @pytest.mark.parametrize("text, expected", [
        ("八字是 甲子 丙寅 戊辰 庚午", "甲子 丙寅 戊辰 庚午"),
        ("我的八字：甲子丙寅戊辰庚午", "甲子 丙寅 戊辰 庚午"),
        ("没有八字", None),
    ])
    def test_extract_bazi(self, text, expected):
        assert extract_bazi(text) == expected


class TestCorrectText:
    def test_correct_text(self):
        glossary = {"巴字": "八字", "八只": "八字"}
        assert correct_text("这巴字不错", glossary) == "这八字不错"
        assert correct_text("这八只不错", glossary) == "这八字不错"


class TestBuildCaseDatabase:
    def test_build(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        md = kb_dir / "test_knowledge_final.md"
        md.write_text(
            "# 甲子 丙寅 戊辰 庚午\n\n"
            "## 八字：甲子 丙寅 戊辰 庚午\n\n"
            "**来源视频**：2025-01-01_test\n\n"
            "### 命理师分析\n\n"
            "> 这八字身强，喜用神是金水。\n\n"
            "### 关键信息\n\n"
            "**涉及术语**：身强，用神\n\n"
            "**主要结论**：\n- 事业有成\n- 财运不错\n",
            encoding="utf-8",
        )
        glossary = tmp_path / "g.json"
        glossary.write_text("{}", encoding="utf-8")
        out = tmp_path / "cases.jsonl"
        summary = build_case_database(kb_dir, out, glossary)
        assert summary["total_cases"] == 1
        assert out.exists()
        case = json.loads(out.read_text(encoding="utf-8").strip())
        assert case["bazi"] == "甲子 丙寅 戊辰 庚午"
        assert case["day_master"] == "戊"
        assert case["month_branch"] == "寅"
        assert "身强" in case["key_terms"]


class TestRetrieveSimilarCases:
    @pytest.mark.asyncio
    async def test_retrieve(self, tmp_path: Path):
        cases_path = tmp_path / "cases.jsonl"
        cases_path.write_text(
            json.dumps({
                "bazi": "乙卯 戊寅 庚子 丙子",
                "analysis_corrected": "庚金日主，伤官格",
                "key_terms": ["伤官"],
                "conclusions": [],
            }, ensure_ascii=False)
            + "\n"
            + json.dumps({
                "bazi": "甲申 癸酉 壬子 甲辰",
                "analysis_corrected": "壬水日主",
                "key_terms": ["身旺"],
                "conclusions": [],
            }, ensure_ascii=False)
            + "\n"
        )
        results = await retrieve_similar_cases("乙卯 戊寅 庚子 丙子", "问事业", cases_path, top_k=1)
        assert len(results) == 1
        assert results[0]["bazi"] == "乙卯 戊寅 庚子 丙子"


class TestStripConfidenceAnnotations:
    def test_strips_chinese_confidence_marker(self):
        assert _strip_confidence_annotations("适合技术行业。（置信度：low）") == "适合技术行业。"
        assert _strip_confidence_annotations("适合技术行业(置信度:medium)") == "适合技术行业"
        assert _strip_confidence_annotations("无标记文本") == "无标记文本"


class TestRuleBasedYearly:
    def test_fallback_avoids_template_phrases(self):
        result = _rule_based_yearly(
            "癸未 己未 甲申 壬申",
            [
                {"pillar": "戊午", "start_age": 0, "end_age": 8},
                {"pillar": "丁巳", "start_age": 8, "end_age": 18},
                {"pillar": "丙辰", "start_age": 18, "end_age": 28},
                {"pillar": "乙卯", "start_age": 28, "end_age": 38},
            ],
            [{"year": 2026, "pillar": "丙午"}, {"year": 2027, "pillar": "丁未"}],
            1993,
        )
        forbidden = {"顺其自然", "按部就班", "按年度节奏推进", "量入为出", "规律作息"}
        combined = " ".join(
            y.get("overview", "") + y.get("career", "") + y.get("wealth", "")
            + y.get("marriage", "") + y.get("health", "")
            for y in result["yearly_analysis"]
        )
        for phrase in forbidden:
            assert phrase not in combined, f"fallback contains forbidden phrase: {phrase}"
        assert result.get("_rule_based") is True
        assert all("算法兜底" not in c for c in result.get("caveats", []))
        assert all("AI 输出无法解析" not in c for c in result.get("caveats", []))

    def test_fallback_includes_key_event_and_milestones(self):
        result = _rule_based_yearly(
            "癸未 己未 甲申 壬申",
            [
                {"pillar": "戊午", "start_age": 0, "end_age": 8},
                {"pillar": "丁巳", "start_age": 8, "end_age": 18},
                {"pillar": "丙辰", "start_age": 18, "end_age": 28},
                {"pillar": "乙卯", "start_age": 28, "end_age": 38},
            ],
            [{"year": 2026, "pillar": "丙午"}, {"year": 2027, "pillar": "丁未"}],
            1993,
        )
        for y in result["yearly_analysis"]:
            assert "key_event" in y
            assert isinstance(y["key_event"], str)
            assert len(y["key_event"]) > 0
        assert isinstance(result.get("milestones"), list)

    @pytest.mark.asyncio
    async def test_retrieve_empty(self, tmp_path: Path):
        results = await retrieve_similar_cases("甲子 丙寅 戊辰 庚午", "", tmp_path / "missing.jsonl", top_k=3)
        assert results == []
