"""Tests for tools/bazi_ai/."""

import json
from pathlib import Path

import pytest

from tools.bazi_ai.case_builder import build_case_database, correct_text, extract_bazi
from tools.bazi_ai.engine import retrieve_similar_cases


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
    def test_retrieve(self, tmp_path: Path):
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
        results = retrieve_similar_cases("乙卯 戊寅 庚子 丙子", "问事业", cases_path, top_k=1)
        assert len(results) == 1
        assert results[0]["bazi"] == "乙卯 戊寅 庚子 丙子"

    def test_retrieve_empty(self, tmp_path: Path):
        results = retrieve_similar_cases("甲子 丙寅 戊辰 庚午", "", tmp_path / "missing.jsonl", top_k=3)
        assert results == []
