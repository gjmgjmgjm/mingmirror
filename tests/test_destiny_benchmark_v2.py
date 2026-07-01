"""Tests for the quantitative destiny benchmark v2."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tools.destiny.benchmark_v2 import (
    _aggregate_scores,
    _coverage,
    _evaluate_system,
    _keyword_overlap,
    _system_consistency,
    load_annotated_cases,
    run_benchmark_v2,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def sample_cases() -> List[Dict[str, Any]]:
    return [
        {
            "bazi": "甲子 丙寅 戊辰 庚午",
            "gender": "male",
            "birth_datetime": "1984-02-15T10:30:00",
            "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
            "question": "事业如何？",
            "annotations": {
                "career": {"text": "适合技术", "keywords": ["技术", "管理"]},
                "wealth": {"text": "正财稳定", "keywords": ["正财"]},
            },
        },
        {
            "bazi": "乙丑 丁卯 己巳 辛未",
            "gender": "female",
            "birth_datetime": "1985-03-22T14:20:00",
            "location": {"longitude": 121.5, "latitude": 31.2, "timezone": "Asia/Shanghai"},
            "question": "",
            "annotations": {
                "career": {"text": "适合行政", "keywords": ["行政"]},
                "wealth": {"text": "收入稳定", "keywords": ["稳定"]},
            },
        },
    ]


def test_load_annotated_cases(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"bazi": "甲子 丙寅 戊辰 庚午", "annotations": {}}\n\n{"bazi": "乙丑 丁卯 己巳 辛未", "annotations": {}}\n',
        encoding="utf-8",
    )
    cases = load_annotated_cases(path)
    assert len(cases) == 2
    assert cases[0]["bazi"] == "甲子 丙寅 戊辰 庚午"


def test_keyword_overlap_perfect_match() -> None:
    annotation = {"text": "适合技术", "keywords": ["技术", "管理"]}
    prediction = {"text": "适合技术管理岗位", "keywords": ["技术", "管理"]}
    p, r, f1 = _keyword_overlap(annotation, prediction)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0


def test_keyword_overlap_partial() -> None:
    annotation = {"text": "适合技术", "keywords": ["技术", "管理"]}
    prediction = {"text": "适合行政岗位", "keywords": ["行政"]}
    p, r, f1 = _keyword_overlap(annotation, prediction)
    assert f1 == 0.0


def test_coverage() -> None:
    annotations = {"career": {"text": "a"}, "wealth": {"text": "b"}}
    result = {"domain_analysis": {"career": "a", "health": "c"}}
    assert _coverage(annotations, result) == 0.5


def test_aggregate_scores() -> None:
    agg = _aggregate_scores([0.2, 0.4, 0.6])
    assert agg["mean"] == pytest.approx(0.4)
    assert agg["min"] == 0.2
    assert agg["max"] == 0.6
    assert agg["count"] == 3


def test_evaluate_system(sample_cases: List[Dict[str, Any]]) -> None:
    results = [
        {
            "domain_analysis": {
                "career": {"text": "适合技术", "keywords": ["技术"]},
                "wealth": {"text": "正财稳定", "keywords": ["正财"]},
            },
            "confidence": "high",
        },
        {
            "domain_analysis": {
                "career": {"text": "适合行政", "keywords": ["行政"]},
                "wealth": {"text": "收入稳定", "keywords": ["稳定"]},
            },
            "confidence": "medium",
        },
    ]
    metrics = _evaluate_system("mock", sample_cases, results)
    assert metrics["coverage"]["mean"] == 1.0
    assert metrics["domain_metrics"]["career"]["f1"]["mean"] > 0
    assert metrics["calibration"]["high"]["count"] >= 1


def test_system_consistency() -> None:
    results_a = [
        {"domain_analysis": {"career": {"text": "A", "keywords": ["x"]}}},
    ]
    results_b = [
        {"domain_analysis": {"career": {"text": "A", "keywords": ["x"]}}},
    ]
    consistency = _system_consistency({"a": results_a, "b": results_b})
    assert consistency["mean"] == 1.0


def test_run_benchmark_v2_mock_only(sample_cases: List[Dict[str, Any]]) -> None:
    report = _run(run_benchmark_v2(sample_cases))
    assert report["cases"] == 2
    assert report["api_key_present"] is False
    assert "bazi" in report["system_metrics"]
    assert "ensemble_single" in report["system_metrics"]
    assert "inter_system_consistency" in report
