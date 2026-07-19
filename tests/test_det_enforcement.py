"""Det field enforcement: model freestyle cannot override 用神/六亲强弱."""

from __future__ import annotations

from tools.bazi_ai.engine import _force_det_fields, _validate_output
from tools.bazi_ai.bazi_structural import liuqin_profile, structural_profile


def test_force_det_overwrites_wrong_liuqin_strength():
    bazi = "壬子 辛亥 丙午 庚寅"
    liuqin = liuqin_profile(bazi, gender="male") or {}
    structural = structural_profile(bazi) or {}
    fake = {
        "basic_info": {
            "bazi": bazi,
            "useful_gods": ["乱填用神"],
            "taboo_gods": ["乱填忌神"],
        },
        "liuqin_strength": {
            "father": "强",
            "mother": "强",  # det says 弱 after 2026-07 fix
            "spouse": "强",
            "son": "强",
            "daughter": "强",
            "brother": "强",
            "sister": "强",
        },
        "liuqin_analysis": "模型乱写母亲极强。",
        "caveats": [],
    }
    out = _force_det_fields(
        fake,
        bazi,
        liuqin_facts=liuqin,
        structural_facts=structural,
        gender="male",
    )
    assert out["liuqin_strength"]["mother"] == (liuqin.get("mother") or {}).get(
        "strength"
    )
    assert out["liuqin_strength"]["mother"] in ("强", "弱")
    # useful gods overwritten when structural has them
    if structural.get("useful_gods"):
        assert out["basic_info"]["useful_gods"] != ["乱填用神"]
    assert out.get("_det_enforced", {}).get("liuqin_strength") is True
    assert "【程序六亲强弱" in (out.get("liuqin_analysis") or "")


def test_validate_output_enforces_det():
    bazi = "甲子 丙寅 戊辰 庚午"
    result = {
        "basic_info": {"bazi": bazi, "day_master": "错", "month_branch": "错"},
        "liuqin_strength": {"father": "??"},
        "domain_analysis": {"career": "ok"},
        "caveats": [],
    }
    out = _validate_output(result, bazi, gender="male")
    assert out["basic_info"]["day_master"] == "戊"
    assert out["liuqin_strength"]["father"] in ("强", "弱")
    assert out.get("_det_enforced")
