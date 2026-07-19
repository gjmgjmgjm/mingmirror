#!/usr/bin/env python3
"""Unified 用神 / 忌神 resolver (扶抑 + 调候 + 通关).

``bazi_structural.structural_profile`` already embeds a simplified 用神.  This
module is the **single authoritative** implementation:

1. **扶抑** from day-master strength (身强泄耗克, 身弱生扶).
2. **调候** from 穷通宝鉴 core (``tiao_hou.py``) — seasonal + day-master pairs.
3. **通关** when two strong elements clash.

Merge policy (practical school):
- Extreme months (巳午未 / 亥子丑): 调候 first, then 扶抑 non-conflicting.
- Other months: 扶抑 first; 调候 elements added if not already 忌神.
- Intersection of 扶抑 ∩ 调候 is listed first (highest confidence).

Also provides year-element scoring helpers for 应期 shortlist (useful year + /
taboo year −).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.tiao_hou import tiaohou_yongshen, tiaohou_yongshen_stems

_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}
_GENERATING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_SUMMER = {"巳", "午", "未"}
_WINTER = {"亥", "子", "丑"}

# Year-stem/branch useful → soft shortlist boost (conservative).
YEAR_USEFUL_WEIGHT = 0.25
YEAR_TABOO_WEIGHT = -0.15


def _find_key(mapping: Dict[str, str], value: str) -> str:
    for k, v in mapping.items():
        if v == value:
            return k
    return ""


def _weighted_elements(pillars: List[str]) -> Dict[str, float]:
    weighted = {"木": 0.0, "火": 0.0, "土": 0.0, "金": 0.0, "水": 0.0}
    for p in pillars:
        weighted[_ELEMENT[p[0]]] += 0.5
        weighted[_ELEMENT[p[1]]] += 1.0
    return weighted


def day_master_strength(bazi: str) -> Tuple[str, Dict[str, float], str, str]:
    """Return (strength, weighted, day_master, month_branch)."""
    pillars = extract_pillars(bazi)
    day_master = pillars[2][0]
    month_branch = pillars[1][1]
    weighted = _weighted_elements(pillars)
    dm_el = _ELEMENT[day_master]
    mb_el = _ELEMENT[month_branch]
    month_supports = mb_el == dm_el or _GENERATING[mb_el] == dm_el
    month_opposes = _RESTRAINING[mb_el] == dm_el or _GENERATING[dm_el] == mb_el
    dm_score = weighted[dm_el]

    if month_supports and dm_score >= 2.0:
        strength = "偏旺"
    elif month_opposes and dm_score <= 1.5:
        strength = "偏弱"
    elif dm_score >= 2.5:
        strength = "偏旺"
    elif dm_score <= 1.0:
        strength = "偏弱"
    else:
        strength = "中和"

    if strength == "中和":
        yin_el = _find_key(_GENERATING, dm_el)
        shi_el = _GENERATING[dm_el]
        cai_el = _RESTRAINING[dm_el]
        guan_el = _find_key(_RESTRAINING, dm_el)
        help_score = weighted[dm_el] + weighted.get(yin_el, 0.0)
        drain_score = (
            weighted.get(shi_el, 0.0)
            + weighted.get(cai_el, 0.0)
            + weighted.get(guan_el, 0.0)
        )
        if help_score - drain_score >= 1.0:
            strength = "偏旺"
        elif drain_score - help_score >= 1.0:
            strength = "偏弱"

    return strength, weighted, day_master, month_branch


def fuyi_yongshen(strength: str, day_master: str) -> Tuple[List[str], List[str]]:
    """扶抑用神/忌神 as element lists."""
    dm_el = _ELEMENT[day_master]
    guan = _find_key(_RESTRAINING, dm_el)
    shi = _GENERATING[dm_el]
    cai = _RESTRAINING[dm_el]
    yin = _find_key(_GENERATING, dm_el)
    bi = dm_el
    if strength == "偏旺":
        return [guan, shi, cai], [bi, yin]
    if strength == "偏弱":
        return [yin, bi], [guan, cai]
    return [], []


def tongguan_yongshen(weighted: Dict[str, float]) -> List[str]:
    """通关：两强相克时取通关五行。"""
    useful: List[str] = []
    for a_el, wa in sorted(weighted.items(), key=lambda x: -x[1]):
        if wa < 1.5:
            break
        b_el = _RESTRAINING.get(a_el)
        if b_el and weighted.get(b_el, 0) >= 1.5:
            tong = _GENERATING.get(a_el)
            if tong and tong not in useful:
                useful.append(tong)
    return useful


def resolve_yongshen(bazi: str) -> Dict[str, Any]:
    """Full 用神 resolution for a chart.

    Returns keys used by prompt / rules / structural_profile::
        strength, day_master, month_branch,
        useful_gods (list[str]), taboo_gods (list[str]),
        useful_gods_text, taboo_gods_text,
        methods (list of {name, useful, note}),
        tiaohou_stems, primary_method, prompt_block
    """
    strength, weighted, day_master, month_branch = day_master_strength(bazi)
    fuyi_u, fuyi_t = fuyi_yongshen(strength, day_master)
    tiaohou: Set[str] = tiaohou_yongshen(day_master, month_branch)
    tiaohou_stems = sorted(tiaohou_yongshen_stems(day_master, month_branch))
    tongguan = tongguan_yongshen(weighted)

    extreme_season = month_branch in _SUMMER or month_branch in _WINTER
    methods: List[Dict[str, Any]] = []

    if strength in ("偏旺", "偏弱"):
        methods.append(
            {
                "name": "扶抑",
                "useful": list(fuyi_u),
                "taboo": list(fuyi_t),
                "note": f"日主{strength}，{'泄耗克' if strength == '偏旺' else '生扶'}为用",
            }
        )
    if tiaohou:
        methods.append(
            {
                "name": "调候",
                "useful": sorted(tiaohou),
                "taboo": [],
                "note": f"穷通宝鉴·{day_master}日/{month_branch}月 喜{''.join(sorted(tiaohou))}"
                + (f"（{'夏月润燥' if month_branch in _SUMMER else '冬月驱寒'}）" if extreme_season else ""),
            }
        )
    if tongguan:
        methods.append(
            {
                "name": "通关",
                "useful": list(tongguan),
                "taboo": [],
                "note": "两强相克取通关之神",
            }
        )

    useful: List[str] = []
    taboo: List[str] = []
    primary = "扶抑"

    # 调候独胜:扶抑(帮身/克泄)与调候(穷通宝鉴)完全冲突(disjoint)时,以 cited
    # 权威为准。否则扶抑在春/秋会盖过穷通宝鉴的调候用神(如庚金春秋月喜木火、
    # 壬癸水秋月喜金),与 engine 自称的"对齐穷通宝鉴"不一致。
    tiaohou_conflict = bool(tiaohou) and set(fuyi_u).isdisjoint(tiaohou)

    if tiaohou_conflict:
        primary = "调候"
        useful.extend(sorted(tiaohou))
        for el in tongguan:  # 通关若与调候不冲突仍可并入
            if el not in useful and el not in tiaohou:
                useful.append(el)
        for el in fuyi_u:  # 冲突的扶抑帮身元素转为忌(与调候对立)
            if el not in useful:
                taboo.append(el)
    elif extreme_season and tiaohou:
        # 调候优先
        primary = "调候"
        useful.extend(sorted(tiaohou))
        for el in fuyi_u:
            if el not in useful and el not in (set(fuyi_t) - tiaohou):
                # skip fuyi items that are pure 忌 and not 调候
                if el in fuyi_t and el not in tiaohou:
                    continue
                if el not in useful:
                    useful.append(el)
        for el in fuyi_t:
            if el not in tiaohou and el not in useful:
                taboo.append(el)
        for el in tongguan:
            if el not in useful:
                useful.append(el)
    elif strength == "中和":
        primary = "调候+通关" if (tiaohou or tongguan) else "中和细断"
        useful.extend(sorted(tiaohou))
        for el in tongguan:
            if el not in useful:
                useful.append(el)
        # mild seasonal opposite as taboo
        if month_branch in _SUMMER:
            taboo.append("火")
        elif month_branch in _WINTER:
            taboo.append("水")
    else:
        primary = "扶抑"
        # intersection first
        for el in fuyi_u:
            if el in tiaohou and el not in useful:
                useful.append(el)
        for el in fuyi_u:
            if el not in useful:
                useful.append(el)
        for el in sorted(tiaohou):
            if el not in useful and el not in fuyi_t:
                useful.append(el)
        for el in tongguan:
            if el not in useful and el not in fuyi_t:
                useful.append(el)
        taboo.extend([e for e in fuyi_t if e not in useful])

    useful = list(dict.fromkeys([e for e in useful if e]))
    taboo = list(dict.fromkeys([e for e in taboo if e and e not in useful]))

    prompt_block = _format_prompt_block(
        strength=strength,
        day_master=day_master,
        month_branch=month_branch,
        useful=useful,
        taboo=taboo,
        primary=primary,
        methods=methods,
        tiaohou_stems=tiaohou_stems,
    )

    return {
        "strength": strength,
        "day_master": day_master,
        "month_branch": month_branch,
        "useful_gods": useful,
        "taboo_gods": taboo,
        "useful_gods_text": ",".join(useful) if useful else "需细断",
        "taboo_gods_text": ",".join(taboo) if taboo else "需细断",
        "methods": methods,
        "tiaohou_stems": tiaohou_stems,
        "tiaohou_elements": sorted(tiaohou),
        "primary_method": primary,
        "prompt_block": prompt_block,
        "element_weighted": weighted,
    }


def _format_prompt_block(
    *,
    strength: str,
    day_master: str,
    month_branch: str,
    useful: List[str],
    taboo: List[str],
    primary: str,
    methods: List[Dict[str, Any]],
    tiaohou_stems: List[str],
) -> str:
    lines = [
        "【用神/忌神（结构化，择吉与吉凶方向以本块为准）】",
        f"- 日主{day_master}，月令{month_branch}，旺衰：{strength}",
        f"- 主法：{primary}",
        f"- 用神五行：{','.join(useful) if useful else '需细断'}",
        f"- 忌神五行：{','.join(taboo) if taboo else '需细断'}",
    ]
    if tiaohou_stems:
        lines.append(f"- 调候喜用天干参考：{'、'.join(tiaohou_stems)}")
    for m in methods:
        u = ",".join(m.get("useful") or []) or "—"
        lines.append(f"- 〔{m['name']}〕用={u}｜{m.get('note', '')}")
    lines.append(
        "- 择年/断吉凶：流年天干地支五行落在用神为偏吉信号，落在忌神为偏凶信号；"
        "须与宫位冲合、十神引动综合，不可单凭用神定案。"
    )
    return "\n".join(lines)


def year_pillar_elements(year: int) -> Tuple[str, str]:
    """Return (stem_element, branch_element) for a Gregorian year."""
    # 1984 = 甲子
    gan = "甲乙丙丁戊己庚辛壬癸"[(year - 1984) % 10]
    zhi = "子丑寅卯辰巳午未申酉戌亥"[(year - 1984) % 12]
    return _ELEMENT[gan], _ELEMENT[zhi]


def score_year_by_yongshen(
    year: int,
    useful: List[str],
    taboo: List[str],
) -> Tuple[float, List[str]]:
    """Soft score for a year against useful/taboo elements."""
    if not useful and not taboo:
        return 0.0, []
    se, be = year_pillar_elements(year)
    score = 0.0
    reasons: List[str] = []
    useful_set = set(useful)
    taboo_set = set(taboo)
    if se in useful_set:
        score += YEAR_USEFUL_WEIGHT
        reasons.append(f"流年天干五行{se}为用神({YEAR_USEFUL_WEIGHT:+.2f})")
    if be in useful_set:
        score += YEAR_USEFUL_WEIGHT * 0.8
        reasons.append(f"流年地支五行{be}为用神({YEAR_USEFUL_WEIGHT * 0.8:+.2f})")
    if se in taboo_set:
        score += YEAR_TABOO_WEIGHT
        reasons.append(f"流年天干五行{se}为忌神({YEAR_TABOO_WEIGHT:+.2f})")
    if be in taboo_set:
        score += YEAR_TABOO_WEIGHT * 0.8
        reasons.append(f"流年地支五行{be}为忌神({YEAR_TABOO_WEIGHT * 0.8:+.2f})")
    return score, reasons
