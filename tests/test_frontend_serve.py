"""Tests for the bundled frontend static file serving."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app


@pytest.fixture
def client(tmp_path: Path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "path: ./Downloaded\nmode: [post]\nlink: []\n",
        encoding="utf-8",
    )
    config = ConfigLoader(str(config_path))
    return TestClient(build_app(config))


def test_root_redirects_to_frontend(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/app/"


def test_frontend_index_served(client):
    resp = client.get("/app/index.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "命镜" in resp.text or "MingMirror" in resp.text


def test_frontend_static_assets_linked(client):
    resp = client.get("/app/index.html")
    assert resp.status_code == 200
    # Vite build produces <script type="module" src="/assets/index-*.js">
    assert "<script type=\"module\"" in resp.text
    assert "/assets/index-" in resp.text
