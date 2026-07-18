"""Tests for the Qi Zheng Si Yu analyzer."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.qizheng.engine import QiZhengAnalyzer, analyze_yearly
from tools.qizheng.star_tables import MIAO_WANG_YANG


@pytest.fixture
def analyzer(tmp_path: Path):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "chart": "甲子 丙寅 戊辰 庚午",
                "analysis": "测试案例",
                "domains": {"career": "技术"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return QiZhengAnalyzer(
        rule_primer_path=None,
        cases_path=cases_path,
        api_key="",
        top_k=1,
    )


def test_analyze_mock_fallback_returns_domains(analyzer):
    result = analyzer.analyze({"bazi": "甲子 丙寅 戊辰 庚午"})
    # analyze is async; run it explicitly for the sync test helper.
    result = run_sync(result)

    assert "error" not in result
    assert result["basic_info"]["chart"] == "甲子 丙寅 戊辰 庚午"
    assert result["basic_info"]["day_master"] == "戊"
    for domain in ("career", "wealth", "marriage", "health"):
        assert domain in result["domain_analysis"]
        assert result["domain_analysis"][domain]
    assert result["confidence"] == "low"
    assert result.get("_mock") is True


def test_analyze_invalid_chart(analyzer):
    result = run_sync(analyzer.analyze({"bazi": "不是八字"}))
    assert "error" in result
    assert result["confidence"] == "low"
    assert not result.get("domain_analysis")


def test_analyze_api_success(analyzer):
    api_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "basic_info": {
                                "chart": "甲子 丙寅 戊辰 庚午",
                                "day_master": "戊",
                                "life_palace": "巳",
                                "body_palace": "亥",
                                "dominant_stars": ["太阳"],
                            },
                            "reasoning": "测试推理",
                            "domain_analysis": {
                                "career": "事业顺遂",
                                "wealth": "财运稳定",
                                "marriage": "婚姻平和",
                                "health": "健康良好",
                            },
                            "summary": ["日主戊土"],
                            "confidence": "medium",
                            "caveats": [],
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=api_response)
    mock_session.post = MagicMock(return_value=mock_resp)

    analyzer.api_key = "test-key"
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = run_sync(analyzer.analyze({"bazi": "甲子 丙寅 戊辰 庚午"}))

    assert result["basic_info"]["day_master"] == "戊"
    assert result["domain_analysis"]["career"] == "事业顺遂"
    assert result["confidence"] == "medium"


def test_analyze_api_bad_json_falls_back(analyzer):
    api_response = {
        "choices": [{"message": {"content": "not valid json"}}]
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=api_response)
    mock_session.post = MagicMock(return_value=mock_resp)

    analyzer.api_key = "test-key"
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = run_sync(analyzer.analyze({"bazi": "甲子 丙寅 戊辰 庚午"}))

    assert "parse_error" in result
    assert result["basic_info"]["chart"] == "甲子 丙寅 戊辰 庚午"


def run_sync(coro):
    """Helper to run async results in sync test helpers."""
    import asyncio

    return asyncio.run(coro)


def test_analyze_yearly_mock_fallback():
    result = run_sync(
        analyze_yearly(
            "甲子 丙寅 戊辰 庚午",
            gender="male",
            birth_year=1984,
            mode="10y",
            api_key="",
        )
    )
    assert "error" not in result
    assert result.get("dayun_summary")
    assert result.get("yearly_analysis")
    assert len(result["yearly_analysis"]) == 10
    assert result.get("_rule_based") is True
    assert result["confidence"] == "low"
    assert result.get("trust") == "certain_simplified"
    summary = result.get("structural_summary") or {}
    assert summary.get("life_palace")
    assert summary.get("day_master")
    assert summary.get("liunian_count") == 10
    for y in result["yearly_analysis"]:
        assert all(
            k in y
            for k in (
                "year",
                "pillar",
                "overview",
                "career",
                "wealth",
                "marriage",
                "health",
                "caution",
                "active_palace",
                "palace_lord",
                "palace_lord_relation",
                "stars_in_palace",
                "strongest_star",
                "star_impact",
                "taishui_impact",
                "four_remainder_note",
                "pattern_note",
            )
        )
        assert isinstance(y["stars_in_palace"], list)
        assert isinstance(y["strongest_star"], dict)
        assert "name" in y["strongest_star"]
        assert "strength" in y["strongest_star"]
        assert y["palace_lord_relation"]
        assert y["taishui_impact"]


def test_analyze_yearly_invalid_chart():
    result = run_sync(
        analyze_yearly(
            "不是八字",
            gender="male",
            birth_year=1984,
            mode="10y",
            api_key="",
        )
    )
    assert "error" in result
    assert result["dayun_summary"] == []
    assert result["yearly_analysis"] == []


def test_analyze_yearly_lifetime_mode():
    result = run_sync(
        analyze_yearly(
            "甲子 丙寅 戊辰 庚午",
            gender="male",
            birth_year=1984,
            mode="lifetime",
            api_key="",
        )
    )
    assert "error" not in result
    assert result.get("dayun_summary")
    assert result.get("yearly_analysis")
    assert result.get("_rule_based") is True


def test_analyze_yearly_dignity_table_switch():
    default = run_sync(
        analyze_yearly(
            "甲子 丙寅 戊辰 庚午",
            gender="male",
            birth_year=1984,
            mode="10y",
            api_key="",
        )
    )
    yang = run_sync(
        analyze_yearly(
            "甲子 丙寅 戊辰 庚午",
            gender="male",
            birth_year=1984,
            mode="10y",
            api_key="",
            dignity_table=MIAO_WANG_YANG,
        )
    )
    assert len(default["yearly_analysis"]) == len(yang["yearly_analysis"])
    diffs = sum(
        1
        for d, y in zip(default["yearly_analysis"], yang["yearly_analysis"])
        if d["star_impact"] != y["star_impact"]
    )
    assert diffs > 0
