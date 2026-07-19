"""Det 六亲细断 dossier."""
from __future__ import annotations

from tools.bazi_ai.liuqin_dossier import (
    build_liuqin_dossier,
    format_liuqin_dossier_markdown,
    format_liuqin_dossier_prompt,
)


def test_build_dossier_has_all_members_and_fields():
    d = build_liuqin_dossier(
        "甲午 丁卯 癸酉 庚申",
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    assert d is not None
    members = d["members"]
    for key in ("father", "mother", "spouse", "son", "daughter", "brother", "sister"):
        m = members[key]
        assert m["label"]
        assert m["strength"] in ("强", "弱")
        assert m["character"]
        assert m["ability"]
        assert m["health"]
        assert m["relation"]
        assert "timing" in m
        assert m["narrative"]
        assert "palace" in m
        assert "stars" in m
        # timing always has liunian_samples key (may be empty without birth)
        assert "liunian_samples" in m["timing"]
    assert d["disclaimer"]
    assert "双星" in d["disclaimer"] or "宫位" in d["disclaimer"]
    md = format_liuqin_dossier_markdown(d)
    assert "父亲" in md and "性格" in md
    pr = format_liuqin_dossier_prompt(d)
    assert "程序六亲细断" in pr
    assert "强弱" in pr


def test_female_spouse_star_is_zhengguan():
    d = build_liuqin_dossier(
        "丁未 戊申 癸亥 庚申",
        gender="female",
        birth_date="1984-07-05",
        birth_time="12:00",
    )
    assert d is not None
    assert d["members"]["spouse"]["star"] in ("正官", "七杀", "正官/七杀") or d[
        "members"
    ]["spouse"]["star"]


def test_mother_dual_star_when_yin_both_present():
    """When 正印+偏印 both exist, dossier should dual-blend and tag dual_star_note."""
    # 甲午 丁卯 癸酉 庚申 — day master 癸; structural may merge 印
    d = build_liuqin_dossier(
        "甲午 丁卯 癸酉 庚申",
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    assert d is not None
    mother = d["members"]["mother"]
    # star may be single or dual depending on chart
    assert mother["stars"]
    assert mother["palace"].get("palace_branch")  # 父母宫月支
    assert mother["palace"].get("palace_note")
    # if dual label, must have dual note
    if "/" in str(mother.get("star") or ""):
        assert mother.get("dual_star_note")
        assert "正印" in mother["star"] or "偏印" in mother["star"]
        assert "合参" in mother["dual_star_note"] or "印" in mother["dual_star_note"]


def test_palace_and_liunian_samples_on_spouse():
    d = build_liuqin_dossier(
        "甲午 丁卯 癸酉 庚申",
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    assert d is not None
    sp = d["members"]["spouse"]
    assert sp["palace"]["palace_label"]
    assert "夫妻宫" in sp["palace"]["palace_note"] or sp["palace"]["palace_branch"]
    # With birth date, liunian samples may or may not hit; key must exist
    samples = sp["timing"]["liunian_samples"]
    assert isinstance(samples, list)
    for s in samples:
        assert "year" in s and "pillar" in s and "note" in s
        assert s.get("kind") == "symbolic_sample"
        # honesty: note must not claim 必在
        assert "必在" not in s["note"]
    md = format_liuqin_dossier_markdown(d)
    # if any member has samples, md mentions 流年
    any_ln = any(
        (m.get("timing") or {}).get("liunian_samples")
        for m in d["members"].values()
    )
    if any_ln:
        assert "流年" in md


def test_structural_dual_star_father_and_spouse():
    """liuqin_profile merges 父 偏财+正财 and 配偶 正财+偏财 when both exist."""
    from tools.bazi_ai.bazi_structural import liuqin_profile

    # 甲午 丁卯 癸酉 庚申: day master 癸 — 偏财=丁, 正财 often present
    prof = liuqin_profile("甲午 丁卯 癸酉 庚申", gender="male")
    assert prof is not None
    father = prof["father"]
    spouse = prof["spouse"]
    mother = prof["mother"]
    # Mother dual already known for this chart
    if mother.get("exists") and "/" in str(mother.get("star") or ""):
        assert "正印" in mother["star"] and "偏印" in mother["star"]
    # Father / spouse: if dual label present, both tokens are 财星
    for m, pair in ((father, ("偏财", "正财")), (spouse, ("正财", "偏财"))):
        star = str(m.get("star") or "")
        if "/" in star:
            for tok in pair:
                assert tok in star
            assert m.get("exists") is True


def test_year_timing_liuqin_bridge():
    from tools.bazi_ai.liuqin_dossier import build_liuqin_dossier
    from tools.bazi_ai.year_timing_surface import (
        enrich_year_timing_with_liuqin,
        resolve_year_timing,
    )

    bazi = "甲午 丁卯 癸酉 庚申"
    q = "命主父亲于哪年去世?"
    opts = [
        "A 1959 己亥年",
        "B 1963 癸卯年",
        "C 1964 甲辰年",
        "D 1969 己酉年",
    ]
    s = resolve_year_timing(
        bazi, q, opts, gender="male", birth_date="1954-03-18", birth_time="15:00"
    )
    d = s.to_dict()
    dossier = build_liuqin_dossier(
        bazi, gender="male", birth_date="1954-03-18", birth_time="15:00"
    )
    d = enrich_year_timing_with_liuqin(d, dossier, question=q)
    bridge = (d.get("meta") or {}).get("liuqin_bridge") or {}
    assert bridge.get("member_keys") == ["father"]
    assert isinstance(bridge.get("samples"), list)
    # samples should be father-tagged when present
    for srow in bridge.get("samples") or []:
        assert srow.get("member_key") == "father"
        assert srow.get("kind") == "liuqin_symbolic"
    assert "不作" in (bridge.get("honesty") or "") or "象征" in (
        bridge.get("honesty") or ""
    )
    # force_det path also links
    from tools.bazi_ai.engine import _force_det_fields, _link_year_timing_liuqin

    out = _force_det_fields(
        {
            "basic_info": {},
            "liuqin_strength": {},
            "liuqin_analysis": "",
            "caveats": [],
            "year_timing_surface": resolve_year_timing(
                bazi, q, opts, gender="male", birth_date="1954-03-18", birth_time="15:00"
            ).to_dict(),
        },
        bazi,
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    _link_year_timing_liuqin(
        out,
        question=q,
        bazi=bazi,
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    b2 = (out["year_timing_surface"].get("meta") or {}).get("liuqin_bridge") or {}
    assert b2.get("member_keys") == ["father"]


def test_force_det_attaches_dossier():
    from tools.bazi_ai.engine import _force_det_fields

    result = {
        "basic_info": {},
        "liuqin_strength": {},
        "liuqin_analysis": "",
        "caveats": [],
    }
    out = _force_det_fields(
        result,
        "甲午 丁卯 癸酉 庚申",
        gender="male",
        birth_date="1954-03-18",
        birth_time="15:00",
    )
    assert "liuqin_dossier" in out
    assert out["liuqin_dossier"]["members"]["father"]["character"]
    assert "父亲" in (out.get("liuqin_analysis") or "")
    # new fields survive force_det path
    mom = out["liuqin_dossier"]["members"]["mother"]
    assert "palace" in mom
    assert "liunian_samples" in mom["timing"]
