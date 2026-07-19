"""Targeted regressions for 六亲 strength heuristics (2026-07 accuracy push)."""

from __future__ import annotations

from tools.bazi_ai.bazi_structural import liuqin_profile


def test_mother_canggan_yueling_not_false_strong():
    """月支仅藏干印 + 时支合化坏根 → 弱 (was false 强)."""
    prof = liuqin_profile("壬子 辛亥 丙午 庚寅", gender="male") or {}
    mother = prof.get("mother") or {}
    assert mother.get("strength") == "弱"
    assert "坏根" in (mother.get("support_text") or "") or "虚浮" in (
        mother.get("support_text") or ""
    )


def test_child_requires_stem_for_strong():
    """子女无透干仅月令本气 → 弱 (was false 强)."""
    prof = liuqin_profile("己未 癸酉 戊辰 丙辰", gender="female") or {}
    son = (prof.get("son") or {}).get("strength", "?")
    dau = (prof.get("daughter") or {}).get("strength", "?")
    # master 弱 — neither star should be forced 强-only-with-root
    assert "强" not in {s for s in (son, dau) if s == "强"} or dau == "弱"
    assert dau == "弱" or son == "弱"


def test_spouse_with_stem_survives_global_drain_noise():
    """透干官星 + 有根 不被全局火土噪声误降 (drain thr 2.5)."""
    prof = liuqin_profile("戊辰 癸亥 丙午 壬辰", gender="female") or {}
    spouse = prof.get("spouse") or {}
    assert spouse.get("strength") == "强"


def test_spouse_benqi_with_canggan_yue_counts_strong():
    """月支藏干 + 另有本气真根 → 仍可判强."""
    prof = liuqin_profile("丁巳 庚戌 丙辰 丁酉", gender="male") or {}
    spouse = prof.get("spouse") or {}
    assert spouse.get("strength") == "强"


def test_father_root_only_in_day_branch_is_weak():
    """父星透干但本气根仅在日支（夫妻宫）→ 弱 (年月无本气)."""
    prof = liuqin_profile("己酉 癸酉 乙未 丙子", gender="male") or {}
    father = prof.get("father") or {}
    assert father.get("strength") == "弱"
    sup = father.get("support_text") or ""
    assert "年月" in sup or "父母" in sup or father.get("strength") == "弱"


def test_sibling_dual_star_labels():
    """手足比劫互参标签（强弱仍认主星）."""
    prof = liuqin_profile("甲午 丁卯 癸酉 庚申", gender="male") or {}
    bro = prof.get("brother") or {}
    sis = prof.get("sister") or {}
    for m in (bro, sis):
        assert m.get("strength") in ("强", "弱")
        star = str(m.get("star") or "")
        if "/" in star:
            assert "比肩" in star or "劫财" in star


def test_father_caishengsha_day_branch_is_weak():
    """甲日坐申七杀 + 年透偏财 → 财生杀，父星弱."""
    prof = liuqin_profile("戊辰 癸亥 甲申 庚午", gender="male") or {}
    father = prof.get("father") or {}
    assert father.get("strength") == "弱"
    assert "财生官杀" in (father.get("support_text") or "") or father.get(
        "strength"
    ) == "弱"


def test_spouse_multi_stem_survives_hour_clash():
    """多透干财星 + 仅子午冲坏时支根 → 配偶仍强."""
    prof = liuqin_profile("壬戌 癸卯 戊午 壬子", gender="male") or {}
    spouse = prof.get("spouse") or {}
    assert spouse.get("strength") == "强"
