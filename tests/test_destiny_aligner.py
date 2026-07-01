"""Tests for destiny output alignment."""

from tools.destiny.aligner import align


def test_align_maps_bazi_domains():
    raw = {
        "domain_analysis": {
            "career": "技术岗位",
            "wealth": "正财稳定",
            "marriage": "婚姻平和",
            "health": "注意脾胃",
        },
        "confidence": "medium",
    }
    conclusions = align(raw, "bazi")
    domains = {c.domain for c in conclusions}
    assert domains == {"career", "wealth", "marriage", "health"}
    assert all(c.confidence == "medium" for c in conclusions)


def test_align_maps_chinese_keys():
    raw = {
        "domain_analysis": {
            "事业": "技术岗位",
            "财运": "正财稳定",
            "婚姻": "婚姻平和",
            "健康": "注意脾胃",
        },
        "confidence": "high",
    }
    conclusions = align(raw, "qizheng")
    mapping = {c.domain: c.text for c in conclusions}
    assert mapping["career"] == "技术岗位"
    assert mapping["wealth"] == "正财稳定"
    assert mapping["marriage"] == "婚姻平和"
    assert mapping["health"] == "注意脾胃"


def test_align_ignores_empty_text():
    raw = {
        "domain_analysis": {
            "career": "",
            "wealth": "有财",
        },
        "confidence": "low",
    }
    conclusions = align(raw, "bazi")
    assert len(conclusions) == 1
    assert conclusions[0].domain == "wealth"


def test_align_defaults_unknown_domain_to_general():
    raw = {
        "domain_analysis": {"family": "家庭和睦"},
        "confidence": "medium",
    }
    conclusions = align(raw, "ziwei")
    assert len(conclusions) == 1
    assert conclusions[0].domain == "general"
