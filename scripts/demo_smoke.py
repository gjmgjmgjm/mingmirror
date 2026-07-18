#!/usr/bin/env python3
"""MingMirror demo smoke: validate demo charts + product packages offline.

Usage (repo root):
  python scripts/demo_smoke.py
  python scripts/demo_smoke.py --export-dir ./demo_out
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="MingMirror demo smoke")
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="If set, write package .md/.html for each demo chart",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Liunian span in package appendix (default 5)",
    )
    args = parser.parse_args()

    from tools.destiny.demo_charts import list_demo_charts, demo_chart_as_birth_payload
    from tools.bazi_ai.report_export import build_product_package
    from tools.ziwei.chart import yearly_bundle
    from tools.qizheng.engine import structural_yearly_sync

    charts = list_demo_charts()
    print(f"demo charts: {len(charts)}")
    assert len(charts) >= 3, "expected at least 3 demo charts"

    export_dir: Path | None = args.export_dir
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)

    for demo in charts:
        payload = demo_chart_as_birth_payload(demo)
        bazi = payload["bazi"]
        print(f"\n== {demo['id']} · {demo['label']} ==")
        print(f"   bazi={bazi}  birth={payload['birth_date']} {payload['birth_time']}")

        pkg = build_product_package(
            bazi,
            gender=payload["gender"],
            birth_info={
                "birth_date": payload["birth_date"],
                "birth_time": payload["birth_time"],
                "calendar_type": payload["calendar_type"],
            },
            label=payload["label"],
            include_auspicious=True,
            auspicious_days_n=2,
            liunian_years=args.years,
        )
        assert pkg["markdown"], "empty markdown"
        assert "row-current" in pkg["html"] or "今年" in pkg["markdown"]
        multi = pkg.get("multi_system") or {}
        print(
            f"   package v{pkg['meta'].get('package_version')} "
            f"ziwei_ln={len((multi.get('ziwei') or {}).get('liunian') or [])} "
            f"qz_ln={len((multi.get('qizheng') or {}).get('yearly_analysis') or [])}"
        )

        yb = yearly_bundle(
            bazi,
            gender=payload["gender"],
            birth_date=payload["birth_date"],
            years=3,
        )
        assert yb.get("liunian"), f"ziwei yearly empty for {demo['id']}"

        qy = structural_yearly_sync(
            bazi,
            gender=payload["gender"],
            birth_year=int(payload["birth_date"][:4]),
            years=3,
        )
        assert not qy.get("error"), qy.get("error")
        assert qy.get("yearly_analysis"), f"qizheng yearly empty for {demo['id']}"

        if export_dir is not None:
            stem = export_dir / f"{demo['id']}"
            stem.with_suffix(".md").write_text(pkg["markdown"], encoding="utf-8")
            stem.with_suffix(".html").write_text(pkg["html"], encoding="utf-8")
            print(f"   wrote {stem}.md / .html")

    print("\nOK — all demo charts package + yearly smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
