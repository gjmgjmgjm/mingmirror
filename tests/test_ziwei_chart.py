"""Tests for deterministic ziwei structural chart + API."""
from __future__ import annotations

import asyncio

from tools.ziwei.chart import (
    chart_from_birth,
    five_element_bureau,
    life_palace_stem,
    liunian_years,
    structural_chart,
    yearly_bundle,
)
from tools.ziwei.engine import ZiWeiAnalyzer


def test_life_palace_nayin_bureau():
    """五行局 must use 命宫干支纳音 (五虎遁), not year pillar alone."""
    # 甲年 + 命宫巳 → 己巳 → 大林木 → 木三局
    assert life_palace_stem("甲", "巳") == "己"
    el, bureau = five_element_bureau(year_stem="甲", life_palace="巳")
    assert el == "木" and bureau == 3
    # 乙年 + 命宫寅 → 戊寅 → 城头土 → 土五局
    assert life_palace_stem("乙", "寅") == "戊"
    el2, b2 = five_element_bureau(year_stem="乙", life_palace="寅")
    assert el2 == "土" and b2 == 5
    # structural_chart must apply life-palace bureau
    chart = structural_chart("乙卯 戊寅 庚子 丙子", gender="male", day_of_month=15)
    assert chart is not None
    assert chart["bureau_source"] == "life_palace_nayin"
    assert chart["five_element"] == el2
    assert chart["bureau"] == b2


def test_structural_chart_deterministic():
    a = structural_chart("乙卯 戊寅 庚子 丙子", gender="male", day_of_month=15)
    b = structural_chart("乙卯 戊寅 庚子 丙子", gender="male", day_of_month=15)
    assert a is not None and b is not None
    assert a["life_palace"] == b["life_palace"]
    assert a["ziwei_branch"] == b["ziwei_branch"]
    assert len(a["palaces"]) == 12
    assert a["bureau"] in (2, 3, 4, 5, 6)
    assert a["zhu_xing"]
    # 辅星 / 煞星 / 大限
    assert a["major_limits"] and len(a["major_limits"]) == 12
    assert a["major_limits"][0]["start_age"] == a["bureau"]
    assert any(
        p.get("aux_stars") for p in a["palaces"]
    ), "expected some aux stars placed"
    assert any(
        p.get("sha_stars") for p in a["palaces"]
    ), "expected some sha stars placed"
    # 命宫应拆分 main/aux/sha
    ming = next(p for p in a["palaces"] if p["name"] == "命宫")
    assert "main_stars" in ming and "aux_stars" in ming


def test_chart_from_birth_day():
    c = chart_from_birth(
        "乙卯 戊寅 庚子 丙子", gender="female", birth_date="1990-02-15"
    )
    assert c is not None
    assert c["day_of_month_used"] == 15
    assert c["gender"] == "female"


def test_ziwei_analyzer_mock_structural():
    analyzer = ZiWeiAnalyzer()
    result = asyncio.run(
        analyzer.analyze(
            {"bazi": "乙卯 戊寅 庚子 丙子", "gender": "male", "birth_date": "1990-02-15"},
            question="",
        )
    )
    assert result["system"] == "ziwei"
    assert result["basic_info"].get("ming_gong")
    assert result["basic_info"].get("zhu_xing") is not None
    assert result.get("structural") or result["basic_info"].get("palaces") is not None
    assert result["confidence"] in ("medium", "low", "high")


def test_qizheng_mock_has_palaces():
    from tools.qizheng.engine import QiZhengAnalyzer

    analyzer = QiZhengAnalyzer()
    result = asyncio.run(
        analyzer.analyze({"bazi": "乙卯 戊寅 庚子 丙子"}, question="")
    )
    bi = result.get("basic_info") or {}
    assert bi.get("life_palace") and bi.get("life_palace") != "待模型分析"
    assert bi.get("twelve_palaces") or result.get("structural")


def test_liunian_years_structure():
    chart = chart_from_birth(
        "乙卯 戊寅 庚子 丙子", gender="male", birth_date="1990-02-15"
    )
    assert chart is not None
    rows = liunian_years(chart, 2024, 2026, birth_year=1990)
    assert len(rows) == 3
    y0 = rows[0]
    assert y0["year"] == 2024
    assert y0["pillar"] and len(y0["pillar"]) == 2
    assert y0["palace_name"]
    assert y0["palace_branch"] == y0["branch"]
    assert "overview" in y0 and "caution" in y0
    assert "si_hua" in y0
    # 流年太岁宫 = 年支对应本命宫
    branch_to_name = {p["branch"]: p["name"] for p in chart["palaces"]}
    assert y0["palace_name"] == branch_to_name[y0["branch"]]


def test_yearly_bundle_default_range():
    bundle = yearly_bundle(
        "乙卯 戊寅 庚子 丙子",
        gender="male",
        birth_date="1990-02-15",
        start_year=2025,
        years=5,
    )
    assert bundle.get("error") is None
    assert bundle["chart"] is not None
    assert bundle["basic_info"]["ming_gong"]
    assert len(bundle["liunian"]) == 5
    assert bundle["start_year"] == 2025
    assert bundle["end_year"] == 2029
    assert bundle["trust"] == "certain_simplified"
    assert "流年" in (bundle.get("note") or "")


def test_server_ziwei_endpoint(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    client = TestClient(build_app(config))
    r = client.post(
        "/api/v1/ziwei/analyze",
        json={"bazi": "乙卯 戊寅 庚子 丙子", "gender": "male", "birth_date": "1990-02-15"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["basic_info"]["ming_gong"]
    assert "palaces" in (body["result"].get("basic_info") or {}) or body[
        "result"
    ].get("structural")


def test_server_ziwei_yearly_endpoint(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    client = TestClient(build_app(config))
    r = client.post(
        "/api/v1/ziwei/yearly",
        json={
            "bazi": "乙卯 戊寅 庚子 丙子",
            "gender": "male",
            "birth_date": "1990-02-15",
            "start_year": 2025,
            "years": 3,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bazi"].startswith("乙卯")
    result = body["result"]
    assert result["error"] is None
    assert len(result["liunian"]) == 3
    assert result["liunian"][0]["year"] == 2025
    assert result["liunian"][0]["palace_name"]
    assert result["trust"] == "certain_simplified"
