"""Tests for the debate strategy."""

import asyncio

import pytest

from tools.destiny.contract import ChartInfo, DomainConclusion
from tools.destiny.strategies.debate import DebateStrategy


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def chart() -> ChartInfo:
    return ChartInfo(bazi="甲子 丙寅 戊辰 庚午")


@pytest.fixture
def debate() -> DebateStrategy:
    return DebateStrategy()


@pytest.mark.asyncio
async def test_debate_reaches_high_confidence_on_full_agreement(
    debate: DebateStrategy,
    chart: ChartInfo,
) -> None:
    conclusions = {
        "bazi": [DomainConclusion(domain="career", text="适合技术", confidence="high")],
        "ziwei": [DomainConclusion(domain="career", text="适合技术", confidence="high")],
    }
    result = await debate.debate(chart, conclusions)
    assert result["career"]["text"] == "适合技术"
    assert result["career"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_debate_reports_medium_confidence_on_partial_agreement(
    debate: DebateStrategy,
    chart: ChartInfo,
) -> None:
    conclusions = {
        "bazi": [DomainConclusion(domain="career", text="A", confidence="medium")],
        "ziwei": [DomainConclusion(domain="career", text="A", confidence="medium")],
        "qizheng": [DomainConclusion(domain="career", text="B", confidence="medium")],
    }
    result = await debate.debate(chart, conclusions)
    assert result["career"]["text"] == "A"
    assert result["career"]["confidence"] == "medium"


@pytest.mark.asyncio
async def test_debate_ignores_empty_conclusions(
    debate: DebateStrategy,
    chart: ChartInfo,
) -> None:
    conclusions: dict = {"bazi": [], "ziwei": []}
    result = await debate.debate(chart, conclusions)
    assert "career" not in result


def test_sync_debate(chart: ChartInfo) -> None:
    debate = DebateStrategy()
    conclusions = {
        "bazi": [DomainConclusion(domain="wealth", text="正财", confidence="medium")],
        "ziwei": [DomainConclusion(domain="wealth", text="正财", confidence="medium")],
    }
    result = _run(debate.debate(chart, conclusions))
    assert result["wealth"]["text"] == "正财"
