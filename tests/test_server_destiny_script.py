"""Tests for the Destiny Script REST endpoint."""

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app


def test_destiny_script_endpoint(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/destiny/script",
            json={
                "bazi": "庚午 辛巳 庚辰 壬午",
                "gender": "male",
                "birth_datetime": "1990-05-20T10:00:00",
                "birth_year": 1990,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "character_card" in data
        assert "chapters" in data
        assert "opening" in data
        assert "closing" in data
        assert data["character_card"].get("talents")
        assert data["character_card"].get("weaknesses")
        assert isinstance(data["chapters"], list)
