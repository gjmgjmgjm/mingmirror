"""Tests for the reflection strategy."""

import asyncio

import pytest

from tools.destiny.contract import ChartInfo
from tools.destiny.strategies.reflection import ReflectionStrategy


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def chart() -> ChartInfo:
    return ChartInfo(
        bazi="甲子 丙寅 戊辰 庚午",
        question="事业如何？",
    )


@pytest.fixture
def reflection() -> ReflectionStrategy:
    return ReflectionStrategy()


@pytest.mark.asyncio
async def test_reflect_downgrades_confidence_when_reasoning_is_weak(
    reflection: ReflectionStrategy,
    chart: ChartInfo,
) -> None:
    raw = {
        "confidence": "high",
        "reasoning": "短",
        "domain_analysis": {"career": "ok"},
    }
    result = await reflection.reflect("bazi", raw, chart)
    assert result["confidence"] != "high"
    assert result["_reflection_applied"] is True
    assert any("推理" in note for note in result["reflection_notes"])


@pytest.mark.asyncio
async def test_reflect_keeps_high_confidence_for_strong_result(
    reflection: ReflectionStrategy,
    chart: ChartInfo,
) -> None:
    raw = {
        "confidence": "high",
        "reasoning": "日主甲木生于寅月，木旺。年月干透火，食神生财。事业适合技术与管理岗位。",
        "basic_info": {"bazi": "甲子 丙寅 戊辰 庚午"},
        "domain_analysis": {
            "career": "适合技术管理",
            "wealth": "正财稳定",
            "marriage": "稳定",
            "health": "注意肝胆",
        },
    }
    result = await reflection.reflect("bazi", raw, chart)
    assert result["confidence"] == "high"
    assert result["_reflection_applied"] is True


def test_sync_reflect(chart: ChartInfo) -> None:
    reflection = ReflectionStrategy()
    raw = {"confidence": "medium", "reasoning": "x" * 50, "domain_analysis": {}}
    result = _run(reflection.reflect("bazi", raw, chart))
    assert result["_reflection_applied"] is True
