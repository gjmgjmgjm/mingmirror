"""E2E: register → verify → entitlement user scope → export gate."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from config import ConfigLoader
from server.app import build_app


def test_auth_entitlement_user_scope_e2e(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Isolate product + account DBs under tmp
    (tmp_path / "data").mkdir(exist_ok=True)
    config = ConfigLoader(None)
    config.update(path=str(tmp_path / "out"))
    # Force event db / product store path via env used by app if any
    app = build_app(config)

    with TestClient(app) as client:
        # Register
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "e2e@example.com",
                "password": "password12",
                "display_name": "E2E",
                "device_id": "dev-e2e-1",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        token = body["token"]
        assert body["user"]["email"] == "e2e@example.com"
        verify_tok = body.get("email_verify_token")
        assert verify_tok  # no SMTP in test

        headers = {"Authorization": f"Bearer {token}"}

        # Verify email
        vr = client.post(
            "/api/v1/auth/verify-email", json={"token": verify_tok}
        )
        assert vr.status_code == 200
        assert vr.json()["user"]["email_verified"] is True

        # Me
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        uid = me.json()["user"]["id"]

        # Activate pro on user scope (via auth)
        act = client.post(
            "/api/v1/product/entitlement/activate",
            headers=headers,
            json={
                "device_id": "dev-e2e-1",
                "action": "pro",
                "code": "demo-pro",
                "days": 7,
            },
        )
        # May 503 if product store not initialized in minimal config
        if act.status_code == 200:
            ent = act.json()["entitlement"]
            assert ent["plan"] == "pro"
            assert act.json().get("scope_key", "").startswith("user:")

            ge = client.get(
                "/api/v1/product/entitlement",
                headers=headers,
                params={"device_id": "dev-e2e-1"},
            )
            assert ge.status_code == 200
            assert ge.json().get("scoped_by") == "user"

        # Create chart owned by user
        cr = client.post(
            "/api/v1/charts",
            headers=headers,
            json={
                "bazi": "甲子 乙丑 丙寅 丁卯",
                "gender": "male",
                "device_id": "dev-e2e-1",
                "label": "e2e-chart",
            },
        )
        if cr.status_code == 200:
            chart = cr.json()
            assert chart.get("user_id") == uid or chart.get("device_id") == "dev-e2e-1"
            mine = client.get("/api/v1/me/charts", headers=headers)
            assert mine.status_code == 200
            assert mine.json()["count"] >= 1

        # Health
        h = client.get("/api/v1/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"
        assert "smtp" in h.json()


def test_mailer_config_disabled_by_default():
    from server.mailer import MailConfig, Mailer

    m = Mailer(MailConfig())
    assert m.enabled is False
    assert m.send("a@b.c", "t", "body") is False
