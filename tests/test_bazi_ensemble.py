"""Tests for tools/bazi_ai/ensemble.py."""

import pytest

from tools.bazi_ai.ensemble import _aggregate, analyze_bazi_ensemble


def test_aggregate_consensus():
    results = [
        {
            "basic_info": {
                "bazi": "甲子 丙寅 戊辰 庚午",
                "pattern": "伤官格",
                "useful_gods": ["水", "木"],
                "taboo_gods": ["金"],
            },
            "domain_analysis": {"career": "技术", "wealth": "小康"},
            "summary": ["身强", "喜水木"],
            "confidence": "high",
            "caveats": [],
        },
        {
            "basic_info": {
                "bazi": "甲子 丙寅 戊辰 庚午",
                "pattern": "伤官格",
                "useful_gods": ["水", "木"],
                "taboo_gods": ["金"],
            },
            "domain_analysis": {"career": "技术", "wealth": "中产"},
            "summary": ["身强", "喜水木"],
            "confidence": "medium",
            "caveats": [],
        },
    ]
    agg = _aggregate(results)
    assert agg["basic_info"]["pattern"] == "伤官格"
    assert "水" in agg["basic_info"]["useful_gods"]
    assert agg["domain_analysis"]["career"] == "技术"
    assert agg["confidence"] == "medium"
    assert agg["_ensemble_runs"] == 2


@pytest.mark.asyncio
async def test_analyze_bazi_ensemble_mock(tmp_path):
    # No API key; should fall back to mock and aggregate.
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("", encoding="utf-8")
    knowledge_path = tmp_path / "rule_primer.md"
    knowledge_path.write_text("# 基础知识", encoding="utf-8")

    result = await analyze_bazi_ensemble(
        "乙卯 戊寅 庚子 丙子",
        runs=2,
        cases_path=cases_path,
        knowledge_base_path=knowledge_path,
        top_k=0,
    )
    assert result["_ensemble_runs"] == 2
    assert result["basic_info"]["bazi"] == "乙卯 戊寅 庚子 丙子"
