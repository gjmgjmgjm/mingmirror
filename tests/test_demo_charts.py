"""Demo chart catalog + package + API smoke."""
from __future__ import annotations

from pathlib import Path

from tools.destiny.demo_charts import (
    demo_chart_as_birth_payload,
    get_demo_chart,
    list_demo_charts,
)


def test_list_demo_charts_shape():
    items = list_demo_charts()
    assert len(items) >= 3
    ids = {c["id"] for c in items}
    assert "demo-gengzi-male" in ids
    for c in items:
        assert c["bazi"] and len(c["bazi"].split()) == 4
        assert c["gender"] in ("male", "female")
        assert c.get("birth_date")
        payload = demo_chart_as_birth_payload(c)
        assert payload["bazi"] == c["bazi"]
        assert payload["label"]


def test_get_demo_chart():
    assert get_demo_chart("nope") is None
    d = get_demo_chart("demo-gengzi-male")
    assert d is not None
    assert "庚子" in d["bazi"] or "庚" in d["bazi"]


def test_demo_package_build():
    from tools.bazi_ai.report_export import build_product_package

    demo = get_demo_chart("demo-gengzi-male")
    assert demo
    p = demo_chart_as_birth_payload(demo)
    pkg = build_product_package(
        p["bazi"],
        gender=p["gender"],
        birth_info={
            "birth_date": p["birth_date"],
            "birth_time": p["birth_time"],
        },
        label=p["label"],
        include_auspicious=False,
        liunian_years=3,
        chart_id="demo:demo-gengzi-male",
    )
    assert pkg["meta"]["package_version"]
    assert "庚" in pkg["markdown"] or p["bazi"] in pkg["markdown"]
    multi = pkg.get("multi_system") or {}
    assert multi.get("ziwei") or multi.get("qizheng")


def test_server_demo_charts_api(tmp_path: Path):
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

    r = client.get("/api/v1/product/demo-charts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 3
    assert body["items"][0]["id"]

    demo_id = body["items"][0]["id"]
    r2 = client.get(f"/api/v1/product/demo-charts/{demo_id}")
    assert r2.status_code == 200
    assert r2.json()["bazi"]

    r3 = client.post(
        f"/api/v1/product/demo-charts/{demo_id}/package",
        json={"liunian_years": 3},
    )
    assert r3.status_code == 200
    pkg = r3.json()
    assert pkg["markdown"]
    assert pkg["html"]
    assert "window.print" in pkg["html"] or "打印" in pkg["html"]

    r4 = client.get("/api/v1/product/demo-charts/not-a-real-id")
    assert r4.status_code == 404
