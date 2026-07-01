"""Tests for tools/bazi_ai/evaluator.py."""

from tools.bazi_ai.evaluator import check_format, core_signature


def test_check_format_complete():
    result = {
        "basic_info": {},
        "reasoning": "",
        "domain_analysis": {},
        "summary": [],
        "confidence": "high",
        "caveats": [],
    }
    assert check_format(result) == []


def test_check_format_missing():
    result = {"basic_info": {}, "reasoning": ""}
    missing = check_format(result)
    assert "domain_analysis" in missing
    assert "summary" in missing


def test_core_signature():
    result = {
        "basic_info": {
            "pattern": "伤官格",
            "useful_gods": ["水", "木"],
            "taboo_gods": ["金"],
        },
        "domain_analysis": {
            "career": "技术",
            "wealth": "小康",
            "marriage": "晚婚",
            "health": "注意肾",
        },
    }
    sig = core_signature(result)
    assert "伤官格" in sig
    assert "技术" in sig
    assert "小康" in sig
