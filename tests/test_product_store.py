"""Product store: funnel analytics + entitlements."""
from __future__ import annotations


def test_product_store_track_and_funnel(tmp_path):
    from tools.destiny.product_store import ProductStore

    store = ProductStore(tmp_path / "p.db")
    store.track("page_home", device_id="d1")
    store.track("chart_created", device_id="d1", chart_id="c1")
    store.track("package_export", device_id="d1", chart_id="c1")
    summary = store.funnel_summary(since_unix=0)
    assert summary["counts"]["page_home"] >= 1
    assert summary["counts"]["chart_created"] >= 1
    assert summary["rates"]["export_per_chart"] > 0
    store.close()


def test_entitlement_pro_and_credit(tmp_path):
    from tools.destiny.product_store import ProductStore

    store = ProductStore(tmp_path / "p.db")
    free = store.get_entitlement("dev-a").to_dict()
    assert free["plan"] == "free"
    assert free["can_export_package"] is False

    store.add_credits("dev-a", 2)
    assert store.get_entitlement("dev-a").to_dict()["package_credits"] == 2
    ok = store.consume_credit("dev-a")
    assert ok["ok"] is True
    assert ok["entitlement"]["package_credits"] == 1

    pro = store.activate_pro("dev-a", days=7).to_dict()
    assert pro["plan"] == "pro"
    assert pro["can_export_package"] is True
    assert store.consume_credit("dev-a")["ok"] is True  # pro unlimited
    store.close()


def test_server_product_endpoints(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    client = TestClient(app)

    r = client.post(
        "/api/v1/product/track",
        json={"event": "page_home", "device_id": "t-device"},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/product/entitlement", params={"device_id": "t-device"})
    assert r.status_code == 200
    assert r.json()["plan"] == "free"

    r = client.post(
        "/api/v1/product/entitlement/activate",
        json={
            "device_id": "t-device",
            "action": "pro",
            "code": "demo-pro",
            "days": 30,
        },
    )
    assert r.status_code == 200
    assert r.json()["entitlement"]["plan"] == "pro"

    r = client.post(
        "/api/v1/product/entitlement/activate",
        json={"device_id": "t-device", "action": "pro", "code": "wrong"},
    )
    assert r.status_code == 403

    r = client.post(
        "/api/v1/product/entitlement/consume",
        json={"device_id": "t-device"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/api/v1/product/funnel", params={"days": 7})
    assert r.status_code == 200
    assert "counts" in r.json()


def test_payment_webhook_idempotent(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    client = TestClient(app)

    payload = {
        "provider": "demo",
        "external_id": "ord_001",
        "device_id": "pay-device",
        "product": "pro",
        "amount_cents": 9900,
        "status": "succeeded",
        "days": 30,
    }
    r1 = client.post("/api/v1/product/payment/webhook", json=payload)
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["duplicate"] is False
    assert r1.json()["entitlement"]["plan"] == "pro"

    r2 = client.post("/api/v1/product/payment/webhook", json=payload)
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True

    # package credit product
    r3 = client.post(
        "/api/v1/product/payment/webhook",
        json={
            "provider": "demo",
            "external_id": "ord_002",
            "device_id": "pay-device-2",
            "product": "package",
            "credits": 3,
            "status": "paid",
        },
    )
    assert r3.status_code == 200
    assert r3.json()["entitlement"]["package_credits"] >= 3


def test_checkout_closed_loop(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    client = TestClient(build_app(config))

    r = client.post(
        "/api/v1/product/checkout",
        json={
            "device_id": "checkout-dev",
            "product": "pro",
            "amount_cents": 9900,
            "days": 30,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["entitlement"]["plan"] == "pro"
    assert body["payment_id"]
    ext = body["external_id"]

    # status lookup
    r2 = client.get(
        "/api/v1/product/payment/status",
        params={"provider": "demo", "external_id": ext},
    )
    assert r2.status_code == 200
    assert r2.json()["payment"]["external_id"] == ext

    # payments list
    r3 = client.get(
        "/api/v1/product/payments",
        params={"device_id": "checkout-dev"},
    )
    assert r3.status_code == 200
    assert r3.json()["count"] >= 1

    # package checkout
    r4 = client.post(
        "/api/v1/product/checkout",
        json={
            "device_id": "checkout-dev-2",
            "product": "package",
            "credits": 2,
            "amount_cents": 1900,
        },
    )
    assert r4.status_code == 200
    assert r4.json()["entitlement"]["package_credits"] >= 2


def test_admin_grant_and_overview_payments(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    client = TestClient(build_app(config))

    # seed payment for overview
    client.post(
        "/api/v1/product/checkout",
        json={"device_id": "admin-seed", "product": "pro", "amount_cents": 9900},
    )

    r = client.get("/api/v1/admin/overview", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert "payments_summary" in body
    assert body["payments_summary"]["order_count"] >= 1
    assert body["payments_summary"]["revenue_cents"] >= 9900
    assert isinstance(body.get("recent_payments"), list)

    r2 = client.post(
        "/api/v1/admin/entitlement/grant",
        json={"device_id": "grant-dev", "action": "credit", "credits": 5},
    )
    assert r2.status_code == 200
    assert r2.json()["entitlement"]["package_credits"] >= 5

    r3 = client.post(
        "/api/v1/admin/entitlement/grant",
        json={"device_id": "grant-dev", "action": "pro", "days": 7},
    )
    assert r3.status_code == 200
    assert r3.json()["entitlement"]["plan"] == "pro"


def test_store_checkout_and_summary(tmp_path):
    from tools.destiny.product_store import ProductStore

    store = ProductStore(tmp_path / "pay.db")
    out = store.checkout(
        device_id="s1",
        product="pro",
        amount_cents=9900,
        days=14,
    )
    assert out["ok"] and out["entitlement"]["plan"] == "pro"
    summary = store.payment_summary(since_unix=0)
    assert summary["order_count"] >= 1
    assert summary["revenue_cents"] >= 9900
    payments = store.list_payments(device_id="s1")
    assert len(payments) >= 1
    store.close()


def test_admin_overview(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    client = TestClient(app)

    client.post(
        "/api/v1/product/track",
        json={"event": "chart_created", "device_id": "a1"},
    )
    r = client.get("/api/v1/admin/overview", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert "funnel" in body
    assert "recent_events" in body
    assert "charts" in body
