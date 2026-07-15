"""Tests for qizheng endpoints in server/app.py."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app


@pytest.fixture
def client(tmp_path: Path):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("", encoding="utf-8")
    knowledge_path = tmp_path / "rule_primer.md"
    knowledge_path.write_text("# 七政四余基础知识", encoding="utf-8")
    download_path = tmp_path / "Downloaded"
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"path: {download_path}\n"
        f"mode: [post]\n"
        f"link: []\n"
        f"bazi_ai:\n"
        f"  cases: {cases_path}\n"
        f"  knowledge_base: {knowledge_path}\n",
        encoding="utf-8",
    )
    config = ConfigLoader(str(config_path))
    app = build_app(config)
    return TestClient(app)


def test_qizheng_yearly_invalid(client):
    resp = client.post("/api/v1/qizheng/yearly", json={"bazi": "不是八字"})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]
    assert data["result"]["yearly_analysis"] == []


def test_qizheng_yearly_valid_mock(client):
    resp = client.post(
        "/api/v1/qizheng/yearly",
        json={
            "bazi": "甲子 丙寅 戊辰 庚午",
            "gender": "male",
            "birth_year": 1984,
            "mode": "10y",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"] == "甲子 丙寅 戊辰 庚午"
    assert data["mode"] == "10y"
    assert data["result"]["dayun_summary"]
    assert len(data["result"]["yearly_analysis"]) == 10
    assert data["result"]["confidence"] == "low"
    assert data["result"].get("_rule_based") is True


def test_qizheng_analyze_with_datetime(client):
    resp = client.post(
        "/api/v1/qizheng/analyze",
        json={
            "birth_datetime": "1990-05-15T08:00:00",
            "latitude": 39.9042,
            "longitude": 116.4074,
            "timezone_offset": 8.0,
            "question": "事业如何",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"]
    assert data["result"]["basic_info"]["chart"] == data["bazi"]
    # Astronomical profile should be present because pyswisseph is installed.
    assert data["result"].get("astro_profile")


def test_qizheng_analyze_with_precession_mode(client):
    resp = client.post(
        "/api/v1/qizheng/analyze",
        json={
            "birth_datetime": "1990-05-15T08:00:00",
            "latitude": 39.9042,
            "longitude": 116.4074,
            "timezone_offset": 8.0,
            "precession_mode": "sidereal_lahiri",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"]
    astro = data["result"].get("astro_profile")
    assert astro
    assert astro["precession_mode"] == "sidereal_lahiri"
    assert astro["precession_offset_degrees"] > 20.0


def test_qizheng_analyze_missing_input(client):
    resp = client.post(
        "/api/v1/qizheng/analyze",
        json={"question": "事业如何"},
    )
    assert resp.status_code == 400


def test_qizheng_analyze_invalid_datetime(client):
    resp = client.post(
        "/api/v1/qizheng/analyze",
        json={
            "birth_datetime": "not-a-datetime",
            "latitude": 39.9042,
            "longitude": 116.4074,
        },
    )
    assert resp.status_code == 400


def test_qizheng_yearly_with_datetime(client):
    resp = client.post(
        "/api/v1/qizheng/yearly",
        json={
            "birth_datetime": "1990-05-15T08:00:00",
            "latitude": 39.9042,
            "longitude": 116.4074,
            "timezone_offset": 8.0,
            "gender": "male",
            "mode": "10y",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"]
    assert data["mode"] == "10y"
    assert data["result"]["dayun_summary"]
    assert len(data["result"]["yearly_analysis"]) == 10


def test_qizheng_yearly_dignity_table_switch(client):
    default_resp = client.post(
        "/api/v1/qizheng/yearly",
        json={
            "bazi": "甲子 丙寅 戊辰 庚午",
            "gender": "male",
            "birth_year": 1984,
            "mode": "10y",
            "dignity_table": "default",
        },
    )
    yang_resp = client.post(
        "/api/v1/qizheng/yearly",
        json={
            "bazi": "甲子 丙寅 戊辰 庚午",
            "gender": "male",
            "birth_year": 1984,
            "mode": "10y",
            "dignity_table": "yang",
        },
    )
    assert default_resp.status_code == 200
    assert yang_resp.status_code == 200
    default = default_resp.json()["result"]["yearly_analysis"]
    yang = yang_resp.json()["result"]["yearly_analysis"]
    diffs = sum(
        1 for d, y in zip(default, yang) if d["star_impact"] != y["star_impact"]
    )
    assert diffs > 0


def test_qizheng_analyze_dignity_table_invalid(client):
    resp = client.post(
        "/api/v1/qizheng/analyze",
        json={
            "bazi": "甲子 丙寅 戊辰 庚午",
            "dignity_table": "unknown",
        },
    )
    assert resp.status_code == 400
