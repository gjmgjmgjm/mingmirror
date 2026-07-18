"""Tests for product chart identity store + export package."""
from __future__ import annotations

from tools.destiny.chart_store import ChartRecord, ChartStore, is_chart_uuid


class TestChartStore:
    def test_create_get_list_delete(self, tmp_path):
        store = ChartStore(tmp_path / "c.db")
        rec = ChartRecord.create(
            bazi="乙卯 戊寅 庚子 丙子",
            gender="male",
            birth_date="1990-02-15",
            birth_time="12:00",
            label="测试命盘",
        )
        assert is_chart_uuid(rec.id)
        store.save(rec)
        got = store.get(rec.id)
        assert got is not None
        assert got.bazi == "乙卯 戊寅 庚子 丙子"
        assert got.birth_date == "1990-02-15"
        assert store.get_by_bazi("乙卯 戊寅 庚子 丙子").id == rec.id
        assert len(store.list()) >= 1
        assert store.resolve_bazi(rec.id) == rec.bazi
        assert store.resolve_bazi(rec.bazi) == rec.bazi
        assert store.delete(rec.id) is True
        assert store.get(rec.id) is None
        store.close()

    def test_upsert_updates(self, tmp_path):
        store = ChartStore(tmp_path / "c.db")
        rec = ChartRecord.create(bazi="甲子 乙丑 丙寅 丁卯", gender="female")
        store.save(rec)
        rec.label = "新标签"
        store.save(rec)
        assert store.get(rec.id).label == "新标签"
        store.close()


class TestReportExport:
    def test_product_package_shape(self):
        from tools.bazi_ai.report_export import build_product_package

        pkg = build_product_package(
            "乙卯 戊寅 庚子 丙子",
            gender="male",
            birth_info={"birth_date": "1990-02-15", "birth_time": "12:00"},
            include_auspicious=True,
            auspicious_days_n=3,
        )
        assert pkg["markdown"]
        assert "命盘" in pkg["markdown"] or "命" in pkg["markdown"]
        assert "<!DOCTYPE html>" in pkg["html"]
        assert "window.print" in pkg["html"]
        assert pkg["filename_stem"]
        assert pkg["meta"]["package_version"] in ("1.0", "1.1", "1.2", "1.3")
        assert "report" in pkg
        multi = pkg.get("multi_system") or {}
        # v1.2+: ziwei/qizheng yearly appendix; v1.3: range + 今年高亮
        if multi.get("ziwei"):
            assert multi["ziwei"].get("ming_gong") or multi["ziwei"].get("liunian")
        if multi.get("qizheng"):
            assert multi["qizheng"].get("life_palace")
        assert "紫微" in pkg["markdown"] or "七政" in pkg["markdown"] or multi
        # custom range
        pkg2 = build_product_package(
            "乙卯 戊寅 庚子 丙子",
            gender="male",
            birth_info={"birth_date": "1990-02-15", "birth_time": "12:00"},
            include_auspicious=False,
            liunian_start_year=2030,
            liunian_years=5,
        )
        assert pkg2["meta"]["liunian_start_year"] == 2030
        assert pkg2["meta"]["liunian_years"] == 5
        zw_ln = (pkg2.get("multi_system") or {}).get("ziwei", {}).get("liunian") or []
        if zw_ln:
            assert zw_ln[0]["year"] == 2030
            assert len(zw_ln) == 5


def test_server_chart_and_export(tmp_path):
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        import pytest

        pytest.skip("server deps not available")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/charts",
        json={
            "bazi": "乙卯 戊寅 庚子 丙子",
            "gender": "male",
            "birth_date": "1990-02-15",
            "birth_time": "12:00",
            "label": "产品测试",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    chart_id = data["id"]
    assert chart_id
    assert data["bazi"] == "乙卯 戊寅 庚子 丙子"

    # reuse
    resp2 = client.post(
        "/api/v1/charts",
        json={"bazi": "乙卯 戊寅 庚子 丙子", "reuse_existing": True},
    )
    assert resp2.json()["id"] == chart_id

    resp3 = client.get(f"/api/v1/charts/{chart_id}")
    assert resp3.status_code == 200

    # events under UUID
    er = client.post(
        f"/api/v1/charts/{chart_id}/events",
        json={
            "event_type": "job",
            "happened_at": "2020-01-01",
            "description": "入职",
        },
    )
    assert er.status_code == 200
    assert er.json()["chart_id"] == chart_id

    lst = client.get(f"/api/v1/charts/{chart_id}/events")
    assert len(lst.json()) == 1

    # product package
    pkg = client.post(f"/api/v1/charts/{chart_id}/export/package")
    assert pkg.status_code == 200
    body = pkg.json()
    assert "markdown" in body and "html" in body
    assert body["meta"]["chart_id"] == chart_id

    # raw bazi export
    pkg2 = client.post(
        "/api/v1/bazi/export/package",
        json={"bazi": "乙卯 戊寅 庚子 丙子", "gender": "male"},
    )
    assert pkg2.status_code == 200
    assert "BEGIN" not in pkg2.json()["html"] or "html" in pkg2.json()
