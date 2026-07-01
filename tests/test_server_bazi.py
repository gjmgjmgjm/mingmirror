"""Tests for bazi endpoints in server/app.py."""

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
    knowledge_path.write_text("# 基础知识", encoding="utf-8")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"path: ./Downloaded\n"
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


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_bazi_invalid(client):
    resp = client.post("/api/v1/bazi/analyze", json={"bazi": "不是八字"})
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]


def test_analyze_bazi_valid_mock(client):
    resp = client.post(
        "/api/v1/bazi/analyze",
        json={"bazi": "乙卯 戊寅 庚子 丙子", "question": "事业"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bazi"] == "乙卯 戊寅 庚子 丙子"
    assert "basic_info" in data["result"]


def test_list_bazi_cases_empty(client):
    resp = client.get("/api/v1/bazi/cases")
    assert resp.status_code == 200
    assert resp.json()["cases"] == []


def test_bazi_feedback(client, tmp_path: Path):
    resp = client.post(
        "/api/v1/bazi/feedback",
        json={"bazi": "乙卯 戊寅 庚子 丙子", "correct": True, "note": "准"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
