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
