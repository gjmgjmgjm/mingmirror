"""Tests for dual-chart 合婚 engine."""
from __future__ import annotations

from tools.bazi_ai.hehun import compare_charts


class TestCompareCharts:
    def test_basic_shape(self):
        r = compare_charts(
            "乙卯 戊寅 庚子 丙子",
            "male",
            "甲子 丙寅 戊辰 壬子",
            "female",
        )
        assert "error" not in r
        assert 0 <= r["score"] <= 100
        assert r["level"]
        assert len(r["dimensions"]) == 5
        for d in r["dimensions"]:
            assert 0 <= d["score"] <= 100
            assert d["label"]
        assert "profiles" in r
        assert r["profiles"]["a"]["day_master"] == "庚"
        assert r["profiles"]["b"]["day_master"] == "戊"

    def test_invalid_bazi(self):
        r = compare_charts("不是八字", "male", "甲子 丙寅 戊辰 壬子", "female")
        assert r.get("error")
        assert r["score"] == 0

    def test_same_chart_self(self):
        bazi = "乙卯 戊寅 庚子 丙子"
        r = compare_charts(bazi, "male", bazi, "male")
        assert 0 <= r["score"] <= 100
        # 同气比和至少不应崩溃
        assert any(d["key"] == "day_stem" for d in r["dimensions"])

    def test_gender_normalization(self):
        r = compare_charts(
            "乙卯 戊寅 庚子 丙子",
            "男",
            "甲子 丙寅 戊辰 壬子",
            "女",
        )
        assert r["profiles"]["a"]["gender"] == "male"
        assert r["profiles"]["b"]["gender"] == "female"

    def test_supports_or_conflicts_lists(self):
        r = compare_charts(
            "乙卯 戊寅 庚子 丙子",
            "male",
            "甲子 丙寅 戊辰 壬子",
            "female",
        )
        assert isinstance(r["supports"], list)
        assert isinstance(r["conflicts"], list)
        assert r["trust"] == "certain"

    def test_reading_layer(self):
        r = compare_charts(
            "乙卯 戊寅 庚子 丙子",
            "male",
            "甲子 丙寅 戊辰 壬子",
            "female",
        )
        reading = r["reading"]
        assert reading["sections"]
        assert reading["advice"]
        assert "合婚解读" in reading["markdown"]
        assert any(s["id"] == "overview" for s in reading["sections"])


def test_joint_auspicious_days():
    from datetime import date, timedelta

    from tools.bazi_ai.hehun import joint_auspicious_days

    d0 = date(2026, 7, 16)
    joint = joint_auspicious_days(
        "乙卯 戊寅 庚子 丙子",
        "male",
        "甲子 丙寅 戊辰 壬子",
        "female",
        event_type="marriage",
        date_from=d0,
        date_to=d0 + timedelta(days=30),
        top_n=5,
    )
    assert not joint.get("error")
    assert len(joint["top"]) <= 5
    assert len(joint["days"]) >= 1
    for day in joint["top"]:
        assert "score_a" in day and "score_b" in day
        assert 0 <= day["score"] <= 100


def test_compare_with_joint_and_ics():
    from datetime import date, timedelta

    r = compare_charts(
        "乙卯 戊寅 庚子 丙子",
        "male",
        "甲子 丙寅 戊辰 壬子",
        "female",
        include_joint_days=True,
        include_ics=True,
        date_from=date(2026, 7, 16),
        date_to=date(2026, 7, 16) + timedelta(days=20),
        top_n=3,
    )
    assert r["joint_top"]
    assert "BEGIN:VCALENDAR" in (r.get("ics") or "")


def test_server_compatibility_endpoint():
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest
        pytest.skip("server deps not available")

    app = build_app(ConfigLoader())
    client = TestClient(app)
    resp = client.post(
        "/api/v1/bazi/compatibility",
        json={
            "bazi_a": "乙卯 戊寅 庚子 丙子",
            "gender_a": "male",
            "bazi_b": "甲子 丙寅 戊辰 壬子",
            "gender_b": "female",
            "include_joint_days": True,
            "include_ics": True,
            "top_n": 3,
            "date_from": "2026-07-16",
            "date_to": "2026-08-05",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert len(data["dimensions"]) == 5
    assert data.get("joint_top")
    assert "BEGIN:VCALENDAR" in (data.get("ics") or "")
