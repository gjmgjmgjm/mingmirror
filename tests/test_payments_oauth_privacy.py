"""Payment adapters + account export/delete + OAuth scaffold."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_normalize_wechat_alipay_stripe():
    from server.payments import normalize_webhook_payload

    wx = normalize_webhook_payload(
        "wechat",
        {
            "resource": {
                "out_trade_no": "wx_ord_1",
                "trade_state": "SUCCESS",
                "amount": {"total": 9900},
                "attach": json.dumps(
                    {"device_id": "d-wx", "product": "pro"}, ensure_ascii=False
                ),
            }
        },
    )
    assert wx["provider"] == "wechat"
    assert wx["external_id"] == "wx_ord_1"
    assert wx["device_id"] == "d-wx"
    assert wx["product"] == "pro"
    assert wx["status"] == "succeeded"
    assert wx["amount_cents"] == 9900

    ali = normalize_webhook_payload(
        "alipay",
        {
            "out_trade_no": "ali_ord_1",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "19.00",
            "passback_params": json.dumps(
                {"device_id": "d-ali", "product": "package"}, ensure_ascii=False
            ),
        },
    )
    assert ali["provider"] == "alipay"
    assert ali["external_id"] == "ali_ord_1"
    assert ali["device_id"] == "d-ali"
    assert ali["product"] == "package"
    assert ali["status"] == "succeeded"
    assert ali["amount_cents"] == 1900

    stripe = normalize_webhook_payload(
        "stripe",
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_1",
                    "payment_status": "paid",
                    "amount_total": 9900,
                    "currency": "usd",
                    "metadata": {"device_id": "d-st", "product": "pro"},
                }
            },
        },
    )
    assert stripe["provider"] == "stripe"
    assert stripe["external_id"] == "cs_test_1"
    assert stripe["device_id"] == "d-st"
    assert stripe["product"] == "pro"
    assert stripe["status"] == "succeeded"


def test_pending_checkout_and_webhook_fulfill(tmp_path: Path):
    from tools.destiny.product_store import ProductStore

    store = ProductStore(tmp_path / "pay.db")
    out = store.checkout(
        device_id="dev-pending",
        product="pro",
        provider="wechat",
        amount_cents=9900,
        days=30,
        external_id="wx_pend_1",
    )
    assert out["mode"] == "pending"
    assert out["status"] == "pending"
    ent_before = store.get_entitlement("dev-pending").to_dict()
    assert ent_before.get("plan") == "free"

    fulfilled = store.fulfill_pending_or_new(
        provider="wechat",
        external_id="wx_pend_1",
        device_id="dev-pending",
        product="pro",
        amount_cents=9900,
        days=30,
        credits=1,
        raw={"trade_state": "SUCCESS"},
    )
    assert fulfilled["ok"] is True
    assert fulfilled["entitlement"]["plan"] == "pro"

    # Idempotent second fulfill
    again = store.fulfill_pending_or_new(
        provider="wechat",
        external_id="wx_pend_1",
        device_id="dev-pending",
        product="pro",
        amount_cents=9900,
        days=30,
    )
    assert again["duplicate"] is True
    store.close()


def test_export_and_delete_user(tmp_path: Path):
    from server.accounts import AccountStore

    store = AccountStore(tmp_path / "acc.db")
    user, sess = store.register(
        "privacy@example.com", "password12", display_name="隐", device_id="d1"
    )
    export = store.export_user_data(user.id)
    assert export["user"]["email"] == "privacy@example.com"
    assert "d1" in export["devices"]
    assert "password_hash" not in str(export["user"])
    assert export["entitlement_scope"] == f"user:{user.id}"

    store.delete_user(user.id, password="password12")
    assert store.get_user(user.id) is None
    assert store.get_user_by_token(sess.token) is None
    store.close()


def test_oauth_authorize_and_stub_exchange(tmp_path: Path, monkeypatch):
    from server.accounts import AccountStore
    from server.oauth import build_authorize_url, exchange_code_stub

    info = build_authorize_url("wechat", state="st1")
    assert "open.weixin.qq.com" in info["authorize_url"]
    assert info["state"] == "st1"
    assert info["ready"] is False  # no keys in test env

    apple = build_authorize_url("apple")
    assert "appleid.apple.com" in apple["authorize_url"]

    monkeypatch.setenv("MINGMIRROR_OAUTH_STUB", "1")
    profile = exchange_code_stub("wechat", "code_abc_xyz")
    assert profile["provider"] == "wechat"
    assert profile["provider_user_id"].startswith("wx_stub_")

    store = AccountStore(tmp_path / "oauth.db")
    user, sess = store.upsert_oauth_identity(
        provider=profile["provider"],
        provider_user_id=profile["provider_user_id"],
        email=profile.get("email") or "",
        display_name=profile.get("display_name") or "",
        device_id="oauth-dev",
    )
    assert user.email.endswith("@oauth.local")
    assert sess.token
    # Second login same identity
    u2, s2 = store.upsert_oauth_identity(
        provider=profile["provider"],
        provider_user_id=profile["provider_user_id"],
        device_id="oauth-dev-2",
    )
    assert u2.id == user.id
    assert s2.token != sess.token
    store.close()


def test_http_privacy_and_oauth_and_provider_webhook(tmp_path: Path, monkeypatch):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        pytest.skip("server deps")

    monkeypatch.setenv("MINGMIRROR_OAUTH_STUB", "1")
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    client = TestClient(build_app(config))

    # register → export → delete
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "http-priv@example.com",
            "password": "password12",
            "display_name": "H",
            "device_id": "http-dev",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    exp = client.get("/api/v1/auth/export-data", headers=headers)
    assert exp.status_code == 200
    assert exp.json()["data"]["user"]["email"] == "http-priv@example.com"

    # OAuth authorize scaffold
    oa = client.get("/api/v1/auth/oauth/wechat")
    assert oa.status_code == 200
    assert "authorize_url" in oa.json()

    # OAuth stub exchange
    ox = client.post(
        "/api/v1/auth/oauth/wechat/exchange",
        json={"code": "testcode12345", "device_id": "oauth-http"},
    )
    assert ox.status_code == 200
    assert ox.json()["token"]
    assert ox.json()["user"]["email"].endswith("@oauth.local")

    # Provider-path wechat webhook (canonical attach fields via normalize)
    wx_body = {
        "resource": {
            "out_trade_no": "http_wx_1",
            "trade_state": "SUCCESS",
            "amount": {"total": 1900},
            "attach": json.dumps(
                {"device_id": "wx-http-dev", "product": "package"}, ensure_ascii=False
            ),
            "days": 30,
            "credits": 2,
        }
    }
    wh = client.post("/api/v1/product/payment/webhook/wechat", json=wx_body)
    assert wh.status_code == 200, wh.text
    body = wh.json()
    assert body["ok"] is True
    assert body["entitlement"]["package_credits"] >= 2

    # delete original email account
    dele = client.post(
        "/api/v1/auth/delete-account",
        headers=headers,
        json={"password": "password12", "confirm": "DELETE"},
    )
    assert dele.status_code == 200
    assert dele.json()["deleted"] is True
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401
