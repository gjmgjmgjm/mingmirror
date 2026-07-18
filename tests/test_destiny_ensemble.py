"""Tests for the multi-destiny ensemble."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tools.destiny.contract import ChartInfo
from tools.destiny.ensemble import MultiDestinyAnalyzer


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mock_analyzer():
    """Return an ensemble with deterministic mocked subsystems."""

    async def bazi_caller(chart: ChartInfo, question: str):
        return {
            "basic_info": {"bazi": chart.bazi},
            "domain_analysis": {
                "career": "bazi-career",
                "wealth": "bazi-wealth",
                "marriage": "bazi-marriage",
                "health": "bazi-health",
            },
            "confidence": "medium",
        }

    async def ziwei_caller(chart: ChartInfo, question: str):
        return {
            "basic_info": {"bazi": chart.bazi},
            "domain_analysis": {
                "career": "ziwei-career",
                "wealth": "bazi-wealth",
                "marriage": "bazi-marriage",
                "health": "bazi-health",
            },
            "confidence": "medium",
        }

    async def qizheng_caller(chart: ChartInfo, question: str):
        return {
            "basic_info": {"bazi": chart.bazi},
            "domain_analysis": {
                "career": "qizheng-career",
                "wealth": "bazi-wealth",
                "marriage": "bazi-marriage",
                "health": "bazi-health",
            },
            "confidence": "medium",
        }

    return MultiDestinyAnalyzer(
        systems=["bazi", "ziwei", "qizheng"],
        callables={
            "bazi": bazi_caller,
            "ziwei": ziwei_caller,
            "qizheng": qizheng_caller,
        },
    )


def test_ensemble_returns_all_systems(mock_analyzer):
    chart = ChartInfo(bazi="甲子 丙寅 戊辰 庚午")
    result = _run(mock_analyzer.analyze(chart))

    assert result["bazi"] == "甲子 丙寅 戊辰 庚午"
    systems = {sr["system"] for sr in result["per_system"]}
    assert systems == {"bazi", "ziwei", "qizheng"}


def test_weighted_fusion_prefers_high_weight_system():
    """Calibration weights should tip consensus when texts disagree."""

    async def bazi_caller(chart: ChartInfo, question: str):
        return {
            "domain_analysis": {"career": "八字说升职"},
            "confidence": "medium",
        }

    async def qizheng_caller(chart: ChartInfo, question: str):
        return {
            "domain_analysis": {"career": "七政说平稳"},
            "confidence": "medium",
        }

    analyzer = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        system_weights={"bazi": 0.8, "qizheng": 0.2},
    )
    result = _run(analyzer.analyze(ChartInfo(bazi="甲子 丙寅 戊辰 庚午")))
    assert result["aligned"]["career"]["consensus"] == "八字说升职"
    assert result["system_weights"]["bazi"] == 0.8
    assert result["weights_source"] == "calibration"
    assert result["aligned"]["career"].get("weight_share", 0) >= 0.7

    # Flip weights → consensus flips
    analyzer2 = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        system_weights={"bazi": 0.2, "qizheng": 0.8},
    )
    result2 = _run(analyzer2.analyze(ChartInfo(bazi="甲子 丙寅 戊辰 庚午")))
    assert result2["aligned"]["career"]["consensus"] == "七政说平稳"


def test_ensemble_high_confidence_on_full_agreement():
    async def same_caller(chart: ChartInfo, question: str):
        return {
            "domain_analysis": {
                "career": "一致",
                "wealth": "一致",
                "marriage": "一致",
                "health": "一致",
            },
            "confidence": "high",
        }

    analyzer = MultiDestinyAnalyzer(
        systems=["bazi", "ziwei"],
        callables={"bazi": same_caller, "ziwei": same_caller},
    )
    result = _run(analyzer.analyze(ChartInfo(bazi="甲子 丙寅 戊辰 庚午")))

    assert result["overall_confidence"] == "high"
    for domain in ("career", "wealth", "marriage", "health"):
        assert result["aligned"][domain]["confidence"] == "high"
        assert result["aligned"][domain]["dissent"] == []


def test_ensemble_reports_conflict_and_lowers_confidence():
    async def bazi_caller(chart: ChartInfo, question: str):
        return {"domain_analysis": {"career": "A"}, "confidence": "medium"}

    async def ziwei_caller(chart: ChartInfo, question: str):
        return {"domain_analysis": {"career": "A"}, "confidence": "medium"}

    async def qizheng_caller(chart: ChartInfo, question: str):
        return {"domain_analysis": {"career": "B"}, "confidence": "medium"}

    analyzer = MultiDestinyAnalyzer(
        systems=["bazi", "ziwei", "qizheng"],
        callables={
            "bazi": bazi_caller,
            "ziwei": ziwei_caller,
            "qizheng": qizheng_caller,
        },
    )
    result = _run(analyzer.analyze(ChartInfo(bazi="甲子 丙寅 戊辰 庚午")))

    career = result["aligned"]["career"]
    assert career["consensus"] == "A"
    assert career["confidence"] == "medium"
    assert "B" in career["dissent"]


def test_ensemble_reports_missing_system_as_error():
    analyzer = MultiDestinyAnalyzer(
        systems=["bazi", "ziwei"],
        callables={
            "bazi": AsyncMock(return_value={"domain_analysis": {"career": "ok"}}),
        },
    )
    result = _run(analyzer.analyze(ChartInfo(bazi="甲子 丙寅 戊辰 庚午")))

    ziwei_result = next(sr for sr in result["per_system"] if sr["system"] == "ziwei")
    assert "error" in ziwei_result["raw_result"]
    assert "not available" in ziwei_result["raw_result"]["error"]


def test_ensemble_accepts_dict_chart_info(mock_analyzer):
    result = _run(mock_analyzer.analyze({"bazi": "甲子 丙寅 戊辰 庚午"}))
    assert result["bazi"] == "甲子 丙寅 戊辰 庚午"
