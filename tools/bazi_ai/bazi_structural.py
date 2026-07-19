#!/usr/bin/env python3
"""Structural bazi analysis helpers (10-gods, combinations, clashes, etc.)."""
from typing import Any, Dict, List, Optional, Tuple

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

# 地支三合局（每行为一行，第三个是该局五行）
_DI_ZHI_SAN_HE = {
    ("申", "子", "辰"): "水",
    ("寅", "午", "戌"): "火",
    ("亥", "卯", "未"): "木",
    ("巳", "酉", "丑"): "金",
}

# 地支三会局
_DI_ZHI_SAN_HUI = {
    ("寅", "卯", "辰"): "木",
    ("巳", "午", "未"): "火",
    ("申", "酉", "戌"): "金",
    ("亥", "子", "丑"): "水",
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

# 地支藏干（本气/中气/余气）
_BRANCH_HIDDEN_STEMS: Dict[str, List[str]] = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "戊", "庚"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}

# 六亲十神定位（gender: male/female）
_LIUQIN_STARS = {
    "male": {
        "father": "偏财",
        "mother": "正印",
        "spouse": "正财",
        "son": "七杀",
        "daughter": "正官",
        "brother": "比肩",
        "sister": "劫财",
    },
    "female": {
        "father": "偏财",
        "mother": "正印",
        "spouse": "正官",
        "son": "食神",
        "daughter": "伤官",
        "brother": "比肩",
        "sister": "劫财",
    },
}


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


def _di_zhi_san_he(
    branches: List[str],
    labels: Optional[List[str]] = None,
) -> List[Tuple[str, ...]]:
    """Find 三合局/半合局 among branches. Returns tuples of (labels..., type, element)."""
    if labels is None:
        labels = _BRANCH_LABELS
    result = []
    # Full 三合局
    for triplet, element in _DI_ZHI_SAN_HE.items():
        indices = []
        for b in triplet:
            if b in branches:
                idx = branches.index(b)
                # Avoid duplicate index if same branch appears twice
                if idx in indices:
                    alt = [i for i, x in enumerate(branches) if x == b and i not in indices]
                    if alt:
                        idx = alt[0]
                indices.append(idx)
        if len(set(indices)) == 3:
            result.append((labels[indices[0]], labels[indices[1]], labels[indices[2]], f"三合{element}局", element))
    # 半合局（三合中任意两个）
    for triplet, element in _DI_ZHI_SAN_HE.items():
        for pair in [(triplet[0], triplet[1]), (triplet[1], triplet[2])]:
            if pair[0] in branches and pair[1] in branches:
                idx1 = branches.index(pair[0])
                idx2 = branches.index(pair[1])
                # Check not already part of a full 三合局
                third = triplet[2] if pair == (triplet[0], triplet[1]) else triplet[0]
                if third not in branches:
                    result.append((labels[idx1], labels[idx2], f"半合{element}局", element))
    return result


def _di_zhi_san_hui(
    branches: List[str],
    labels: Optional[List[str]] = None,
) -> List[Tuple[str, ...]]:
    """Find 三会局 among branches."""
    if labels is None:
        labels = _BRANCH_LABELS
    result = []
    for triplet, element in _DI_ZHI_SAN_HUI.items():
        indices = []
        for b in triplet:
            if b in branches:
                idx = branches.index(b)
                if idx in indices:
                    alt = [i for i, x in enumerate(branches) if x == b and i not in indices]
                    if alt:
                        idx = alt[0]
                indices.append(idx)
        if len(set(indices)) == 3:
            result.append((labels[indices[0]], labels[indices[1]], labels[indices[2]], f"三会{element}局", element))
    return result


def _hidden_stem_interactions(
    branches: List[str],
    labels: Optional[List[str]] = None,
) -> List[Tuple[str, str, str, str, str]]:
    """Find interactions among hidden stems of branches.

    Returns tuples of (branch_label1, hidden_stem1, branch_label2, hidden_stem2, relation).
    """
    if labels is None:
        labels = _BRANCH_LABELS
    result = []
    n = len(branches)
    for i in range(n):
        for j in range(i + 1, n):
            b1, b2 = branches[i], branches[j]
            l1, l2 = labels[i], labels[j]
            hidden1 = _BRANCH_HIDDEN_STEMS.get(b1, [])
            hidden2 = _BRANCH_HIDDEN_STEMS.get(b2, [])
            for h1 in hidden1:
                for h2 in hidden2:
                    pair = (h1, h2)
                    rev = (h2, h1)
                    if pair in _TIAN_GAN_HE or rev in _TIAN_GAN_HE:
                        he_result = _TIAN_GAN_HE.get(pair) or _TIAN_GAN_HE.get(rev)
                        result.append((l1, h1, l2, h2, f"天干五合（化{he_result}）"))
                    # 生克关系可扩展，此处先记录合
    return result


def comprehensive_di_zhi_relations(
    branches: List[str],
    labels: Optional[List[str]] = None,
) -> Dict[str, List[Tuple]]:
    """Return comprehensive branch relations including 六合/冲/害/刑/三合/半合/三会/藏干合.

    Also annotates 冲合互解：若某合被冲，则标记为"合被冲解"；若某冲被合，则标记为"冲被合解"。
    """
    if labels is None:
        labels = _BRANCH_LABELS

    liu_he = []
    chong = []
    hai = []
    xing = []
    san_he = _di_zhi_san_he(branches, labels)
    san_hui = _di_zhi_san_hui(branches, labels)
    hidden_he = _hidden_stem_interactions(branches, labels)

    n = len(branches)
    he_pairs: Dict[Tuple[int, int], str] = {}
    chong_pairs: Dict[Tuple[int, int], str] = {}

    for i in range(n):
        for j in range(i + 1, n):
            b1, b2 = branches[i], branches[j]
            l1, l2 = labels[i], labels[j]
            pair = (b1, b2)
            rev = (b2, b1)

            if pair in _DI_ZHI_LIU_HE or rev in _DI_ZHI_LIU_HE:
                he_element = _DI_ZHI_LIU_HE.get(pair) or _DI_ZHI_LIU_HE.get(rev, "")
                he_pairs[(i, j)] = he_element
                liu_he.append((l1, l2, "六合", he_element))

            if pair in _DI_ZHI_CHONG or rev in _DI_ZHI_CHONG:
                chong_pairs[(i, j)] = ""
                chong.append((l1, l2, "六冲", ""))

            if pair in _DI_ZHI_HAI or rev in _DI_ZHI_HAI:
                hai.append((l1, l2, "六害", ""))

            if pair in _DI_ZHI_XING:
                xing.append((l1, l2, "刑", _DI_ZHI_XING[pair]))
            elif rev in _DI_ZHI_XING:
                xing.append((l1, l2, "刑", _DI_ZHI_XING[rev]))

    # Annotate 冲合互解
    resolved: List[Tuple[str, str, str, str]] = []
    for (i, j), he_element in he_pairs.items():
        # Check if either branch is involved in a 冲 with a third branch
        for (ci, cj) in chong_pairs:
            if (i in (ci, cj) or j in (ci, cj)) and not (i in (ci, cj) and j in (ci, cj)):
                resolved.append((labels[i], labels[j], "合被冲解", "六合被六冲破坏"))
                break

    for (i, j), _ in chong_pairs.items():
        # Check if either branch is involved in a 合 with a third branch
        for (hi, hj), he_element in he_pairs.items():
            if (i in (hi, hj) or j in (hi, hj)) and not (i in (hi, hj) and j in (hi, hj)):
                resolved.append((labels[i], labels[j], "冲被合解", "六冲被六合牵制"))
                break

    return {
        "六合": liu_he,
        "六冲": chong,
        "六害": hai,
        "刑": xing,
        "三合": san_he,
        "三会": san_hui,
        "藏干合": hidden_he,
        "冲合互解": resolved,
    }


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

    # 中和 bucket 太宽（dm_score 1.0~2.5 都落这）：用"生扶 vs 克泄耗"平衡做二次判定。
    # 帮身=印(生我)+比劫(同我)；耗身=官杀(克我)+食伤(我生)+财(我克)。
    if strength == "中和":
        yin_el = _find_key(_GENERATING, dm_element)
        shi_el = _GENERATING[dm_element]
        cai_el = _RESTRAINING[dm_element]
        guan_el = _find_key(_RESTRAINING, dm_element)
        help_score = weighted[dm_element] + weighted.get(yin_el, 0.0)
        drain_score = (weighted.get(shi_el, 0.0) + weighted.get(cai_el, 0.0)
                       + weighted.get(guan_el, 0.0))
        if help_score - drain_score >= 1.0:
            strength = "偏旺"
        elif drain_score - help_score >= 1.0:
            strength = "偏弱"
        # 差距 <1.0 才真正保留中和

    # 用神/忌神：统一走 yongshen.resolve（扶抑+调候+通关），避免双实现漂移。
    try:
        from tools.bazi_ai.yongshen import resolve_yongshen

        _ys = resolve_yongshen(bazi)
        useful = list(_ys.get("useful_gods") or [])
        taboo = list(_ys.get("taboo_gods") or [])
        strength = _ys.get("strength") or strength
        yongshen_block = _ys.get("prompt_block") or ""
        yongshen_primary = _ys.get("primary_method") or ""
    except Exception:
        # Fallback: legacy 扶抑-only if yongshen import/runtime fails.
        guan_sha = _find_key(_RESTRAINING, dm_element)
        shi_shang = _GENERATING[dm_element]
        cai = _RESTRAINING[dm_element]
        yin = _find_key(_GENERATING, dm_element)
        bi_jie = dm_element
        if strength == "偏旺":
            useful = [guan_sha, shi_shang, cai]
            taboo = [bi_jie, yin]
        elif strength == "偏弱":
            useful = [yin, bi_jie]
            taboo = [guan_sha, cai]
        else:
            useful, taboo = [], []
        useful = list(dict.fromkeys([x for x in useful if x]))
        taboo = list(dict.fromkeys([x for x in taboo if x and x not in useful]))
        yongshen_block = ""
        yongshen_primary = "扶抑"

    # Build text descriptions of structural relations
    tg_he = _tian_gan_he(stems)
    dz_rel = _di_zhi_interactions(branches)
    dz_comp = comprehensive_di_zhi_relations(branches)

    tg_he_text = "、".join(f"{a}与{b}合化{c}" for a, b, c in tg_he) or "无"
    dz_rel_text = "、".join(
        f"{a}与{b}{t}" + (f"（化{c}）" if c else "") for a, b, t, c in dz_rel
    ) or "无"

    def _format_comp_rel(name: str, items: List[Tuple]) -> str:
        if not items:
            return ""
        parts = []
        for item in items:
            if name == "三合":
                if len(item) == 5:
                    parts.append(f"{item[0]}、{item[1]}、{item[2]}{item[3]}（化{item[4]}）")
                else:
                    # 半合局为 4 元组
                    parts.append(f"{item[0]}与{item[1]}{item[2]}（化{item[3]}）")
            elif name == "三会":
                parts.append(f"{item[0]}、{item[1]}、{item[2]}{item[3]}（化{item[4]}）")
            elif name == "藏干合":
                parts.append(f"{item[0]}藏{item[1]}与{item[2]}藏{item[3]}{item[4]}")
            elif name == "冲合互解":
                parts.append(f"{item[0]}与{item[1]}{item[2]}（{item[3]}）")
            else:
                element = item[3] if len(item) > 3 else ""
                parts.append(f"{item[0]}与{item[1]}{item[2]}" + (f"（化{element}）" if element else ""))
        return f"{name}：" + "、".join(parts)

    dz_comp_texts = []
    for name in ["六合", "六冲", "六害", "刑", "三合", "三会", "藏干合", "冲合互解"]:
        text = _format_comp_rel(name, dz_comp.get(name, []))
        if text:
            dz_comp_texts.append(text)
    dz_comp_text = "\n".join(dz_comp_texts) if dz_comp_texts else "无特殊组合"

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

    # 确定性格局（子平月令定格：取月支本气藏干的十神为格，争议远小于用神）。
    # 注意 branch_shishen 只给分类(比劫/官杀/...)，需用本气藏干算细十神区分正偏。
    _ZHI_MAIN_GAN = {"子": "癸", "丑": "己", "寅": "甲", "卯": "乙", "辰": "戊",
                     "巳": "丙", "午": "丁", "未": "己", "申": "庚", "酉": "辛",
                     "戌": "戊", "亥": "壬"}
    _GEJU_MAP = {
        "食神": "食神格", "伤官": "伤官格",
        "正财": "正财格", "偏财": "偏财格",
        "正官": "正官格", "七杀": "七杀格",
        "正印": "正印格", "偏印": "偏印格",
        "比肩": "建禄格", "劫财": "月劫格",
    }
    month_main_gan = _ZHI_MAIN_GAN.get(branches[1], "")
    month_main_ss = shishen_for_stem(day_master, month_main_gan) if month_main_gan else ""
    geju = _GEJU_MAP.get(month_main_ss, "")

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
        "geju": geju,
        "useful_gods": ",".join(useful) or "需细断",
        "taboo_gods": ",".join(taboo) or "需细断",
        "yongshen_primary": yongshen_primary,
        "yongshen_block": yongshen_block,
        "tian_gan_he": tg_he,
        "tian_gan_he_text": tg_he_text,
        "di_zhi_relations": dz_rel,
        "di_zhi_relations_text": dz_rel_text,
        "di_zhi_comprehensive": dz_comp,
        "di_zhi_comprehensive_text": dz_comp_text,
        "kong_wang": f"{kw[0]}{kw[1]}" if kw[0] else "",
        "palace_text": palace_text,
        "palace_map": {label: palace_map[label] for label in _BRANCH_LABELS},
        "liuqin_text": liuqin_text,
    }


def wealth_power_resource_flow(bazi: str) -> Optional[Dict]:
    """Detect 财->杀->印->身 circulation that transforms pressure into support.

    For a wood day master this is 土（财）-> 金（杀）-> 水（印）-> 木（身）.
    If present, the chart's wealth potential is much higher than simple
    "weak body, strong wealth" would suggest.
    """
    profile = structural_profile(bazi)
    if profile is None:
        return None

    dm = profile["day_master"]
    dm_el = _ELEMENT[dm]
    # 十神对应的五行（相对日主）：
    # 财 = 我克者；官杀 = 克我者；印 = 生我者；食伤 = 我生者；比劫 = 同我者
    wealth_el = _RESTRAINING.get(dm_el)           # 我克者为财
    power_el = _find_key(_RESTRAINING, dm_el)     # 克我者为官杀
    resource_el = _find_key(_GENERATING, dm_el)   # 生我者为印

    if not all((wealth_el, power_el, resource_el)):
        return None

    # Collect elements present in stems and branches (including hidden).
    present_elements: set = set()
    stems = profile["stems"]
    branches = profile["branches"]
    for s in stems:
        present_elements.add(_ELEMENT[s])
    for b in branches:
        present_elements.add(_ELEMENT[b])
        for h in _BRANCH_HIDDEN_STEMS.get(b, []):
            present_elements.add(_ELEMENT[h])

    has_wealth = wealth_el in present_elements
    has_power = power_el in present_elements
    has_resource = resource_el in present_elements
    has_self = dm_el in present_elements  # always true

    # Check direct stem link: does a wealth stem sit next to power stem, etc.
    def _link_exists(src_el: str, dst_el: str) -> bool:
        """Return True if any src element stem/branch generates dst element nearby."""
        # Simplified: check if both elements are present in the chart.
        return src_el in present_elements and dst_el in present_elements

    flow_complete = has_wealth and has_power and has_resource and has_self
    flow_links = (
        _link_exists(wealth_el, power_el)
        and _link_exists(power_el, resource_el)
        and _link_exists(resource_el, dm_el)
    )

    if not (flow_complete and flow_links):
        return None

    # Describe the flow in terms of 10-gods.
    def _el_name(el: str) -> str:
        return el

    # For the day master element, map 10-gods.
    # The mapping below works because we constructed wealth/power/resource by
    # the restraining chain relative to dm_el.
    return {
        "exists": True,
        "description": (
            f"命局存在{_el_name(wealth_el)}（财）生{_el_name(power_el)}（官杀）、"
            f"{_el_name(power_el)}（官杀）生{_el_name(resource_el)}（印）、"
            f"{_el_name(resource_el)}（印）生{_el_name(dm_el)}（日主）的流通。"
            "财虽旺，但能通过官杀转而生印，最终印生身，化泄财星压力，主富贵有源。"
        ),
        "wealth_element": wealth_el,
        "power_element": power_el,
        "resource_element": resource_el,
        "self_element": dm_el,
    }


def _find_shishen_locations(day_master: str, pillars: List[str]) -> List[Dict]:
    """Return all locations (stem/branch/hidden) where each 10-god appears."""
    locations: Dict[str, List[Dict]] = {}
    for idx, pillar in enumerate(pillars):
        stem, branch = pillar[0], pillar[1]
        label = _STEM_LABELS[idx]
        ss = shishen_for_stem(day_master, stem)
        locations.setdefault(ss, []).append({
            "pillar": pillar,
            "position": label,
            "type": "天干",
            "char": stem,
        })
        # branch main qi — use 本气天干's precise 十神 (正印/偏印…), NOT the
        # coarse shishen_for_branch_main bucket ("印"/"财"/"官杀"). The coarse
        # keys never match liuqin_profile lookups (mother→正印), so 月支本气
        # was historically dropped and only 藏干 remained → systematic under-count.
        main_stems = _BRANCH_HIDDEN_STEMS.get(branch, [])
        if main_stems:
            main_stem = main_stems[0]
            ss_br = shishen_for_stem(day_master, main_stem)
            locations.setdefault(ss_br, []).append({
                "pillar": pillar,
                "position": _BRANCH_LABELS[idx],
                "type": "地支本气",
                "char": main_stem,
            })
        # hidden stems (skip the 本气 stem already recorded above to avoid
        # double-counting the same char as both 本气 and 藏干)
        for hidden in main_stems[1:]:
            ss_h = shishen_for_stem(day_master, hidden)
            locations.setdefault(ss_h, []).append({
                "pillar": pillar,
                "position": _BRANCH_LABELS[idx],
                "type": "地支藏干",
                "char": hidden,
            })
        # single-qi branches (子/卯/酉) only have 本气 — already recorded.
        # Branches whose list was empty fall through with no root (shouldn't happen).
    return locations


def _element_relation(day_master: str, char: str) -> str:
    """Return 生克关系 of *char* relative to day master."""
    dm_el = _ELEMENT[day_master]
    ch_el = _ELEMENT[char]
    if ch_el == dm_el:
        return "比劫"
    if _GENERATING[dm_el] == ch_el:
        return "泄耗"
    if _GENERATING[ch_el] == dm_el:
        return "生助"
    if _RESTRAINING[dm_el] == ch_el:
        return "克制"
    if _RESTRAINING[ch_el] == dm_el:
        return "受克"
    return "平"


def _star_element(day_master: str, shishen: str) -> str:
    """五行 of the given 十神 relative to day master."""
    dm_el = _ELEMENT[day_master]
    if shishen in ("比肩", "劫财"):
        return dm_el
    if shishen in ("食神", "伤官"):
        return _GENERATING[dm_el]
    if shishen in ("偏财", "正财"):
        return _RESTRAINING[dm_el]
    if shishen in ("七杀", "正官"):
        return _find_key(_RESTRAINING, dm_el)
    if shishen in ("偏印", "正印"):
        return _find_key(_GENERATING, dm_el)
    return dm_el


_LQ_POSITIONS = ("年支", "月支", "日支", "时支")
_LQ_ELEMENTS = ("木", "火", "土", "金", "水")


def _resolved_clash_pairs(dz_comp: dict) -> set:
    """六冲 pairs that are neutralized (冲被合解) — a resolved clash does NOT
    spoil a root. Returns a set of frozenset({posA, posB})."""
    out = set()
    for tup in dz_comp.get("冲合互解", []):
        if len(tup) >= 2 and "冲被合解" in " ".join(str(t) for t in tup):
            out.add(frozenset([tup[0], tup[1]]))
    return out


def _root_destroyed_at(pos: str, star_el: str, dz_comp: dict,
                       resolved_clash: set = None,
                       shishen: str = "") -> str:
    """Reason the root at branch *pos* is spoiled, or ''.

    六冲 shakes the root — but ONLY if the clash is not neutralized (冲被合解);
    合(化) to an element ≠ the star's transforms the root away. This fixes the
    冲坏根 over-fire (master still calls a star 强 when its clash is resolved or
    it has other support).
    """
    resolved_clash = resolved_clash or set()
    for tup in dz_comp.get("六冲", []):
        if pos in tup:
            pair = frozenset([tup[0], tup[1]])
            if pair not in resolved_clash:
                return "逢冲"
    for key in ("六合", "三合", "三会"):
        for tup in dz_comp.get(key, []):
            poses = [t for t in tup if t in _LQ_POSITIONS]
            hua = tup[-1] if tup and tup[-1] in _LQ_ELEMENTS else ""
            if pos in poses and hua and hua != star_el:
                # 印星月令合而不化: 三合/三会半合不破当令印根(母星常见);
                # 不推广到财官,避免配偶 over-promotion.
                if (
                    pos == "月支"
                    and key in ("三合", "三会")
                    and shishen in ("正印", "偏印")
                ):
                    continue
                return f"合化{hua}"
    return ""


def liuqin_profile(bazi: str, gender: str = "male") -> Optional[Dict]:
    """Return six-relations structural facts keyed by family member.

    For each relation: which 10-god, where it appears (stem/branch/hidden),
    which palace, whether supported/restrained, and a natural description.
    """
    profile = structural_profile(bazi)
    if profile is None:
        return None

    day_master = profile["day_master"]
    stems = profile["stems"]
    branches = profile["branches"]
    pillars = [f"{s}{b}" for s, b in zip(stems, branches)]

    gender_key = "male" if gender in ("male", "男") else "female"
    mapping = _LIUQIN_STARS[gender_key]
    locations = _find_shishen_locations(day_master, pillars)

    palace_map = {
        "年支": "祖上/父母宫",
        "月支": "父母/兄弟宫",
        "日支": "夫妻宫",
        "时支": "子女宫",
    }

    def _describe(relation: str, shishen: str) -> Dict:
        locs = locations.get(shishen, [])
        # Deduplicate by position+char to avoid repeats when branch main qi
        # overlaps with hidden stem representation.
        seen = set()
        unique_locs = []
        for loc in locs:
            key = (loc["position"], loc["char"], loc["type"])
            if key in seen:
                continue
            seen.add(key)
            unique_locs.append(loc)

        # For siblings, the day master itself counts as 比肩/劫财 by definition,
        # but it does not represent an actual sibling in the chart.
        if relation in ("兄弟", "姐妹"):
            unique_locs = [loc for loc in unique_locs if loc["position"] != "日干"]
            if not unique_locs:
                return {
                    "star": shishen,
                    "exists": False,
                    "description": f"命局天干不透{shishen}，地支亦无强根，{relation}缘分淡薄或助力有限。",
                }

        if not unique_locs:
            return {
                "star": shishen,
                "exists": False,
                "description": f"命局不现{shishen}，{relation}缘薄或助力不显。",
            }

        lines = []
        for loc in unique_locs:
            rel = _element_relation(day_master, loc["char"])
            palace = palace_map.get(loc["position"], "")
            line = f"{loc['position']}{loc['char']}（{loc['type']}），与日主{rel}"
            if palace:
                line += f"，落在{palace}"
            lines.append(line)

        # Determine if the star has root / is supported.
        # Three fixes from diagnose:
        # ① 冲坏根 over-fire → 条件化(已解决冲不算; 有其他支持时不判弱)
        # ② 中档太宽(有根无透干非得令→弱,大师倾向) → 收紧为弱
        # ③ 透干无根=弱 (keep, 大师偶尔判强是例外)
        has_stem = any(loc["type"] == "天干" for loc in unique_locs)
        root_positions = [loc["position"] for loc in unique_locs
                          if loc["type"] in ("地支本气", "地支藏干") and loc["position"] in _LQ_POSITIONS]
        has_branch_root = bool(root_positions)
        # 本气根 positions (得令 / 强根只认本气, 藏干月支不算「月令真根」)
        benqi_positions = {
            loc["position"]
            for loc in unique_locs
            if loc["type"] == "地支本气" and loc["position"] in _LQ_POSITIONS
        }
        star_el = _star_element(day_master, shishen)
        dz_comp = profile.get("di_zhi_comprehensive", {})
        resolved_clash = _resolved_clash_pairs(dz_comp)
        destroyed = [
            (rp, _root_destroyed_at(rp, star_el, dz_comp, resolved_clash, shishen))
            for rp in root_positions
        ]
        destroyed = [(rp, r) for rp, r in destroyed if r]
        destroyed_set = {rp for rp, _ in destroyed}
        intact_roots = [rp for rp in root_positions if rp not in destroyed_set]
        intact_benqi = [rp for rp in intact_roots if rp in benqi_positions]
        # 得令:
        #  - 月支本气未坏 → 真得令
        #  - 月支仅藏干: 仅当另有本气真根未坏时才算「有令有根」(避免母星假强)
        dedeling_benqi = "月支" in intact_benqi
        dedeling_cang = (
            "月支" in intact_roots
            and "月支" not in intact_benqi
            and bool(intact_benqi)
        )
        dedeling = dedeling_benqi or dedeling_cang

        support_notes = []
        if has_stem:
            support_notes.append("透干有力")
        if has_branch_root:
            support_notes.append("有根")
        if destroyed:
            sup_note = "、".join(f"{rp}{r}" for rp, r in destroyed)
            sup_suffix = ""
            if resolved_clash and any(
                    frozenset([rp, "月支"]) in resolved_clash or frozenset([rp, "年支"]) in resolved_clash
                    for rp, _ in destroyed):
                sup_suffix = "（该冲已被合解）"
            support_notes.append(f"但{sup_note}坏根{sup_suffix}，实为虚浮无力")
        support_text = "、".join(support_notes) if support_notes else "虚浮无根"

        # Effective strength (master-like binary, 中→弱 tightened).
        # 子女更严: 强必须透干+未坏根 (仅月令本气无透干 → 弱, 避免食伤「有根假强」).
        is_child = relation in ("儿子", "女儿", "子女")
        is_father = relation in ("父亲",)
        if is_child:
            if intact_roots and has_stem:
                strength = "强"
            else:
                strength = "弱"
        elif intact_roots and (has_stem or dedeling):
            strength = "强"    # intact root + (透干 or 得令) → 强
        elif has_stem and not intact_roots and not has_branch_root:
            strength = "弱"    # 透干无根 → 虚浮 → 弱
        else:
            strength = "弱"    # 有根无透干非得令→弱; 虚浮→弱; 根全坏→弱

        # Consistency: all roots destroyed → never leave as 强
        if strength == "强" and has_branch_root and not intact_roots:
            strength = "弱"

        # 父星: 真根宜落在年月（父母/祖上侧）。仅日时有本气/藏干根时，
        # 财气偏入夫妻/子女宫，父缘按弱论（对齐杨炎若干 gold）。
        if is_father and strength == "强":
            ym_benqi = any(p in ("年支", "月支") for p in intact_benqi)
            if not ym_benqi and not dedeling:
                strength = "弱"
                support_notes.append("根不在年月父母宫侧，父星作弱")
                support_text = "、".join(support_notes)

        # 父星: 财生官杀于日支 → 父财被日支官杀所耗，父缘作弱
        # （例：甲日坐申七杀，年透偏财戊土生申金）。
        if is_father and strength == "强" and star_el:
            day_br = branches[2] if len(branches) > 2 else ""
            main_stems = _BRANCH_HIDDEN_STEMS.get(day_br, [])
            if main_stems:
                day_ss = shishen_for_stem(day_master, main_stems[0])
                day_el = _ELEMENT.get(main_stems[0], "")
                if (
                    day_ss in ("七杀", "正官")
                    and day_el
                    and _GENERATING.get(star_el) == day_el
                ):
                    strength = "弱"
                    support_notes.append("财生官杀于日支，父星被耗作弱")
                    support_text = "、".join(support_notes)

        # 星被重度克泄→降级为弱(命理: 财被比劫夺 / 食伤被枭夺 / 官被食伤克).
        # 透干+本气真根时提高阈值, 避免官星透干有力却因全局火土多被误降.
        if strength == "强":
            _w = dict.fromkeys(_ELEMENT.values(), 0.0)
            for _s in stems:
                _w[_ELEMENT[_s]] += 0.5
            for _b in branches:
                _w[_ELEMENT[_b]] += 1.0
            _yin = _find_key(_GENERATING, star_el)      # 生星=印(帮)
            _xie = _GENERATING[star_el]                  # 星生=食伤(泄)
            _keme = _find_key(_RESTRAINING, star_el)     # 克星=官杀
            _ike = _RESTRAINING[star_el]                 # 星克=财(耗)
            _help = _w[star_el] + _w.get(_yin, 0.0)
            _drain = _w.get(_xie, 0.0) + _w.get(_keme, 0.0) + _w.get(_ike, 0.0)
            # 透干有力时阈值提高: 避免全局五行噪声压过官星透干真根.
            # 无透干仍用 1.5, 保留「星被克泄过重」降级能力.
            _thr = 2.5 if has_stem else 1.5
            if _drain - _help >= _thr:
                strength = "弱"
                support_notes.append(f"但{star_el}星被克泄过重({_xie}/{_keme}/{_ike}党众),实为弱")
                support_text = "、".join(support_notes)

        # 配偶: 多透干财/官星时，仅时/日支逢冲坏根不必然假弱
        # （例：戊日多透壬癸，子午冲坏时支本气根，大师仍断强）。
        is_spouse = relation in ("配偶",)
        if is_spouse and strength == "弱" and has_stem and has_branch_root:
            stem_count = sum(1 for loc in unique_locs if loc["type"] == "天干")
            only_chong = bool(destroyed) and all(
                (r == "逢冲" or (isinstance(r, str) and r.startswith("逢冲")))
                for _, r in destroyed
            )
            if stem_count >= 2 and only_chong and not intact_roots:
                strength = "强"
                support_notes.append("多透干，宫冲坏根仍存星力")
                support_text = "、".join(support_notes)

        return {
            "star": shishen,
            "exists": True,
            "locations": unique_locs,
            "strength": strength,
            "support_text": support_text,
            "description": f"{relation}以{shishen}为星：" + "；".join(lines) + f"。整体{support_text}（{strength}）。",
        }

    def _merge_dual_star(
        relation: str,
        primary_star: str,
        secondary_star: str,
        *,
        secondary_label: str = "同参",
        merge_strength: bool = True,
    ) -> Dict[str, Any]:
        """Merge primary + secondary 十神 for one 六亲 (e.g. 正印+偏印).

        When *merge_strength* is True, secondary 强 may lift primary unless
        primary is clearly floating/destroyed. Locations are always unioned.
        Father uses merge_strength=False so 正财(妻星) does not inflate 父星.
        """
        primary = _describe(relation, primary_star) or {
            "star": primary_star,
            "exists": False,
            "locations": [],
            "strength": "弱",
            "support_text": "",
            "description": "",
        }
        secondary = _describe(relation, secondary_star) or {
            "star": secondary_star,
            "exists": False,
            "locations": [],
            "strength": "弱",
            "support_text": "",
            "description": "",
        }
        merged = dict(primary)
        if not secondary.get("exists"):
            return merged
        if not merged.get("exists"):
            # Secondary-only presence: for narrative dual label, but strength
            # still follows merge_strength policy.
            merged = dict(secondary)
            merged["star"] = f"{primary_star}/{secondary_star}"
            if not merge_strength:
                # Keep product strength as 弱 when primary star absent
                # (e.g. 父无偏财仅见正财 → 仍标双星，强弱偏保守)
                merged["strength"] = "弱"
                merged["support_text"] = (
                    f"主星{primary_star}不现，仅{secondary_star}{secondary_label}："
                    f"{secondary.get('support_text', '')}"
                ).strip("：")
            return merged

        zh_sup = primary.get("support_text") or ""
        zh_weak_note = any(t in zh_sup for t in ("虚浮", "坏根", "无根"))
        if merge_strength and secondary.get("strength") == "强" and not zh_weak_note:
            merged["strength"] = "强"
        locs = list(merged.get("locations") or [])
        seen = {
            (item.get("position"), item.get("char"), item.get("type"))
            for item in locs
        }
        for loc in secondary.get("locations") or []:
            key = (loc.get("position"), loc.get("char"), loc.get("type"))
            if key not in seen:
                locs.append(loc)
                seen.add(key)
        merged["locations"] = locs
        merged["star"] = f"{primary_star}/{secondary_star}"
        if secondary.get("strength") == "强" and primary.get("strength") != "强":
            merged["support_text"] = (
                f"{primary.get('support_text', '')};"
                f"{secondary_star}{secondary_label}:{secondary.get('support_text', '')}"
            ).strip("; ")
            merged["description"] = (
                f"{primary.get('description', '')} "
                f"{secondary_star}{secondary_label}亦{secondary.get('strength', '')}。"
            ).strip()
        if zh_weak_note and primary.get("strength") == "弱":
            merged["strength"] = "弱"
        # Explicit: never let secondary alone inflate when merge_strength is off
        if not merge_strength:
            merged["strength"] = primary.get("strength") if primary.get("strength") in ("强", "弱") else "弱"
        return merged

    # Dual-star 合参:
    #  母:正印为主,偏印同参（印星统称）— strength 可合参（历史口径）
    #  父:偏财为主,正财同参标签 — strength 不因正财抬高
    #  配偶:男正财+偏财 / 女正官+七杀 — 标签合参；strength 只认主星
    #  子女:男官杀 / 女食伤 — 标签合参（子↔女星互参）；strength 只认主星
    #    （副星抬强在 gold 上易假阳，det 以主星为准）
    mother_merged = _merge_dual_star(
        "母亲", mapping["mother"], "偏印" if mapping["mother"] == "正印" else "正印",
        secondary_label="同参",
        merge_strength=True,
    )
    father_merged = _merge_dual_star(
        "父亲", mapping["father"], "正财" if mapping["father"] == "偏财" else "偏财",
        secondary_label="同参",
        merge_strength=False,
    )
    spouse_primary = mapping["spouse"]
    if gender_key == "male":
        spouse_secondary = "偏财" if spouse_primary == "正财" else "正财"
    else:
        spouse_secondary = "七杀" if spouse_primary == "正官" else "正官"
    spouse_merged = _merge_dual_star(
        "配偶", spouse_primary, spouse_secondary,
        secondary_label="同参",
        merge_strength=False,
    )
    # 配偶多透干救援：正偏财/官杀双星合参后，若多处天干见配偶星且仅宫冲坏根，
    # 主星 strength 可能仍弱——合参后按合并 locations 再判一次。
    if (
        isinstance(spouse_merged, dict)
        and spouse_merged.get("exists")
        and spouse_merged.get("strength") == "弱"
    ):
        locs = spouse_merged.get("locations") or []
        stem_n = sum(1 for loc in locs if loc.get("type") == "天干")
        root_n = sum(
            1
            for loc in locs
            if loc.get("type") in ("地支本气", "地支藏干")
        )
        if stem_n >= 2 and root_n >= 1:
            sup = spouse_merged.get("support_text") or ""
            if "逢冲" in sup and "合化" not in sup:
                spouse_merged = dict(spouse_merged)
                spouse_merged["strength"] = "强"
                spouse_merged["support_text"] = (
                    f"{sup};多透干合参，宫冲坏根仍存星力"
                ).strip("; ")
                desc = spouse_merged.get("description") or ""
                spouse_merged["description"] = desc.replace("（弱）", "（强）")

    # 子女双星: 男命官杀皆子女, 女命食伤皆子女 — 互为同参标签
    son_primary = mapping["son"]
    dau_primary = mapping["daughter"]
    son_merged = _merge_dual_star(
        "儿子", son_primary, dau_primary,
        secondary_label="同参",
        merge_strength=False,
    )
    dau_merged = _merge_dual_star(
        "女儿", dau_primary, son_primary,
        secondary_label="同参",
        merge_strength=False,
    )
    # 手足双星: 比肩/劫财互参 — 标签合参，强弱只认主星
    bro_primary = mapping["brother"]
    sis_primary = mapping["sister"]
    brother_merged = _merge_dual_star(
        "兄弟", bro_primary, sis_primary,
        secondary_label="同参",
        merge_strength=False,
    )
    sister_merged = _merge_dual_star(
        "姐妹", sis_primary, bro_primary,
        secondary_label="同参",
        merge_strength=False,
    )

    result: Dict[str, Any] = {
        "gender": gender_key,
        "day_master": day_master,
        "father": father_merged,
        "mother": mother_merged,
        "spouse": spouse_merged,
        "son": son_merged,
        "daughter": dau_merged,
        "brother": brother_merged,
        "sister": sister_merged,
        "palace_map": palace_map,
    }

    # Special palace notes
    result["spouse_palace"] = {
        "branch": branches[2],
        "shishen_main": shishen_for_branch_main(day_master, branches[2]),
        "description": f"夫妻宫日支{branches[2]}，本气为{shishen_for_branch_main(day_master, branches[2])}，配偶气质与婚姻基调由此决定。",
    }
    result["parents_palace"] = {
        "branch": branches[1],
        "description": f"父母宫月支{branches[1]}，主原生家庭与父母关系。",
    }
    result["children_palace"] = {
        "branch": branches[3],
        "description": f"子女宫时支{branches[3]}，主子女缘分与晚年。",
    }

    return result


_HEALTH_ORGANS = {
    "木": ["肝", "胆", "筋", "神经", "目"],
    "火": ["心", "血", "小肠", "眼", "舌"],
    "土": ["脾", "胃", "口", "肉"],
    "金": ["肺", "呼吸", "大肠", "皮肤", "鼻"],
    "水": ["肾", "膀胱", "骨", "耳", "泌尿"],
}


def health_profile(bazi: str) -> Optional[Dict]:
    """Deterministic 五行→脏腑弱项推断 (结构层健康锚点, 零 LLM).

    五行偏枯则对应脏腑弱:最弱五行(本气不足)+ 被最旺五行所克(被压制).
    用于注入 engine 健康断(像用神/格局),给 LLM 确定性锚点,而非让其自推.
    """
    prof = structural_profile(bazi)
    if prof is None:
        return None
    stems, branches = prof["stems"], prof["branches"]
    w = dict.fromkeys(_ELEMENT.values(), 0.0)
    for s in stems:
        w[_ELEMENT[s]] += 0.5
    for b in branches:
        w[_ELEMENT[b]] += 1.0
    ordered = sorted(w.items(), key=lambda kv: kv[1])
    weakest, strongest = ordered[0][0], ordered[-1][0]
    weak_els = {weakest, _RESTRAINING[strongest]}  # 最弱 + 被最旺克
    organs = sorted({o for el in weak_els for o in _HEALTH_ORGANS.get(el, [])})
    return {
        "weakest_element": weakest,
        "strongest_element": strongest,
        "weak_organs": organs,
        "element_weights": w,
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
    dz_comp = comprehensive_di_zhi_relations(branches, labels=branch_labels)

    # Filter to those involving liunian
    tg_he_ly = [x for x in tg_he if "流年干" in (x[0], x[1])]
    dz_rel_ly = [x for x in dz_rel if "流年支" in (x[0], x[1])]

    def _format_comp_rel(name: str, items: List[Tuple]) -> str:
        if not items:
            return ""
        parts = []
        for item in items:
            if name == "三合":
                if len(item) == 5:
                    parts.append(f"{item[0]}、{item[1]}、{item[2]}{item[3]}（化{item[4]}）")
                else:
                    # 半合局为 4 元组
                    parts.append(f"{item[0]}与{item[1]}{item[2]}（化{item[3]}）")
            elif name == "三会":
                parts.append(f"{item[0]}、{item[1]}、{item[2]}{item[3]}（化{item[4]}）")
            elif name == "藏干合":
                parts.append(f"{item[0]}藏{item[1]}与{item[2]}藏{item[3]}{item[4]}")
            elif name == "冲合互解":
                parts.append(f"{item[0]}与{item[1]}{item[2]}（{item[3]}）")
            else:
                element = item[3] if len(item) > 3 else ""
                parts.append(f"{item[0]}与{item[1]}{item[2]}" + (f"（化{element}）" if element else ""))
        return f"{name}：" + "、".join(parts)

    dz_comp_texts = []
    for name in ["六合", "六冲", "六害", "刑", "三合", "三会", "藏干合", "冲合互解"]:
        text = _format_comp_rel(name, dz_comp.get(name, []))
        if text:
            dz_comp_texts.append(text)
    dz_comp_text = "\n".join(dz_comp_texts) if dz_comp_texts else "无特殊组合"

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
        "di_zhi_comprehensive": dz_comp,
        "di_zhi_comprehensive_text": dz_comp_text,
    }
