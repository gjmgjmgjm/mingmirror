#!/usr/bin/env python3
"""Structural bazi analysis helpers (10-gods, combinations, clashes, etc.)."""
from typing import Dict, List, Optional, Tuple

from tools.bazi_ai.bazi_validator import extract_pillars

_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}

_YIN_YANG = {
    "甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
    "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴",
}

_GENERATING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 天干五合：合化结果五行
_TIAN_GAN_HE = {
    ("甲", "己"): "土",
    ("乙", "庚"): "金",
    ("丙", "辛"): "水",
    ("丁", "壬"): "木",
    ("戊", "癸"): "火",
}

# 地支六合：合化结果五行
_DI_ZHI_LIU_HE = {
    ("子", "丑"): "土",
    ("寅", "亥"): "木",
    ("卯", "戌"): "火",
    ("辰", "酉"): "金",
    ("巳", "申"): "水",
    ("午", "未"): "土",
}

# 地支六冲
_DI_ZHI_CHONG = {
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
}

# 地支六害
_DI_ZHI_HAI = {
    ("子", "未"), ("丑", "午"), ("寅", "巳"),
    ("卯", "辰"), ("申", "亥"), ("酉", "戌"),
}

# 地支三刑 + 自刑
_DI_ZHI_XING = {
    # 三刑
    ("寅", "巳"): "无恩之刑",
    ("巳", "申"): "无恩之刑",
    ("寅", "申"): "无恩之刑",
    ("丑", "戌"): "恃势之刑",
    ("戌", "未"): "恃势之刑",
    ("丑", "未"): "恃势之刑",
    ("子", "卯"): "无礼之刑",
    # 自刑
    ("辰", "辰"): "自刑",
    ("午", "午"): "自刑",
    ("酉", "酉"): "自刑",
    ("亥", "亥"): "自刑",
}

# 空亡：按日柱干支查（简化表，每旬两个地支）
_KONG_WANG = {
    "甲子": ("戌", "亥"), "甲戌": ("申", "酉"), "甲申": ("午", "未"),
    "甲午": ("辰", "巳"), "甲辰": ("寅", "卯"), "甲寅": ("子", "丑"),
    "乙丑": ("戌", "亥"), "乙亥": ("申", "酉"), "乙酉": ("午", "未"),
    "乙未": ("辰", "巳"), "乙巳": ("寅", "卯"), "乙卯": ("子", "丑"),
    "丙寅": ("戌", "亥"), "丙子": ("申", "酉"), "丙戌": ("午", "未"),
    "丙申": ("辰", "巳"), "丙午": ("寅", "卯"), "丙辰": ("子", "丑"),
    "丁卯": ("戌", "亥"), "丁丑": ("申", "酉"), "丁亥": ("午", "未"),
    "丁酉": ("辰", "巳"), "丁未": ("寅", "卯"), "丁巳": ("子", "丑"),
    "戊辰": ("戌", "亥"), "戊寅": ("申", "酉"), "戊子": ("午", "未"),
    "戊戌": ("辰", "巳"), "戊申": ("寅", "卯"), "戊午": ("子", "丑"),
    "己巳": ("戌", "亥"), "己卯": ("申", "酉"), "己丑": ("午", "未"),
    "己亥": ("辰", "巳"), "己酉": ("寅", "卯"), "己未": ("子", "丑"),
    "庚午": ("戌", "亥"), "庚辰": ("申", "酉"), "庚寅": ("午", "未"),
    "庚子": ("辰", "巳"), "庚戌": ("寅", "卯"), "庚申": ("子", "丑"),
    "辛未": ("戌", "亥"), "辛巳": ("申", "酉"), "辛卯": ("午", "未"),
    "辛丑": ("辰", "巳"), "辛亥": ("寅", "卯"), "辛酉": ("子", "丑"),
    "壬申": ("戌", "亥"), "壬午": ("申", "酉"), "壬辰": ("午", "未"),
    "壬寅": ("辰", "巳"), "壬子": ("寅", "卯"), "壬戌": ("子", "丑"),
    "癸酉": ("戌", "亥"), "癸未": ("申", "酉"), "癸巳": ("午", "未"),
    "癸卯": ("辰", "巳"), "癸丑": ("寅", "卯"), "癸亥": ("子", "丑"),
}

_STEM_LABELS = ["年干", "月干", "日干", "时干"]
_BRANCH_LABELS = ["年支", "月支", "日支", "时支"]


def _find_key(mapping: Dict[str, str], value: str) -> str:
    for k, v in mapping.items():
        if v == value:
            return k
    return ""


def shishen_for_stem(day_master: str, target: str) -> str:
    """Return 10-god of *target* stem relative to *day_master*."""
    if target == day_master:
        return "比肩"
    t_el = _ELEMENT[target]
    dm_el = _ELEMENT[day_master]
    same_yy = _YIN_YANG[target] == _YIN_YANG[day_master]
    if t_el == dm_el:
        return "比肩" if same_yy else "劫财"
    if _GENERATING[dm_el] == t_el:
        return "食神" if same_yy else "伤官"
    if _RESTRAINING[dm_el] == t_el:
        return "偏财" if same_yy else "正财"
    if _GENERATING[t_el] == dm_el:
        return "偏印" if same_yy else "正印"
    if _RESTRAINING[t_el] == dm_el:
        return "七杀" if same_yy else "正官"
    return "未知"


def shishen_for_branch_main(day_master: str, branch: str) -> str:
    """Return 10-god of branch's main qi relative to day master (simplified)."""
    dm_el = _ELEMENT[day_master]
    br_el = _ELEMENT[branch]
    if br_el == dm_el:
        return "比劫"
    if _GENERATING[dm_el] == br_el:
        return "食伤"
    if _RESTRAINING[dm_el] == br_el:
        return "财"
    if _GENERATING[br_el] == dm_el:
        return "印"
    if _RESTRAINING[br_el] == dm_el:
        return "官杀"
    return "未知"


def _tian_gan_he(
    stems: List[str],
    labels: Optional[List[str]] = None,
) -> List[Tuple[str, str, str]]:
    """Find all 天干五合 pairs among the given stems with their labels."""
    if labels is None:
        labels = _STEM_LABELS
    result = []
    n = len(stems)
    for i in range(n):
        for j in range(i + 1, n):
            pair = (stems[i], stems[j])
            rev = (stems[j], stems[i])
            if pair in _TIAN_GAN_HE:
                result.append((labels[i], labels[j], _TIAN_GAN_HE[pair]))
            elif rev in _TIAN_GAN_HE:
                result.append((labels[i], labels[j], _TIAN_GAN_HE[rev]))
    return result


def _di_zhi_interactions(
    branches: List[str],
    labels: Optional[List[str]] = None,
) -> List[Tuple[str, str, str, str]]:
    """Find 六合/六冲/六害/三刑 among given branches with labels."""
    if labels is None:
        labels = _BRANCH_LABELS
    result = []
    n = len(branches)
    for i in range(n):
        for j in range(i + 1, n):
            b1, b2 = branches[i], branches[j]
            l1, l2 = labels[i], labels[j]
            pair = (b1, b2)
            rev = (b2, b1)
            if pair in _DI_ZHI_LIU_HE:
                result.append((l1, l2, "六合", _DI_ZHI_LIU_HE[pair]))
            elif rev in _DI_ZHI_LIU_HE:
                result.append((l1, l2, "六合", _DI_ZHI_LIU_HE[rev]))
            if pair in _DI_ZHI_CHONG or rev in _DI_ZHI_CHONG:
                result.append((l1, l2, "六冲", ""))
            if pair in _DI_ZHI_HAI or rev in _DI_ZHI_HAI:
                result.append((l1, l2, "六害", ""))
            if pair in _DI_ZHI_XING:
                result.append((l1, l2, "刑", _DI_ZHI_XING[pair]))
            elif rev in _DI_ZHI_XING:
                result.append((l1, l2, "刑", _DI_ZHI_XING[rev]))
    return result


def kong_wang(day_pillar: str) -> Tuple[str, str]:
    return _KONG_WANG.get(day_pillar, ("", ""))


def structural_profile(bazi: str) -> Optional[Dict]:
    """Return a structured profile of the chart."""
    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return None

    year, month, day, hour = pillars
    day_master = day[0]

    stems = [year[0], month[0], day[0], hour[0]]
    branches = [year[1], month[1], day[1], hour[1]]

    stem_shishen = {label: shishen_for_stem(day_master, s) for label, s in zip(_STEM_LABELS, stems)}
    branch_shishen = {label: shishen_for_branch_main(day_master, b) for label, b in zip(_BRANCH_LABELS, branches)}

    # Element counts (stems count 0.5, branches count 1.0)
    counts: Dict[str, int] = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    weighted: Dict[str, float] = {"木": 0.0, "火": 0.0, "土": 0.0, "金": 0.0, "水": 0.0}
    for s, b in zip(stems, branches):
        counts[_ELEMENT[s]] += 1
        counts[_ELEMENT[b]] += 1
        weighted[_ELEMENT[s]] += 0.5
        weighted[_ELEMENT[b]] += 1.0

    dm_element = _ELEMENT[day_master]
    mb_element = _ELEMENT[branches[1]]
    month_supports = mb_element == dm_element or _GENERATING[mb_element] == dm_element
    month_opposes = _RESTRAINING[mb_element] == dm_element or _GENERATING[dm_element] == mb_element
    dm_score = weighted[dm_element]

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

    guan_sha = _find_key(_RESTRAINING, dm_element)
    shi_shang = _GENERATING[dm_element]
    cai = _RESTRAINING[dm_element]
    yin = _find_key(_GENERATING, dm_element)
    bi_jie = dm_element

    def _el_label(el: str) -> str:
        return el

    if strength == "偏旺":
        useful = [_el_label(guan_sha), _el_label(shi_shang), _el_label(cai)]
        taboo = [_el_label(bi_jie), _el_label(yin)]
    elif strength == "偏弱":
        useful = [_el_label(yin), _el_label(bi_jie)]
        taboo = [_el_label(guan_sha), _el_label(cai)]
    else:
        useful = []
        taboo = []

    useful = list(dict.fromkeys([x for x in useful if x]))
    taboo = list(dict.fromkeys([x for x in taboo if x]))

    # Build text descriptions of structural relations
    tg_he = _tian_gan_he(stems)
    dz_rel = _di_zhi_interactions(branches)

    tg_he_text = "、".join(f"{a}与{b}合化{c}" for a, b, c in tg_he) or "无"
    dz_rel_text = "、".join(
        f"{a}与{b}{t}" + (f"（化{c}）" if c else "") for a, b, t, c in dz_rel
    ) or "无"

    kw = kong_wang(day)

    # Palace labels keyed by branch label.
    palace_map = {
        "年支": "祖上/父母宫",
        "月支": "父母/兄弟宫",
        "日支": "夫妻宫",
        "时支": "子女宫",
    }
    palace_text = "、".join(
        f"{label}{branches[i]}为{palace_map[label]}"
        for i, label in enumerate(_BRANCH_LABELS)
    )

    # 六亲：哪一柱代表什么
    liuqin_text = (
        f"年柱{year}代表祖上、父母（尤其父亲）、早年家境与出身；"
        f"月柱{month}代表父母、兄弟、家庭环境、事业根基与青年运；"
        f"日柱{day}代表命主自身，日支{day[1]}为夫妻宫主配偶；"
        f"时柱{hour}代表子女、晚辈、下属、学生及晚年运势。"
    )

    return {
        "day_master": day_master,
        "month_branch": branches[1],
        "stems": stems,
        "branches": branches,
        "stem_shishen": stem_shishen,
        "branch_shishen": branch_shishen,
        "element_counts_text": ",".join(f"{k}{counts[k]}" for k in ["木", "火", "土", "金", "水"]),
        "element_weighted_text": ",".join(f"{k}{weighted[k]:.1f}" for k in ["木", "火", "土", "金", "水"]),
        "strength": strength,
        "useful_gods": ",".join(useful) or "需细断",
        "taboo_gods": ",".join(taboo) or "需细断",
        "tian_gan_he": tg_he,
        "tian_gan_he_text": tg_he_text,
        "di_zhi_relations": dz_rel,
        "di_zhi_relations_text": dz_rel_text,
        "kong_wang": f"{kw[0]}{kw[1]}" if kw[0] else "",
        "palace_text": palace_text,
        "palace_map": {label: palace_map[label] for label in _BRANCH_LABELS},
        "liuqin_text": liuqin_text,
    }


def yearly_relations(
    bazi: str,
    dayun_pillar: str,
    liunian_pillar: str,
) -> Optional[Dict]:
    """Return the 10-gods and interactions of a liunian pillar vs chart + dayun."""
    profile = structural_profile(bazi)
    if profile is None:
        return None

    day_master = profile["day_master"]
    ly_stem, ly_branch = liunian_pillar[0], liunian_pillar[1]
    dy_stem, dy_branch = dayun_pillar[0], dayun_pillar[1]

    # Labels extended with dayun/liunian
    stem_labels = ["年干", "月干", "日干", "时干", "大运干", "流年干"]
    branch_labels = ["年支", "月支", "日支", "时支", "大运支", "流年支"]

    stems = profile["stems"] + [dy_stem, ly_stem]
    branches = profile["branches"] + [dy_branch, ly_branch]

    tg_he = _tian_gan_he(stems, labels=stem_labels)
    dz_rel = _di_zhi_interactions(branches, labels=branch_labels)

    # Filter to those involving liunian
    tg_he_ly = [x for x in tg_he if "流年干" in (x[0], x[1])]
    dz_rel_ly = [x for x in dz_rel if "流年支" in (x[0], x[1])]

    return {
        "liunian_pillar": liunian_pillar,
        "dayun_pillar": dayun_pillar,
        "liunian_stem_shishen": shishen_for_stem(day_master, ly_stem),
        "liunian_branch_shishen": shishen_for_branch_main(day_master, ly_branch),
        "dayun_stem_shishen": shishen_for_stem(day_master, dy_stem),
        "dayun_branch_shishen": shishen_for_branch_main(day_master, dy_branch),
        "tian_gan_he": tg_he_ly,
        "tian_gan_he_text": "、".join(f"{a}与{b}合化{c}" for a, b, c in tg_he_ly) or "无",
        "di_zhi_relations": dz_rel_ly,
        "di_zhi_relations_text": "、".join(
            f"{a}与{b}{t}" + (f"（化{c}）" if c else "") for a, b, t, c in dz_rel_ly
        ) or "无",
    }
