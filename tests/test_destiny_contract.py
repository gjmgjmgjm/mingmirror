"""Tests for the destiny shared contract."""

from tools.destiny.contract import ChartInfo, DomainConclusion, SystemResult


def test_chart_info_to_dict():
    chart = ChartInfo(
        bazi="甲子 丙寅 戊辰 庚午",
        system="bazi",
        question="事业",
        gender="男",
        birth_datetime="1990-01-01 12:00",
    )
    data = chart.to_dict()
    assert data["bazi"] == "甲子 丙寅 戊辰 庚午"
    assert data["system"] == "bazi"
    assert data["question"] == "事业"
    assert data["gender"] == "男"


def test_domain_conclusion_to_dict():
    conclusion = DomainConclusion(domain="career", text="事业顺遂", confidence="high")
    data = conclusion.to_dict()
    assert data == {
        "domain": "career",
        "text": "事业顺遂",
        "confidence": "high",
        "system": "",
    }


def test_system_result_to_dict():
    chart = ChartInfo(bazi="甲子 丙寅 戊辰 庚午")
    conclusion = DomainConclusion(domain="wealth", text="财运平稳")
    result = SystemResult(
        system="bazi",
        chart_info=chart,
        raw_result={"confidence": "medium"},
        domain_conclusions=[conclusion],
    )
    data = result.to_dict()
    assert data["system"] == "bazi"
    assert data["chart_info"]["bazi"] == "甲子 丙寅 戊辰 庚午"
    assert data["raw_result"]["confidence"] == "medium"
    assert data["domain_conclusions"][0]["domain"] == "wealth"
