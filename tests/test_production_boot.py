"""Production boot guards: missing secrets must refuse to start."""

from __future__ import annotations

import os

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "MINGMIRROR_ENV",
        "ENV",
        "MINGMIRROR_ADMIN_TOKEN",
        "MINGMIRROR_WEBHOOK_SECRET",
        "MINGMIRROR_ALLOW_INSECURE_BOOT",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_production_boot_refuses_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGMIRROR_ENV", "production")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    with pytest.raises(RuntimeError, match="Production boot refused"):
        build_app(config)


def test_production_boot_refuses_with_only_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGMIRROR_ENV", "production")
    monkeypatch.setenv("MINGMIRROR_ADMIN_TOKEN", "admin-only")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    with pytest.raises(RuntimeError, match="MINGMIRROR_WEBHOOK_SECRET"):
        build_app(config)


def test_production_boot_ok_with_both_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGMIRROR_ENV", "production")
    monkeypatch.setenv("MINGMIRROR_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("MINGMIRROR_WEBHOOK_SECRET", "hook-secret")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    with TestClient(app) as client:
        # Admin without token → 401
        r = client.get("/api/v1/admin/overview")
        assert r.status_code == 401
        # Admin with token → ok (or 200 with payload)
        r2 = client.get(
            "/api/v1/admin/overview",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert r2.status_code == 200


def test_insecure_boot_escape_hatch(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGMIRROR_ENV", "staging")
    monkeypatch.setenv("MINGMIRROR_ALLOW_INSECURE_BOOT", "1")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    with TestClient(app) as client:
        # Still gated at runtime when token unset
        r = client.get("/api/v1/admin/overview")
        assert r.status_code == 503


def test_development_boot_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGMIRROR_ENV", "development")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
        # health may be /health or /api/v1/health depending on routes
        if r.status_code == 404:
            r = client.get("/health")
        assert r.status_code in (200, 404)
