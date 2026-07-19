"""Tests for the Zi Wei Dou Shu analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.ziwei.engine import ZiWeiAnalyzer


@pytest.fixture
def sample_chart() -> Dict[str, Any]:
    return {
        "birth_datetime": "1990-05-20T14:30:00",
        "gender": "male",
        "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
        "bazi": "庚午 辛巳 戊寅 己未",
    }


@pytest.fixture
def analyzer(tmp_path: Path) -> ZiWeiAnalyzer:
    return ZiWeiAnalyzer(
        rule_primer_path=Path("tools/ziwei/rule_primer.md"),
        cases_path=Path("tools/ziwei/cases.jsonl"),
    )


@pytest.mark.asyncio
async def test_analyze_returns_mock_when_no_api_key(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    result = await analyzer.analyze(sample_chart)
    assert result["system"] == "ziwei"
    # Structural chart from four pillars (not the old hardcoded mock palace).
    ming = result["basic_info"].get("ming_gong") or ""
    assert ming.endswith("宫") and ming != "未知"
    assert isinstance(result["basic_info"].get("zhu_xing"), list)
    assert result["confidence"] in ("low", "medium")
    assert result["raw"].get("_mock") is True
    for domain in ("career", "wealth", "marriage", "health", "general"):
        assert domain in result["domain_analysis"]
        assert 0 <= result["domain_analysis"][domain]["score"] <= 100
        assert isinstance(result["domain_analysis"][domain]["text"], str)
        assert isinstance(result["domain_analysis"][domain]["keywords"], list)


def test_analyze_sync_wrapper(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    result = analyzer.analyze_sync(sample_chart)
    assert result["system"] == "ziwei"
    assert result["raw"].get("_mock") is True


@pytest.mark.asyncio
async def test_analyze_with_invalid_gender(analyzer: ZiWeiAnalyzer) -> None:
    chart = {
        "birth_datetime": "1990-05-20T14:30:00",
        "gender": "unknown",
        "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
    }
    result = await analyzer.analyze(chart)
    assert result["confidence"] == "low"
    assert "gender" in result["raw"]["error"]
    assert not result["domain_analysis"]


@pytest.mark.asyncio
async def test_analyze_with_missing_birth_datetime(analyzer: ZiWeiAnalyzer) -> None:
    chart = {
        "gender": "male",
        "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
    }
    result = await analyzer.analyze(chart)
    assert "birth_datetime" in result["raw"]["error"]


@pytest.mark.asyncio
async def test_analyze_with_invalid_datetime(analyzer: ZiWeiAnalyzer) -> None:
    chart = {
        "birth_datetime": "not-a-date",
        "gender": "male",
        "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
    }
    result = await analyzer.analyze(chart)
    assert "格式不正确" in result["raw"]["error"]


@pytest.mark.asyncio
async def test_analyze_with_question_focuses_domain(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    result = await analyzer.analyze(sample_chart, question="我的事业怎么样？")
    career = result["domain_analysis"]["career"]
    # Structural mock scores are fixed placeholders (career=70) when no API key.
    assert 0 <= career["score"] <= 100
    assert isinstance(career.get("text"), str)
    # Non-focused domains still have placeholder structure.
    assert "score" in result["domain_analysis"]["wealth"]


@pytest.mark.asyncio
async def test_analyze_calls_llm_when_api_key_provided(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    analyzer.api_key = "fake-key"
    llm_response = {
        "system": "ziwei",
        "basic_info": {"ming_gong": "子宫", "zhu_xing": ["太阳"]},
        "domain_analysis": {
            "career": {"score": 80, "text": "事业顺遂", "keywords": ["事业"]},
            "wealth": {"score": 70, "text": "财运平稳", "keywords": ["财运"]},
            "marriage": {"score": 60, "text": "婚姻和谐", "keywords": ["婚姻"]},
            "health": {"score": 75, "text": "健康良好", "keywords": ["健康"]},
            "general": {"score": 72, "text": "整体不错", "keywords": ["整体"]},
        },
        "confidence": "high",
    }

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps(llm_response)}}],
    })

    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await analyzer.analyze(sample_chart)

    assert result["basic_info"]["ming_gong"] == "子宫"
    assert result["confidence"] == "high"
    assert result["domain_analysis"]["career"]["score"] == 80
    mock_session.post.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_handles_llm_json_parse_error(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    analyzer.api_key = "fake-key"

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": "not valid json"}}],
    })

    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await analyzer.analyze(sample_chart)

    assert result["system"] == "ziwei"
    assert result.get("parse_error") is True
    assert "raw_content" in result


@pytest.mark.asyncio
async def test_analyze_normalizes_domain_scores(
    analyzer: ZiWeiAnalyzer,
    sample_chart: Dict[str, Any],
) -> None:
    analyzer.api_key = "fake-key"
    llm_response = {
        "system": "ziwei",
        "basic_info": {"ming_gong": "子宫"},
        "domain_analysis": {
            "career": {"score": "150", "text": "", "keywords": []},
        },
        "confidence": "unknown",
    }

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps(llm_response)}}],
    })

    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await analyzer.analyze(sample_chart)

    assert result["domain_analysis"]["career"]["score"] == 100
    assert result["domain_analysis"]["wealth"]["score"] == 50
    assert result["confidence"] == "medium"


@pytest.mark.asyncio
async def test_analyze_female_mock(
    analyzer: ZiWeiAnalyzer,
) -> None:
    chart = {
        "birth_datetime": "1992-07-22T06:45:00",
        "gender": "female",
        "location": {"longitude": 121.5, "latitude": 31.2, "timezone": "Asia/Shanghai"},
    }
    result = await analyzer.analyze(chart)
    # birth_datetime alone must derive pillars and produce a real chart (not 未知).
    ming = result["basic_info"].get("ming_gong") or ""
    assert ming.endswith("宫") and ming != "未知"
    assert isinstance(result["basic_info"].get("zhu_xing"), list)
