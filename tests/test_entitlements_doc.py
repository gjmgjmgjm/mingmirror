"""Smoke: product package still builds (entitlements are frontend-only)."""
from tools.bazi_ai.report_export import build_product_package


def test_package_for_dashboard_export():
    pkg = build_product_package(
        "乙卯 戊寅 庚子 丙子",
        gender="male",
        birth_info={"birth_date": "1990-02-15", "birth_time": "12:00"},
        include_auspicious=True,
        auspicious_days_n=2,
        chart_id="demo-id",
        label="演示命盘",
    )
    assert "打印" in pkg["html"] or "print" in pkg["html"]
    assert pkg["meta"]["label"] == "演示命盘"
    assert pkg["markdown"]
    multi = pkg.get("multi_system") or {}
    # Yearly structural appendix (package v1.2+)
    if multi.get("ziwei") and multi["ziwei"].get("liunian"):
        assert len(multi["ziwei"]["liunian"]) >= 5
        assert "流年" in pkg["markdown"] or "太岁" in pkg["markdown"]
    if multi.get("qizheng") and multi["qizheng"].get("yearly_analysis"):
        assert len(multi["qizheng"]["yearly_analysis"]) >= 5
    # v1.3: current-year highlight class in HTML when table has 今年
    from datetime import date

    today = date.today().year
    pkg_now = build_product_package(
        "乙卯 戊寅 庚子 丙子",
        gender="male",
        birth_info={"birth_date": "1990-02-15"},
        include_auspicious=False,
        liunian_start_year=today,
        liunian_years=3,
    )
    assert "今年" in pkg_now["markdown"]
    assert "row-current" in pkg_now["html"] or "今年" in pkg_now["html"]
