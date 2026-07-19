"""API-level smoke for /bazi/year-timing (no LLM)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app


def test_year_timing_endpoint_parent_death(tmp_path):
    config_path = tmp_path / "config.yml"
    download_path = tmp_path / "Downloaded"
    config_path.write_text(
        f"path: {download_path}\n"
        "mode: [post]\n"
        "link: []\n"
        "thread: 5\n"
        "rate_limit: 2\n"
        "retry_times: 3\n",
        encoding="utf-8",
    )
    app = build_app(ConfigLoader(str(config_path)))
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/bazi/year-timing",
            json={
                "bazi": "甲午 丁卯 癸酉 庚申",
                "question": "命主父亲于哪年去世?",
                "options": [
                    "A 1959 己亥年",
                    "B 1963 癸卯年",
                    "C 1964 甲辰年",
                    "D 1969 己酉年",
                ],
                "gender": "male",
                "birth_date": "1954-03-18",
                "birth_time": "15:00",
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    yts = data["year_timing_surface"]
    assert yts["assert_single_year"] is False
    assert yts["display_mode"] in ("hard_shortlist", "soft_hint", "trend_only")
    if yts["display_mode"] in ("hard_shortlist", "soft_hint"):
        assert len(yts.get("candidates") or []) >= 1
