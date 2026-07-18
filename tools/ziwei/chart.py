#!/usr/bin/env python3
"""Deterministic 紫微斗数 structural chart (structure layer, zero LLM).

Layers:
  1. 安命身宫 + 五行局 + 紫微/天府系主星 + 年干四化
  2. 辅星：左辅右弼、文昌文曲、魁钺、禄存、天马
  3. 煞星（简化）：擎羊陀罗、火星铃星、地空地劫
  4. 大限：按局数起运、阴阳顺逆、十年一宫

Honest: algorithms are classical-simplified for product reproducibility;
full 亮度/流派差请以专业排盘软件交叉校验。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_PALACE_NAMES = [
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "仆役", "官禄", "田宅", "福德", "父母",
]
_PALACE_BRANCHES = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

_NAYIN_BUREAU = {"金": 4, "水": 2, "火": 6, "土": 5, "木": 3}
_NAYIN = {
    "甲子": "金", "乙丑": "金", "丙寅": "火", "丁卯": "火",
    "戊辰": "木", "己巳": "木", "庚午": "土", "辛未": "土",
    "壬申": "金", "癸酉": "金", "甲戌": "火", "乙亥": "火",
    "丙子": "水", "丁丑": "水", "戊寅": "土", "己卯": "土",
    "庚辰": "金", "辛巳": "金", "壬午": "木", "癸未": "木",
    "甲申": "水", "乙酉": "水", "丙戌": "土", "丁亥": "土",
    "戊子": "火", "己丑": "火", "庚寅": "木", "辛卯": "木",
    "壬辰": "水", "癸巳": "水", "甲午": "金", "乙未": "金",
    "丙申": "火", "丁酉": "火", "戊戌": "木", "己亥": "木",
    "庚子": "土", "辛丑": "土", "壬寅": "金", "癸卯": "金",
    "甲辰": "火", "乙巳": "火", "丙午": "水", "丁未": "水",
    "戊申": "土", "己酉": "土", "庚戌": "金", "辛亥": "金",
    "壬子": "木", "癸丑": "木", "甲寅": "水", "乙卯": "水",
    "丙辰": "土", "丁巳": "土", "戊午": "火", "己未": "火",
    "庚申": "木", "辛酉": "木", "壬戌": "水", "癸亥": "水",
}

_ZIWEI_CHAIN = ["紫微", "天机", "", "太阳", "武曲", "天同", "", "廉贞"]
_TIANFU_CHAIN = ["天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "", "", "破军"]

_SIHUA = {
    "甲": {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"},
    "乙": {"禄": "天机", "权": "天梁", "科": "紫微", "忌": "太阴"},
    "丙": {"禄": "天同", "权": "天机", "科": "文昌", "忌": "廉贞"},
    "丁": {"禄": "太阴", "权": "天同", "科": "天机", "忌": "巨门"},
    "戊": {"禄": "贪狼", "权": "太阴", "科": "右弼", "忌": "天机"},
    "己": {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"},
    "庚": {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"},
    "辛": {"禄": "巨门", "权": "太阳", "科": "文曲", "忌": "文昌"},
    "壬": {"禄": "天梁", "权": "紫微", "科": "左辅", "忌": "武曲"},
    "癸": {"禄": "破军", "权": "巨门", "科": "太阴", "忌": "贪狼"},
}

# 年干 → 禄存落宫（地支）
_LUCUN = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
    "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}
# 年干 → 天魁 / 天钺
_KUI_YUE = {
    "甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
    "乙": ("子", "申"), "己": ("子", "申"),
    "丙": ("亥", "酉"), "丁": ("亥", "酉"),
    "壬": ("卯", "巳"), "癸": ("卯", "巳"),
    "辛": ("午", "寅"),
}
# 年支 → 天马
_TIANMA = {
    "寅": "申", "午": "申", "戌": "申",
    "申": "寅", "子": "寅", "辰": "寅",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "亥": "巳", "卯": "巳", "未": "巳",
}
# 年支三合 → 火星/铃星起点（简化：寅午戌火，申子辰水…）
# 火星：寅午戌在丑，申子辰在寅，巳酉丑在卯，亥卯未在酉 — 再顺数时辰
_HUOXING_BASE = {
    "寅": "丑", "午": "丑", "戌": "丑",
    "申": "寅", "子": "寅", "辰": "寅",
    "巳": "卯", "酉": "卯", "丑": "卯",
    "亥": "酉", "卯": "酉", "未": "酉",
}
_LINGXING_BASE = {
    "寅": "卯", "午": "卯", "戌": "卯",
    "申": "戌", "子": "戌", "辰": "戌",
    "巳": "戌", "酉": "戌", "丑": "戌",
    "亥": "戌", "卯": "戌", "未": "戌",
}

_YANG_STEMS = set("甲丙戊庚壬")

_MAIN_STARS = {
    "紫微", "天机", "太阳", "武曲", "天同", "廉贞",
    "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军",
}
_AUX_STARS = {"左辅", "右弼", "文昌", "文曲", "天魁", "天钺", "禄存", "天马"}
_SHA_STARS = {"擎羊", "陀罗", "火星", "铃星", "地空", "地劫"}

_STAR_TRAIT = {
    "紫微": "帝座，领导与尊贵",
    "天机": "善变机智，策划分析",
    "太阳": "光明事业，付出与名声",
    "武曲": "财星刚毅，执行力强",
    "天同": "福星随和，享乐安逸",
    "廉贞": "次桃花，复杂与才情",
    "天府": "库星稳重，守成理财",
    "太阴": "清润细腻，内敛财帛",
    "贪狼": "欲望桃花，交际才艺",
    "巨门": "暗星口舌，是非与研究",
    "天相": "印星辅弼，协调服务",
    "天梁": "荫星清贵，化解与清高",
    "七杀": "将星开创，变动冲击",
    "破军": "耗星革新，破旧立新",
    "左辅": "辅助贵人，得力帮手",
    "右弼": "辅助贵人，人缘调和",
    "文昌": "科名文墨，考试文书",
    "文曲": "才艺口才，灵动多思",
    "天魁": "阳贵人，白天提携",
    "天钺": "阴贵人，暗中扶助",
    "禄存": "财禄根基，聚财守成",
    "天马": "驿马变动，外出奔波",
    "擎羊": "刑伤刚烈，手术碰撞",
    "陀罗": "拖延纠缠，暗耗阻碍",
    "火星": "急躁爆发，血光冲动",
    "铃星": "暗火惊恐，突发波折",
    "地空": "空亡破耗，理想化",
    "地劫": "劫夺破败，起伏大",
}


def _extract_pillars(bazi: str) -> Optional[Tuple[str, str, str, str]]:
    parts = (bazi or "").strip().split()
    if len(parts) != 4 or not all(len(p) >= 2 for p in parts):
        return None
    return parts[0], parts[1], parts[2], parts[3]


def _branch_index(branch: str) -> int:
    if branch in _PALACE_BRANCHES:
        return _PALACE_BRANCHES.index(branch)
    if branch in _ZHI:
        # convert 子丑… to palace branch index
        return _PALACE_BRANCHES.index(branch)
    return 0


def _add_branch(branch: str, steps: int, reverse: bool = False) -> str:
    idx = _branch_index(branch)
    if reverse:
        return _PALACE_BRANCHES[(idx - steps) % 12]
    return _PALACE_BRANCHES[(idx + steps) % 12]


def life_body_palace(month_branch: str, hour_branch: str) -> Tuple[str, str]:
    if month_branch not in _PALACE_BRANCHES or hour_branch not in _ZHI:
        return "寅", "寅"
    m_idx = _PALACE_BRANCHES.index(month_branch)
    h_idx = _ZHI.index(hour_branch)
    life_idx = (m_idx - h_idx) % 12
    body_idx = (m_idx + h_idx) % 12
    return _PALACE_BRANCHES[life_idx], _PALACE_BRANCHES[body_idx]


def five_element_bureau(year_pillar: str) -> Tuple[str, int]:
    el = _NAYIN.get(year_pillar, "土")
    return el, _NAYIN_BUREAU.get(el, 5)


def ziwei_branch(day: int, bureau: int) -> str:
    day = max(1, min(int(day or 1), 30))
    bureau = max(2, min(int(bureau or 5), 6))
    idx = (day + bureau * 2 - 2) % 12
    return _PALACE_BRANCHES[idx]


def tianfu_branch_for_ziwei(zw: str) -> str:
    table = {
        "寅": "寅", "卯": "丑", "辰": "子", "巳": "亥",
        "午": "戌", "未": "酉", "申": "申", "酉": "未",
        "戌": "午", "亥": "巳", "子": "辰", "丑": "卯",
    }
    return table.get(zw, "寅")


def _place_chain(
    start_branch: str, chain: List[str], reverse: bool
) -> Dict[str, List[str]]:
    if start_branch not in _PALACE_BRANCHES:
        start_branch = "寅"
    start = _PALACE_BRANCHES.index(start_branch)
    out: Dict[str, List[str]] = {b: [] for b in _PALACE_BRANCHES}
    for i, name in enumerate(chain):
        if not name:
            continue
        bi = (start - i) % 12 if reverse else (start + i) % 12
        out[_PALACE_BRANCHES[bi]].append(name)
    return out


def _empty_map() -> Dict[str, List[str]]:
    return {b: [] for b in _PALACE_BRANCHES}


def _put(mp: Dict[str, List[str]], branch: str, name: str) -> None:
    if branch in mp and name not in mp[branch]:
        mp[branch].append(name)


def place_aux_stars(
    month_branch: str,
    hour_branch: str,
    year_stem: str,
    year_branch: str,
) -> Dict[str, List[str]]:
    """安左辅右弼、文昌文曲、魁钺、禄存、天马。"""
    mp = _empty_map()
    # 左辅：辰上顺数生月；右弼：戌上逆数生月
    # 正月从辰/戌起第 0 步 → 月支相对寅的序数
    if month_branch in _PALACE_BRANCHES:
        m_steps = _PALACE_BRANCHES.index(month_branch)  # 寅=0 正月
        _put(mp, _add_branch("辰", m_steps, reverse=False), "左辅")
        _put(mp, _add_branch("戌", m_steps, reverse=True), "右弼")
    # 文昌：巳上逆数生时；文曲：酉上顺数生时
    if hour_branch in _ZHI:
        h_steps = _ZHI.index(hour_branch)  # 子=0
        _put(mp, _add_branch("巳", h_steps, reverse=True), "文昌")
        _put(mp, _add_branch("酉", h_steps, reverse=False), "文曲")
    # 魁钺
    kui_yue = _KUI_YUE.get(year_stem)
    if kui_yue:
        _put(mp, kui_yue[0], "天魁")
        _put(mp, kui_yue[1], "天钺")
    # 禄存
    lucun = _LUCUN.get(year_stem)
    if lucun:
        _put(mp, lucun, "禄存")
    # 天马
    tianma = _TIANMA.get(year_branch)
    if tianma:
        _put(mp, tianma, "天马")
    return mp


def place_sha_stars(
    hour_branch: str,
    year_stem: str,
    year_branch: str,
) -> Dict[str, List[str]]:
    """安擎羊陀罗、火星铃星、地空地劫（简化可复现算法）。"""
    mp = _empty_map()
    lucun = _LUCUN.get(year_stem)
    if lucun and lucun in _PALACE_BRANCHES:
        # 羊刃前一，陀罗后一（顺时针地支）
        idx = _PALACE_BRANCHES.index(lucun)
        _put(mp, _PALACE_BRANCHES[(idx + 1) % 12], "擎羊")
        _put(mp, _PALACE_BRANCHES[(idx - 1) % 12], "陀罗")
    # 火星铃星：年支组起点 + 顺数时辰
    if hour_branch in _ZHI:
        h = _ZHI.index(hour_branch)
        hx0 = _HUOXING_BASE.get(year_branch, "丑")
        lx0 = _LINGXING_BASE.get(year_branch, "卯")
        _put(mp, _add_branch(hx0, h, reverse=False), "火星")
        _put(mp, _add_branch(lx0, h, reverse=False), "铃星")
        # 地空地劫：亥上逆/顺数时
        _put(mp, _add_branch("亥", h, reverse=True), "地空")
        _put(mp, _add_branch("亥", h, reverse=False), "地劫")
    return mp


def major_limits(
    life_palace: str,
    bureau: int,
    year_stem: str,
    gender: str,
) -> List[Dict[str, Any]]:
    """大限：起运岁=局数，十年一宫；阳男阴女顺，阴男阳女逆。"""
    gender_key = "female" if gender in ("female", "女", "女命") else "male"
    yang_year = year_stem in _YANG_STEMS
    # 顺行 if (male and yang) or (female and not yang)
    forward = (gender_key == "male" and yang_year) or (
        gender_key == "female" and not yang_year
    )
    start_age = max(1, min(int(bureau or 5), 10))
    if life_palace not in _PALACE_BRANCHES:
        life_palace = "寅"
    life_idx = _PALACE_BRANCHES.index(life_palace)

    limits: List[Dict[str, Any]] = []
    for i in range(12):
        if forward:
            br = _PALACE_BRANCHES[(life_idx + i) % 12]
        else:
            br = _PALACE_BRANCHES[(life_idx - i) % 12]
        age0 = start_age + i * 10
        age1 = age0 + 9
        # palace name relative to life
        if forward:
            pname = _PALACE_NAMES[i % 12]
        else:
            pname = _PALACE_NAMES[i % 12]
        limits.append({
            "index": i,
            "branch": br,
            "palace_name": pname,
            "start_age": age0,
            "end_age": age1,
            "label": f"{age0}-{age1}岁",
            "direction": "顺行" if forward else "逆行",
        })
    return limits


def current_major_limit(
    limits: List[Dict[str, Any]], age: Optional[int]
) -> Optional[Dict[str, Any]]:
    if age is None or not limits:
        return limits[0] if limits else None
    for lim in limits:
        if lim["start_age"] <= age <= lim["end_age"]:
            return lim
    if age < limits[0]["start_age"]:
        return limits[0]
    return limits[-1]


def structural_chart(
    bazi: str,
    gender: str = "male",
    day_of_month: int = 15,
    age: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    pillars = _extract_pillars(bazi)
    if pillars is None:
        return None
    year_p, month_p, day_p, hour_p = pillars
    year_stem, year_branch = year_p[0], year_p[1]
    month_branch = month_p[1]
    hour_branch = hour_p[1]

    life, body = life_body_palace(month_branch, hour_branch)
    el, bureau = five_element_bureau(year_p)
    zw = ziwei_branch(day_of_month, bureau)
    tf = tianfu_branch_for_ziwei(zw)

    zw_map = _place_chain(zw, _ZIWEI_CHAIN, reverse=True)
    tf_map = _place_chain(tf, _TIANFU_CHAIN, reverse=False)
    aux_map = place_aux_stars(month_branch, hour_branch, year_stem, year_branch)
    sha_map = place_sha_stars(hour_branch, year_stem, year_branch)

    stars_by_branch: Dict[str, List[str]] = {b: [] for b in _PALACE_BRANCHES}
    main_by_branch: Dict[str, List[str]] = {b: [] for b in _PALACE_BRANCHES}
    aux_by_branch: Dict[str, List[str]] = {b: [] for b in _PALACE_BRANCHES}
    sha_by_branch: Dict[str, List[str]] = {b: [] for b in _PALACE_BRANCHES}

    for b in _PALACE_BRANCHES:
        mains = zw_map.get(b, []) + tf_map.get(b, [])
        auxs = aux_map.get(b, [])
        shas = sha_map.get(b, [])
        main_by_branch[b] = list(mains)
        aux_by_branch[b] = list(auxs)
        sha_by_branch[b] = list(shas)
        stars_by_branch[b] = list(mains) + list(auxs) + list(shas)

    life_idx = _PALACE_BRANCHES.index(life)
    palaces: List[Dict[str, Any]] = []
    for i, name in enumerate(_PALACE_NAMES):
        br = _PALACE_BRANCHES[(life_idx + i) % 12]
        mains = main_by_branch.get(br, [])
        auxs = aux_by_branch.get(br, [])
        shas = sha_by_branch.get(br, [])
        all_stars = stars_by_branch.get(br, [])
        palaces.append({
            "name": name,
            "branch": br,
            "stars": all_stars,
            "main_stars": mains,
            "aux_stars": auxs,
            "sha_stars": shas,
            "star_traits": [
                _STAR_TRAIT[s] for s in all_stars if s in _STAR_TRAIT
            ],
        })

    sihua = _SIHUA.get(year_stem, {})
    sihua_list = [f"{k}·{v}" for k, v in sihua.items()]

    ming = next(p for p in palaces if p["name"] == "命宫")
    ming_mains = ming.get("main_stars") or []
    zhu_xing = [s for s in ming_mains if s in _MAIN_STARS][:4]
    if not zhu_xing:
        zhu_xing = ming_mains[:2] or ming.get("stars", [])[:2] or ["（空宫）"]

    gender_key = "female" if gender in ("female", "女", "女命") else "male"
    limits = major_limits(life, bureau, year_stem, gender_key)
    cur_limit = current_major_limit(limits, age)

    def _palace_text(pname: str, default: str) -> str:
        p = next((x for x in palaces if x["name"] == pname), None)
        if not p:
            return default
        mains = p.get("main_stars") or []
        auxs = p.get("aux_stars") or []
        shas = p.get("sha_stars") or []
        parts = []
        if mains:
            parts.append("主星" + "、".join(mains))
        if auxs:
            parts.append("辅" + "、".join(auxs))
        if shas:
            parts.append("煞" + "、".join(shas))
        if not parts:
            return default
        return f"{pname}在{p['branch']}，{'；'.join(parts)}。"

    domain_analysis = {
        "career": _palace_text("官禄", "官禄宫待细排。") + "事业宜观官禄与迁移、大限官禄流。",
        "wealth": _palace_text("财帛", "财帛宫待细排。") + "财运看禄存天马与财帛主星。",
        "marriage": _palace_text("夫妻", "夫妻宫待细排。") + "感情看夫妻宫主辅与桃花。",
        "health": _palace_text("疾厄", "疾厄宫待细排。") + "健康忌煞忌同宫，宜规律作息。",
        "general": (
            f"命宫{ming['branch']}主星{'、'.join(zhu_xing)}；身宫{body}；"
            f"{el}{bureau}局；辅星左辅右弼文昌魁钺已安。"
            + (
                f"当前大限{cur_limit['label']}走{cur_limit['branch']}。"
                if cur_limit
                else ""
            )
        ),
    }

    # highlight important aux in ming
    ming_aux = ming.get("aux_stars") or []
    ming_sha = ming.get("sha_stars") or []

    return {
        "system": "ziwei",
        "trust": "certain_simplified",
        "note": (
            "结构层含：命身宫、五行局、紫微/天府主星、年干四化、"
            "辅星(辅弼昌曲魁钺禄马)、煞星(羊陀火铃空劫简化)、大限十年运。"
            "亮度与流派差未展开；日数未知默认十五。"
        ),
        "gender": gender_key,
        "year_pillar": year_p,
        "five_element": el,
        "bureau": bureau,
        "bureau_label": f"{el}{bureau}局",
        "life_palace": life,
        "body_palace": body,
        "ziwei_branch": zw,
        "tianfu_branch": tf,
        "ming_gong": f"{life}宫",
        "shen_gong": f"{body}宫",
        "zhu_xing": zhu_xing,
        "ming_aux": ming_aux,
        "ming_sha": ming_sha,
        "si_hua": sihua_list,
        "si_hua_map": sihua,
        "palaces": palaces,
        "major_limits": limits,
        "current_limit": cur_limit,
        "limit_direction": limits[0]["direction"] if limits else "",
        "domain_analysis": domain_analysis,
        "day_of_month_used": day_of_month,
        "age_used": age,
    }


def chart_from_birth(
    bazi: str,
    gender: str = "male",
    birth_date: str = "",
    age: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    day = 15
    computed_age = age
    if birth_date and len(birth_date) >= 10:
        try:
            day = int(birth_date[8:10])
        except ValueError:
            day = 15
        if computed_age is None:
            try:
                by = int(birth_date[0:4])
                from datetime import date as _date

                computed_age = _date.today().year - by
            except ValueError:
                computed_age = None
    return structural_chart(
        bazi, gender=gender, day_of_month=day, age=computed_age
    )


def _year_pillar(year: int) -> str:
    """Gregorian year → 年柱 (立春近似：整年用该公历年干支)."""
    # 1984 甲子
    idx = (int(year) - 1984) % 60
    jiazi = []
    stems = list("甲乙丙丁戊己庚辛壬癸")
    branches = list("子丑寅卯辰巳午未申酉戌亥")
    for i in range(60):
        jiazi.append(stems[i % 10] + branches[i % 12])
    return jiazi[idx]


def liunian_years(
    chart: Dict[str, Any],
    start_year: int,
    end_year: int,
    birth_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """流年表：太岁入宫 + 流年四化 + 所在大限。

    流年命宫取「太岁地支」所在本命十二宫（常见简化口径）。
    """
    if not chart or not chart.get("palaces"):
        return []
    start_year = int(start_year)
    end_year = int(end_year)
    if end_year < start_year:
        start_year, end_year = end_year, start_year
    # cap range
    if end_year - start_year > 30:
        end_year = start_year + 30

    branch_to_palace = {
        p["branch"]: p for p in chart.get("palaces") or [] if p.get("branch")
    }
    limits = chart.get("major_limits") or []

    rows: List[Dict[str, Any]] = []
    for y in range(start_year, end_year + 1):
        yp = _year_pillar(y)
        y_stem, y_branch = yp[0], yp[1]
        palace = branch_to_palace.get(y_branch) or {}
        sihua = _SIHUA.get(y_stem, {})
        sihua_list = [f"{k}·{v}" for k, v in sihua.items()]
        age = (y - birth_year) if birth_year else None
        lim = current_major_limit(limits, age) if age is not None else None

        mains = palace.get("main_stars") or []
        auxs = palace.get("aux_stars") or []
        shas = palace.get("sha_stars") or []
        pname = palace.get("name") or "（无对应宫）"

        # soft overview
        parts = [f"{y}年{yp}，太岁入{pname}（{y_branch}）"]
        if mains:
            parts.append("宫内主星" + "、".join(mains))
        if auxs:
            parts.append("辅" + "、".join(auxs[:3]))
        if shas:
            parts.append("见煞" + "、".join(shas[:2]))
        if sihua_list:
            parts.append("流年四化" + "、".join(sihua_list))
        if lim:
            parts.append(f"大限{lim.get('label')}·{lim.get('branch')}")

        # domain soft hints by palace name
        focus = {
            "命宫": "自身状态与心态",
            "官禄": "事业工作",
            "财帛": "财运收支",
            "夫妻": "感情婚姻",
            "疾厄": "健康作息",
            "迁移": "外出变动",
            "福德": "精神兴趣",
        }.get(pname, "综合运势")

        overview = "；".join(parts) + f"。本年重点：{focus}。"
        if shas and any(s in ("擎羊", "陀罗", "火星", "铃星") for s in shas):
            caution = f"太岁宫见煞，{focus}宜稳，避免冲动决策。"
        elif "忌" in " ".join(sihua_list):
            caution = "流年化忌启动，相关宫位事务宜谨慎沟通与收尾。"
        else:
            caution = "整体可按大限主题推进，注意劳逸结合。"

        rows.append({
            "year": y,
            "pillar": yp,
            "stem": y_stem,
            "branch": y_branch,
            "age": age,
            "palace_name": pname,
            "palace_branch": y_branch,
            "main_stars": mains,
            "aux_stars": auxs,
            "sha_stars": shas,
            "si_hua": sihua_list,
            "si_hua_map": sihua,
            "major_limit": lim,
            "overview": overview,
            "focus": focus,
            "career": f"事业：{focus if pname in ('官禄', '迁移', '命宫') else '随大限官禄宫'}；" + overview[:60],
            "wealth": f"财运：{'财帛宫受太岁' if pname == '财帛' else '看禄存与财帛主星'}。",
            "marriage": f"感情：{'夫妻宫受太岁' if pname == '夫妻' else '宜观夫妻宫与桃花辅星'}。",
            "health": f"健康：{'疾厄宫受太岁，忌过劳' if pname == '疾厄' else '保持作息'}。",
            "caution": caution,
        })
    return rows


def yearly_bundle(
    bazi: str,
    gender: str = "male",
    birth_date: str = "",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    years: int = 10,
) -> Dict[str, Any]:
    """Natal structural chart + 流年表 for product API."""
    from datetime import date as _date

    chart = chart_from_birth(bazi, gender=gender, birth_date=birth_date)
    if chart is None:
        return {"error": "无效八字", "chart": None, "liunian": []}

    birth_year = None
    if birth_date and len(birth_date) >= 4:
        try:
            birth_year = int(birth_date[:4])
        except ValueError:
            birth_year = None

    today_y = _date.today().year
    if start_year is None:
        start_year = today_y
    if end_year is None:
        end_year = start_year + max(1, min(int(years or 10), 20)) - 1

    liunian = liunian_years(
        chart, start_year, end_year, birth_year=birth_year
    )
    return {
        "error": None,
        "chart": chart,
        "basic_info": to_basic_info(chart),
        "liunian": liunian,
        "start_year": start_year,
        "end_year": end_year,
        "trust": "certain_simplified",
        "note": chart.get("note", "") + " 流年：太岁入宫+流年四化+所在大限。",
    }


def to_basic_info(chart: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ming_gong": chart.get("ming_gong"),
        "shen_gong": chart.get("shen_gong"),
        "zhu_xing": chart.get("zhu_xing") or [],
        "ming_aux": chart.get("ming_aux") or [],
        "ming_sha": chart.get("ming_sha") or [],
        "si_hua": chart.get("si_hua") or [],
        "bureau_label": chart.get("bureau_label"),
        "life_palace": chart.get("life_palace"),
        "body_palace": chart.get("body_palace"),
        "palaces": chart.get("palaces") or [],
        "major_limits": chart.get("major_limits") or [],
        "current_limit": chart.get("current_limit"),
        "limit_direction": chart.get("limit_direction"),
        "trust": chart.get("trust"),
        "note": chart.get("note"),
    }
