"""Tests for the destiny benchmark harness."""

import asyncio

from tools.destiny.benchmark import run_benchmark
from tools.destiny.contract import ChartInfo
from tools.destiny.ensemble import MultiDestinyAnalyzer


def _run(coro):
    return asyncio.run(coro)


def test_benchmark_coverage_and_consistency():
    async def bazi_caller(chart: ChartInfo, question: str):
        return {
            "domain_analysis": {
                "career": "bazi-career",
                "wealth": "bazi-wealth",
                "marriage": "bazi-marriage",
                "health": "bazi-health",
            }
        }

    async def qizheng_caller(chart: ChartInfo, question: str):
        return {
            "domain_analysis": {
                "career": "bazi-career",
                "wealth": "bazi-wealth",
                "marriage": "bazi-marriage",
                "health": "extra-health",
            }
        }

    ensemble = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
    )

    cases = [
        {"bazi": "甲子 丙寅 戊辰 庚午", "question": "事业"},
        {"bazi": "乙丑 丁卯 己巳 辛未", "question": "财运"},
    ]

    result = _run(run_benchmark(cases, bazi_caller, ensemble))

    assert result["cases"] == 2
    assert result["bazi_avg_coverage"] == 4.0
    # Ensemble covers the same 4 domains (health consensus may be empty if
    # texts differ, so coverage depends on exact matching).
    assert result["ensemble_avg_coverage"] >= 3.0
    assert 0.0 <= result["consistency_with_bazi"] <= 1.0
    assert len(result["per_case"]) == 2
