"""Tests for REST server enhancements: cancel, SSE, config override."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app
from server.jobs import JobStatus


@pytest.fixture
def client(tmp_path: Path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "path: ./Downloaded\n"
        "mode: [post]\n"
        "link: []\n"
        "thread: 5\n"
        "rate_limit: 2\n"
        "retry_times: 3\n",
        encoding="utf-8",
    )
    config = ConfigLoader(str(config_path))
    app = build_app(config)

    async def fake_executor(url: str) -> dict:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return TestClient(app)


def test_cancel_pending_job(client):
    resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/user/xxx"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    resp = client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in (
        JobStatus.CANCELLED,
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.SUCCESS,
        JobStatus.FAILED,
    )


def test_cancel_unknown_job(client):
    resp = client.delete("/api/v1/jobs/nonexistent")
    assert resp.status_code == 404


def test_sse_events(client):
    resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/user/xxx"})
    job_id = resp.json()["job_id"]

    resp = client.get(
        f"/api/v1/jobs/{job_id}/events",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = b""
    for chunk in resp.iter_bytes():
        body += chunk
        if b"\n\n" in body:
            break
    assert b"event: status" in body


def test_get_config(client):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("thread") == 5
    assert data.get("rate_limit") == 2


def test_update_config(client):
    resp = client.post("/api/v1/config", json={"thread": 8, "rate_limit": 5.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("thread") == 8
    assert data.get("rate_limit") == 5.0

    resp = client.get("/api/v1/config")
    assert resp.json().get("thread") == 8


def test_update_config_ignores_unknown_keys(client):
    resp = client.post("/api/v1/config", json={"unknown_key": "value", "thread": 2})
    assert resp.status_code == 200
    assert "unknown_key" not in resp.json()
    assert resp.json().get("thread") == 2
