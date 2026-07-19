#!/usr/bin/env python3
"""Detailed deterministic 六亲 dossiers (性格 / 能力 / 健康 / 关系 / 应期).

Built purely from chart structure + 大运/流年 symbols — no LLM.  Product copy must
still treat *timing* as trend/candidates, not prophecy (see capability-boundary).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.bazi_ai.bazi_structural import (
    _LIUQIN_STARS,
    _star_element,
    liuqin_profile,
    shishen_for_branch_main,
    shishen_for_stem,
    structural_profile,
)
from tools.bazi_ai.calendar import dayun_list, liunian_list

# 十神 → 性格 / 能力 / 相处气质（传统子平取象，偏稳健表述）
_SHISHEN_TRAIT: Dict[str, Dict[str, str]] = {
    "比肩": {
        "character": "独立、有主见，重义气，有时固执争强",
        "ability": "自力更生、同辈协作，适合并肩打拼",
        "relation": "与命主多呈平辈相扶或相争之象",
    },
    "劫财": {
        "character": "豪爽、敢为，喜争夺资源，情绪起伏可偏大",
        "ability": "开拓、争利、临场决断力强",
        "relation": "与命主亲近亦易有资源/意见冲突",
    },
    "食神": {
        "character": "温和、乐观，重口福与表达，少极端",
        "ability": "技艺、创意、服务与口才",
        "relation": "对命主多泄秀生财，相处偏轻松",
    },
    "伤官": {
        "character": "聪明敏感、表现欲强，不喜拘束",
        "ability": "技艺突破、批判创新、表达与设计",
        "relation": "与命主缘深但易口舌是非，需边界",
    },
    "正财": {
        "character": "务实、节俭、重承诺与稳定",
        "ability": "理财、经营、踏实办事",
        "relation": "对命主多呈妻财助力或经济纽带",
    },
    "偏财": {
        "character": "灵活、善交际，重面子与机会",
        "ability": "偏财机遇、人脉、商业嗅觉",
        "relation": "与命主缘份起伏，助力偏外缘",
    },
    "正官": {
        "character": "正直、守规矩，有责任感与形象意识",
        "ability": "管理、体制内稳定岗位、名誉",
        "relation": "对命主约束与成就并见，宜以礼相待",
    },
    "七杀": {
        "character": "魄力、急躁、主见强，压力下更显锋芒",
        "ability": "开拓、军警法务类魄力、竞争场",
        "relation": "与命主张力大，助力亦易成压力",
    },
    "正印": {
        "character": "慈祥护佑、文静含蓄，重教养",
        "ability": "学问、贵人提携、文书印信",
        "relation": "对命主多生扶庇护，缘深则稳",
    },
    "偏印": {
        "character": "聪慧内敛、想法独特，有时孤僻",
        "ability": "偏门技艺、研究、非常规思路",
        "relation": "生扶中带疏离，助力偏精神层面",
    },
}

# 双星合参（主星+同参）叙事模板
_DUAL_STAR_BLEND: Dict[frozenset, Dict[str, str]] = {
    frozenset({"正印", "偏印"}): {
        "character": (
            "慈护与独特思维并见：正印偏慈祥教养、含蓄护佑；"
            "偏印同参则更显聪慧内敛、思路非常规，偶有疏离感"
        ),
        "ability": "正途学问/贵人文书与偏门研究、技艺两路皆可，视何星更真而定侧重",
        "relation": (
            "母缘复合：正印偏温厚贴身，偏印偏精神疏离；"
            "双现时常呈「一亲一疏」或阶段性远近交替，不宜单用一种母职形象定论"
        ),
        "note": "母星以正印为主、偏印同参（印星统称）；双现合参论，不作两母实断。",
    },
    frozenset({"正财", "偏财"}): {
        "character": "务实与灵活并见：正财重承诺节俭，偏财重机会与交际",
        "ability": "稳健经营与外缘机遇并存，财路可正可偏",
        "relation": "财星双现时缘份与助力起伏更大，外缘与内助宜分而论",
        "note": "财星正偏同参，气质复合，勿单断一种财性。",
    },
    frozenset({"正官", "七杀"}): {
        "character": "规矩与魄力并见：正官重责任形象，七杀主急进锋芒",
        "ability": "体制管理与竞争开拓两面，压力与成就常同现",
        "relation": "官杀同见则约束与张力并存，相处宜礼亦须边界",
        "note": "官杀同参，不可只论柔顺或只论威压。",
    },
    frozenset({"比肩", "劫财"}): {
        "character": "义气与争强并见：比肩偏独立协作，劫财偏豪爽争夺",
        "ability": "同辈协作与开拓争利并存",
        "relation": "手足缘近亦易资源/意见冲突，宜分利有度",
        "note": "比劫同参，手足气质复合。",
    },
    frozenset({"食神", "伤官"}): {
        "character": "温和表达与敏感表现并见：食神偏乐天，伤官偏锐气",
        "ability": "技艺口才与批判创新可兼",
        "relation": "泄秀生财之中亦易口舌，缘深需边界",
        "note": "食伤同参，才艺气质宜合参。",
    },
}

_ELEMENT_HEALTH: Dict[str, str] = {
    "木": "肝胆、筋骨、眼目、神经系统宜养护",
    "火": "心脑血管、血压、眼目、炎症倾向宜注意",
    "土": "脾胃消化、肌肉、口齿宜调理",
    "金": "肺与呼吸、大肠、皮肤、鼻部宜防护",
    "水": "肾与泌尿、生殖、耳、骨与寒湿宜留意",
}

_ELEMENT_APPEAR: Dict[str, str] = {
    "木": "身形偏修长，气色青润",
    "火": "面色偏红润，神采外扬",
    "土": "体态偏敦厚，面方稳重",
    "金": "轮廓分明，神清气爽",
    "水": "面容润泽，体态可偏柔",
}

_MEMBER_KEYS = (
    ("father", "父亲"),
    ("mother", "母亲"),
    ("spouse", "配偶"),
    ("son", "儿子"),
    ("daughter", "女儿"),
    ("brother", "兄弟"),
    ("sister", "姐妹"),
)

_PRIMARY_STAR = {
    "father": "偏财",
    "mother": "正印",
    "spouse_male": "正财",
    "spouse_female": "正官",
    "son_male": "七杀",
    "son_female": "食神",
    "daughter_male": "正官",
    "daughter_female": "伤官",
    "brother": "比肩",
    "sister": "劫财",
}

# 六亲 → 宫位标签（结构取象，非实体诊断）
_PALACE_META: Dict[str, Tuple[str, str]] = {
    "father": ("parents", "父母宫（月支）"),
    "mother": ("parents", "父母宫（月支）"),
    "spouse": ("spouse", "夫妻宫（日支）"),
    "son": ("children", "子女宫（时支）"),
    "daughter": ("children", "子女宫（时支）"),
    "brother": ("parents", "父母宫（月支）"),
    "sister": ("parents", "父母宫（月支）"),
}

# 宫位本气粗类 → 与六亲主星是否相生/相克的提示
_PALACE_GROUP_FOR_STAR: Dict[str, str] = {
    "正印": "印",
    "偏印": "印",
    "正财": "财",
    "偏财": "财",
    "正官": "官杀",
    "七杀": "官杀",
    "食神": "食伤",
    "伤官": "食伤",
    "比肩": "比劫",
    "劫财": "比劫",
}

# 宫位本气对六亲的助/损（简化）
_PALACE_HELP: Dict[str, set] = {
    "印": {"印", "比劫"},  # 印得比劫/印气
    "财": {"财", "食伤"},
    "官杀": {"官杀", "财"},
    "食伤": {"食伤", "比劫"},
    "比劫": {"比劫", "印"},
}
_PALACE_HURT: Dict[str, set] = {
    "印": {"财"},  # 财坏印
    "财": {"比劫"},  # 比劫夺财
    "官杀": {"食伤"},  # 食伤制杀/伤官见官
    "食伤": {"印"},  # 印制食伤
    "比劫": {"官杀"},
}


def _primary_star(key: str, gender: str) -> str:
    g = "male" if gender in ("male", "男", "m", "M") else "female"
    if key == "spouse":
        return _PRIMARY_STAR[f"spouse_{g}"]
    if key == "son":
        return _PRIMARY_STAR[f"son_{g}"]
    if key == "daughter":
        return _PRIMARY_STAR[f"daughter_{g}"]
    return _PRIMARY_STAR.get(key) or _LIUQIN_STARS[g].get(key, "")


def _parse_star_token(star_field: str, fallback: str) -> str:
    """Take first token from '正印/偏印' style labels."""
    s = (star_field or fallback or "").strip()
    if "/" in s:
        s = s.split("/")[0]
    return s.strip() or fallback


def _all_stars(star_field: str, primary: str) -> List[str]:
    """Parse '正印/偏印' → ['正印','偏印']; always include primary if empty."""
    raw = (star_field or "").strip()
    if not raw:
        return [primary] if primary else []
    parts = [p.strip() for p in raw.replace("、", "/").split("/") if p.strip()]
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    if primary and primary not in seen:
        out.insert(0, primary)
    return out or ([primary] if primary else [])


def _blend_traits(stars: Sequence[str]) -> Dict[str, str]:
    """Single-star or dual-star trait bundle."""
    stars = [s for s in stars if s in _SHISHEN_TRAIT]
    if not stars:
        return {
            "character": "气质随十神组合而论，宜结合宫位",
            "ability": "能力倾向需结合全盘与大运",
            "relation": "与命主关系视星宫强弱而定",
            "dual_note": "",
        }
    if len(stars) == 1:
        t = _SHISHEN_TRAIT[stars[0]]
        return {**t, "dual_note": ""}
    key = frozenset(stars[:2])
    blend = _DUAL_STAR_BLEND.get(key)
    if blend:
        return {
            "character": blend["character"],
            "ability": blend["ability"],
            "relation": blend["relation"],
            "dual_note": blend.get("note", f"{'/'.join(stars)}双星合参。"),
        }
    # generic dual: join single traits
    a, b = stars[0], stars[1]
    ta, tb = _SHISHEN_TRAIT[a], _SHISHEN_TRAIT[b]
    return {
        "character": f"{a}侧：{ta['character']}；{b}同参：{tb['character']}",
        "ability": f"{a}：{ta['ability']}；兼{b}：{tb['ability']}",
        "relation": f"{ta['relation']}；另见{b}象：{tb['relation']}",
        "dual_note": f"{a}/{b}双星合参，气质复合论。",
    }


def _palace_co_note(
    key: str,
    day_master: str,
    palace_zhi: str,
    target_stars: Sequence[str],
    palace_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Parents/spouse/children palace co-participation narrative."""
    meta = _PALACE_META.get(key)
    if not meta or not palace_zhi:
        return {
            "palace_label": "",
            "palace_branch": "",
            "palace_main_qi": "",
            "palace_note": "",
        }
    _, palace_label = meta
    main_qi = shishen_for_branch_main(day_master, palace_zhi) if day_master else ""
    # Prefer structural description snippet when present
    struct_desc = ""
    if palace_info and isinstance(palace_info, dict):
        struct_desc = str(palace_info.get("description") or "")

    # Match any target star's group to palace main qi
    star_groups = {_PALACE_GROUP_FOR_STAR.get(s, "") for s in target_stars}
    star_groups.discard("")
    help_hit = any(main_qi in _PALACE_HELP.get(g, set()) for g in star_groups)
    hurt_hit = any(main_qi in _PALACE_HURT.get(g, set()) for g in star_groups)
    group_match = main_qi in star_groups  # e.g. 印宫见印星

    if group_match:
        tone = f"宫支本气为{main_qi}，与该六亲星同类，宫星相扶，缘分/助力更易落在宫位气质上"
    elif help_hit:
        tone = f"宫支本气为{main_qi}，对该六亲星偏生扶，宫星可互参"
    elif hurt_hit:
        tone = f"宫支本气为{main_qi}，对该六亲星偏克泄，宫动时易见波折或张力"
    elif main_qi:
        tone = f"宫支本气为{main_qi}，与六亲主星非直接同气，宜星宫分论、合参气质"
    else:
        tone = "宫位信息不足，暂以星论"

    note = f"{palace_label}{palace_zhi}：{tone}。"
    if struct_desc and struct_desc not in note:
        # keep short
        note = f"{note.rstrip('。')}（{struct_desc[:40]}）。"

    return {
        "palace_label": palace_label,
        "palace_branch": palace_zhi,
        "palace_main_qi": main_qi,
        "palace_note": note,
    }


def _dayun_timing_notes(
    bazi: str,
    gender: str,
    birth_date: str,
    birth_time: str,
    day_master: str,
    target_stars: Sequence[str],
    palace_zhi: str,
    strength: str,
) -> Dict[str, Any]:
    """Symbolic 大运 highlights when star/palace is activated."""
    highlights: List[Dict[str, str]] = []
    favorable: List[str] = []
    caution: List[str] = []
    if not birth_date:
        return {
            "dayun_highlights": [],
            "favorable_hint": "缺出生日期，暂不排大运应期。",
            "caution_hint": "结构层仅据原局论六亲，不作流年断言。",
            "liunian_samples": [],
        }
    try:
        periods = dayun_list(
            bazi, gender, birth_date, birth_time, calendar_type="solar", until_age=80
        )
    except Exception:
        periods = []

    for p in periods[:8]:
        pillar = str(p.get("pillar") or "")
        if len(pillar) < 2:
            continue
        ds, db = pillar[0], pillar[1]
        ss = shishen_for_stem(day_master, ds)
        a0, a1 = p.get("start_age"), p.get("end_age")
        age_txt = f"{a0}–{a1}岁" if a0 is not None else ""
        notes: List[str] = []
        if target_stars and ss in target_stars:
            notes.append(f"大运天干为{ss}，引动该六亲星")
        if palace_zhi and db == palace_zhi:
            notes.append("大运地支同宫位，宫动")
        if not notes:
            continue
        note = "；".join(notes)
        row = {"pillar": pillar, "ages": age_txt, "note": note, "stem_shishen": ss}
        highlights.append(row)
        if strength == "强":
            favorable.append(f"{age_txt}{pillar}（{note}）")
        else:
            caution.append(f"{age_txt}{pillar}（{note}，星弱时宫动亦易波折）")
        if len(highlights) >= 4:
            break

    if not highlights:
        fav = "原局未见显著「大运天干即六亲星 / 地支同宫」的强应期步，宜以原局论基调。"
        cau = "勿凭空指定公历某年；流年须另排对照。"
    else:
        fav = "；".join(favorable[:3]) if favorable else "见下表大运提要。"
        cau = "；".join(caution[:3]) if caution else "星弱或宫冲时，应期步宜作波折论而非喜庆断言。"

    liunian_samples = _liunian_sample_years(
        birth_date, day_master, target_stars, palace_zhi, strength
    )

    return {
        "dayun_highlights": highlights,
        "favorable_hint": fav,
        "caution_hint": cau,
        "liunian_samples": liunian_samples,
    }


def _liunian_sample_years(
    birth_date: str,
    day_master: str,
    target_stars: Sequence[str],
    palace_zhi: str,
    strength: str,
    *,
    max_samples: int = 4,
    scan_from_age: int = 18,
    scan_to_age: int = 72,
) -> List[Dict[str, Any]]:
    """Symbolic 流年 samples: year stem = liuqin star or year branch = palace.

    Product honesty: these are *illustrative activations*, never「必在某年」.
    """
    if not birth_date or not day_master:
        return []
    try:
        y0 = int(str(birth_date)[:4])
    except (TypeError, ValueError):
        return []
    start_y = y0 + scan_from_age
    end_y = y0 + scan_to_age
    # Prefer a window around "today" if birth is modern; still clamp to age band
    try:
        today_y = date.today().year
    except Exception:
        today_y = 2026
    # Scan full adult band but cap list length
    try:
        rows = liunian_list(start_y, end_y)
    except Exception:
        return []

    samples: List[Dict[str, Any]] = []
    near_today: List[Dict[str, Any]] = []
    for row in rows:
        year = int(row["year"])
        pillar = str(row.get("pillar") or "")
        if len(pillar) < 2:
            continue
        stem, branch = pillar[0], pillar[1]
        ss = shishen_for_stem(day_master, stem)
        reasons: List[str] = []
        if target_stars and ss in target_stars:
            reasons.append(f"流年天干为{ss}，引动六亲星")
        if palace_zhi and branch == palace_zhi:
            reasons.append("流年地支同宫位，宫动")
        if not reasons:
            continue
        age = year - y0
        tone = "星力偏真时或见助力/互动加分" if strength == "强" else "星弱时宫动亦易波折，宜保守看"
        item = {
            "year": year,
            "pillar": pillar,
            "age": age,
            "stem_shishen": ss,
            "note": "；".join(reasons) + f"。{tone}",
            "kind": "symbolic_sample",
        }
        if abs(year - today_y) <= 15:
            near_today.append(item)
        else:
            samples.append(item)

    # Prefer years near "now", then fill from rest; keep chronological among picks
    ordered = sorted(near_today + samples, key=lambda x: x["year"])
    # spread picks: take first match, then later ones with gap
    picked: List[Dict[str, Any]] = []
    last_y = -9999
    for it in ordered:
        if it["year"] - last_y < 3 and picked:
            continue
        picked.append(it)
        last_y = it["year"]
        if len(picked) >= max_samples:
            break
    return picked


def _build_member_dossier(
    key: str,
    label: str,
    info: Dict[str, Any],
    *,
    bazi: str,
    gender: str,
    birth_date: str,
    birth_time: str,
    day_master: str,
    palace_zhi: str,
    palace_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    primary = _primary_star(key, gender)
    stars = _all_stars(str(info.get("star") or ""), primary)
    star = stars[0] if stars else _parse_star_token(str(info.get("star") or ""), primary)
    star_display = "/".join(stars) if len(stars) > 1 else star
    exists = bool(info.get("exists"))
    strength = info.get("strength") if info.get("strength") in ("强", "弱") else "弱"
    if not exists:
        strength = "弱"
    support = info.get("support_text") or ""
    desc = info.get("description") or ""
    traits = _blend_traits(stars if exists else [star])
    dual_note = traits.get("dual_note") or ""

    # Health: blend elements of dual stars
    els = []
    for s in stars:
        if s in _SHISHEN_TRAIT:
            e = _star_element(day_master, s)
            if e and e not in els:
                els.append(e)
    if els:
        health = "；".join(_ELEMENT_HEALTH.get(e, "") for e in els if _ELEMENT_HEALTH.get(e))
        appear = "；".join(_ELEMENT_APPEAR.get(e, "") for e in els if _ELEMENT_APPEAR.get(e))
    else:
        health = "以该六亲星五行为线索调养，勿当作医疗诊断"
        appear = ""

    if not exists:
        character = f"{label}星在原局不显，性格不宜定论过细，缘分整体偏薄。"
        ability = "助力有限，不宜期待强势外援。"
        relation = f"与命主{label}缘浅或聚少，宜以自立为主。"
        health = "星不现则少论其疾厄细节。"
        appear = ""
        dual_note = ""
    elif strength == "弱":
        character = f"{traits['character']}；但星力偏弱/虚浮，上述气质可能打折或时隐时现。"
        ability = f"{traits['ability']}；实际发挥不稳定，助力时有时无。"
        relation = f"{traits['relation']}；缘分有波折，相处中宜降低期待、多沟通。"
        health = f"{health}（星弱者更宜注意，仍非医断）。"
    else:
        character = traits["character"]
        ability = traits["ability"]
        relation = f"{traits['relation']}；星力较真，缘深或助力更显。"
        health = f"{health}（星旺亦防太过）。"

    palace = _palace_co_note(key, day_master, palace_zhi, stars, palace_info)
    if palace.get("palace_note") and exists:
        relation = f"{relation} {palace['palace_note']}"

    target_stars = list(stars) if stars else [star]
    timing = _dayun_timing_notes(
        bazi, gender, birth_date, birth_time, day_master, target_stars, palace_zhi, strength
    )

    narrative_parts = [
        f"【{label}】以{star_display}为星，原局判定：{'现' if exists else '不现'}、{strength}。",
        dual_note,
        desc or support,
        palace.get("palace_note") or "",
        f"性格气质：{character}",
        f"能力倾向：{ability}",
        f"与命主：{relation}",
        f"健康线索：{health}",
    ]
    if appear and exists:
        narrative_parts.append(f"外貌气质参考：{appear}。")
    narrative_parts.append(f"应期提要（结构）：{timing['favorable_hint']}")
    narrative_parts.append(f"留意：{timing['caution_hint']}")
    ln = timing.get("liunian_samples") or []
    if ln:
        bits = [f"{x['year']}年{x['pillar']}" for x in ln[:3]]
        narrative_parts.append(
            f"流年象征取样（非断言）：{'、'.join(bits)}。仅作引动参考，禁止写成必在某年。"
        )

    return {
        "key": key,
        "label": label,
        "star": star_display,
        "stars": stars,
        "exists": exists,
        "strength": strength,
        "support_text": support,
        "locations_text": desc,
        "dual_star_note": dual_note,
        "palace": palace,
        "character": character,
        "ability": ability,
        "health": health,
        "appearance": appear,
        "relation": relation,
        "timing": timing,
        "narrative": "".join(
            p if p.endswith(("。", "；", "\n")) else p + "。" for p in narrative_parts if p
        ),
        "honesty": (
            "性格/健康为十神五行取象；双星/宫位为合参叙述；"
            "应期为大运与流年象征取样，不作「必在某年」断言。"
        ),
    }


def build_liuqin_dossier(
    bazi: str,
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
) -> Optional[Dict[str, Any]]:
    """Return full 六亲细断 dossier dict, or None if chart invalid."""
    lq = liuqin_profile(bazi, gender=gender)
    if not lq:
        return None
    sp = structural_profile(bazi) or {}
    day_master = lq.get("day_master") or sp.get("day_master") or ""
    g = "male" if gender in ("male", "男", "m", "M") else "female"

    parents_palace = lq.get("parents_palace") or {}
    spouse_palace = lq.get("spouse_palace") or {}
    children_palace = lq.get("children_palace") or {}

    palace_of = {
        "father": parents_palace.get("branch") or "",
        "mother": parents_palace.get("branch") or "",
        "spouse": spouse_palace.get("branch") or "",
        "son": children_palace.get("branch") or "",
        "daughter": children_palace.get("branch") or "",
        "brother": parents_palace.get("branch") or "",
        "sister": parents_palace.get("branch") or "",
    }
    palace_info_of = {
        "father": parents_palace,
        "mother": parents_palace,
        "spouse": spouse_palace,
        "son": children_palace,
        "daughter": children_palace,
        "brother": parents_palace,
        "sister": parents_palace,
    }

    members: Dict[str, Any] = {}
    for key, label in _MEMBER_KEYS:
        info = lq.get(key) if isinstance(lq.get(key), dict) else {}
        members[key] = _build_member_dossier(
            key,
            label,
            info or {},
            bazi=bazi,
            gender=g,
            birth_date=birth_date,
            birth_time=birth_time,
            day_master=day_master,
            palace_zhi=str(palace_of.get(key) or ""),
            palace_info=palace_info_of.get(key),
        )

    # Children synthesis
    son, dau = members.get("son") or {}, members.get("daughter") or {}
    if son.get("exists") and dau.get("exists"):
        if son.get("strength") == "强" and dau.get("strength") != "强":
            children_bias = "偏男"
        elif dau.get("strength") == "强" and son.get("strength") != "强":
            children_bias = "偏女"
        else:
            children_bias = "儿女皆有星"
    elif son.get("exists"):
        children_bias = "偏男/子星现"
    elif dau.get("exists"):
        children_bias = "偏女/女星现"
    else:
        children_bias = "子女星皆不显，缘薄或晚得"

    return {
        "gender": g,
        "day_master": day_master,
        "members": members,
        "children_bias": children_bias,
        "spouse_palace": spouse_palace,
        "parents_palace": parents_palace,
        "children_palace": children_palace,
        "disclaimer": (
            "六亲细断为结构取象：强弱为程序 det；性格/健康为十神五行象；"
            "母星等可正偏双星合参；宫位（父母/夫妻/子女）合参气质；"
            "应期为大运引动与流年象征取样，禁止写成「必在某年发生」。"
        ),
    }


def format_liuqin_dossier_prompt(dossier: Dict[str, Any]) -> str:
    """Compact Chinese block for LLM grounding (must not rewrite 强弱)."""
    if not dossier:
        return ""
    lines = [
        "【程序六亲细断·强制依据】",
        f"子女偏向参考：{dossier.get('children_bias', '')}",
        dossier.get("disclaimer", ""),
    ]
    members = dossier.get("members") or {}
    for key, label in _MEMBER_KEYS:
        m = members.get(key) or {}
        dual = m.get("dual_star_note") or ""
        pal = (m.get("palace") or {}).get("palace_note") or ""
        ln = (m.get("timing") or {}).get("liunian_samples") or []
        ln_txt = "、".join(f"{x.get('year')}{x.get('pillar')}" for x in ln[:3])
        lines.append(
            f"【{label}】星={m.get('star')} 现={'是' if m.get('exists') else '否'} "
            f"强弱={m.get('strength')}｜性格：{m.get('character')}｜"
            f"能力：{m.get('ability')}｜健康：{m.get('health')}｜"
            f"关系：{m.get('relation')}｜应期：{((m.get('timing') or {}).get('favorable_hint') or '')[:60]}"
            + (f"｜双星：{dual[:40]}" if dual else "")
            + (f"｜宫：{pal[:40]}" if pal else "")
            + (f"｜流年取样：{ln_txt}" if ln_txt else "")
        )
    lines.append(
        "叙述须与上列强弱一致；双星/宫位合参可写；应期只写趋势/大运步/象征流年，禁止断言单一公历年。"
    )
    return "\n".join(lines)


def format_liuqin_dossier_markdown(dossier: Dict[str, Any]) -> str:
    if not dossier:
        return ""
    lines = ["## 六亲细断（结构层）", "", dossier.get("disclaimer", ""), ""]
    if dossier.get("children_bias"):
        lines.append(f"**子女星偏向**：{dossier['children_bias']}")
        lines.append("")
    for key, label in _MEMBER_KEYS:
        m = (dossier.get("members") or {}).get(key) or {}
        lines.append(f"### {label}（{m.get('star', '—')} · {m.get('strength', '—')}）")
        if m.get("dual_star_note"):
            lines.append(f"- **双星合参**：{m['dual_star_note']}")
        pal = m.get("palace") or {}
        if pal.get("palace_note"):
            lines.append(f"- **宫位合参**：{pal['palace_note']}")
        lines.append(f"- **性格**：{m.get('character', '—')}")
        lines.append(f"- **能力**：{m.get('ability', '—')}")
        lines.append(f"- **健康线索**：{m.get('health', '—')}")
        if m.get("appearance"):
            lines.append(f"- **外貌气质**：{m.get('appearance')}")
        lines.append(f"- **与命主**：{m.get('relation', '—')}")
        t = m.get("timing") or {}
        lines.append(f"- **应期提要**：{t.get('favorable_hint', '—')}")
        if t.get("caution_hint"):
            lines.append(f"- **留意**：{t.get('caution_hint')}")
        highs = t.get("dayun_highlights") or []
        if highs:
            lines.append("- **大运引动**：")
            for h in highs[:4]:
                lines.append(
                    f"  - {h.get('ages', '')} {h.get('pillar', '')}：{h.get('note', '')}"
                )
        ln = t.get("liunian_samples") or []
        if ln:
            lines.append("- **流年象征取样**（非断言）：")
            for x in ln[:4]:
                lines.append(
                    f"  - {x.get('year')}年 {x.get('pillar', '')}"
                    f"（约{x.get('age', '?')}岁）：{x.get('note', '')}"
                )
        lines.append("")
    return "\n".join(lines)
