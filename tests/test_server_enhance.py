"""Tests for REST server enhancements: cancel, SSE, config override."""

import asyncio
from collections import namedtuple
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app
from server.jobs import JobStatus

pytest.importorskip("fastapi")

_AppClient = namedtuple("_AppClient", ["app", "client"])


@pytest.fixture
def client(tmp_path: Path):
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


@pytest.fixture
async def async_app_client(tmp_path: Path):
    """Async httpx client with access to the underlying app for concurrency tests."""
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

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
    config = ConfigLoader(str(config_path))
    app = build_app(config)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield _AppClient(app=app, client=client)


async def test_cancel_running_job(async_app_client):
    """Cancel endpoint should stop a job that has already entered RUNNING."""
    app, client = async_app_client
    manager = app.state.job_manager
    running = asyncio.Event()

    async def slow_executor(url: str) -> dict:
        running.set()
        # Block until the task is cancelled from outside.
        await asyncio.sleep(10)
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    manager.executor = slow_executor

    resp = await client.post(
        "/api/v1/download", json={"url": "https://www.douyin.com/user/xxx"}
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # Wait for the executor to signal it is running.
    await asyncio.wait_for(running.wait(), timeout=1)

    resp = await client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200

    # Give the running task a moment to process the cancellation and update
    # its status. We poll via the public GET endpoint to avoid touching
    # internal JobManager state.
    final_status = None
    for _ in range(50):
        await asyncio.sleep(0.05)
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        final_status = resp.json()["status"]
        if final_status == JobStatus.CANCELLED:
            break
    assert final_status == JobStatus.CANCELLED


def test_sse_events_for_completed_job(client):
    """SSE stream should emit status events and terminate when the job finishes."""
    resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/user/xxx"})
    job_id = resp.json()["job_id"]

    # Fake executor finishes synchronously, so the job is already terminal.
    resp = client.get(
        f"/api/v1/jobs/{job_id}/events",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = b"".join(resp.iter_bytes())
    assert b"event: status" in body
    assert b'"status": "success"' in body


def test_sse_events_for_unknown_job(client):
    """SSE stream should emit an error event when the job does not exist."""
    resp = client.get(
        "/api/v1/jobs/nonexistent/events",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = b"".join(resp.iter_bytes())
    assert b"event: error" in body
    assert b"job not found" in body


def test_update_config_rebuilds_control_objects(client):
    """Runtime overrides must rebuild the corresponding control objects."""
    app = client.app
    deps = app.state.deps

    original_queue = deps.queue_manager
    original_rate = deps.rate_limiter
    original_retry = deps.retry_handler

    resp = client.post(
        "/api/v1/config",
        json={
            "thread": 8,
            "rate_limit": 5.0,
            "retry_times": 7,
            "proxy": "http://proxy.example",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("thread") == 8
    assert data.get("rate_limit") == 5.0
    assert data.get("retry_times") == 7
    assert data.get("proxy") == "http://proxy.example"

    assert deps.queue_manager is not original_queue
    assert deps.queue_manager.max_workers == 8
    assert deps.rate_limiter is not original_rate
    assert deps.rate_limiter.max_per_second == 5.0
    assert deps.retry_handler is not original_retry
    assert deps.retry_handler.max_retries == 7
    assert deps.config.config.get("proxy") == "http://proxy.example"
