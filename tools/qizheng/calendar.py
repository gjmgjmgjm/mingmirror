#!/usr/bin/env python3
"""Structural calculations for Qi Zheng Si Yu (七政四余).

This module computes the traditional palace layout from a four-pillar bazi
string without requiring real astronomical ephemeris data.  It is intentionally
simplified: life/body palaces, body lord, five-element pattern and the twelve
palace branches are derived from the birth chart; the actual degrees of the
seven governors and four remains are left to the LLM layer.
"""

from typing import Any, Dict, List, Optional, Tuple

# 十二地支，命宫排盘从寅起正月，顺行。
_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 命宫推算用：寅为正月，顺数至生月；再从生月宫起子时，逆数至生时。
_MONTH_START = "寅"
_PALACE_BRANCHES = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

# 月份地支 -> 索引（正月寅=0，二月卯=1，...）
_MONTH_INDEX = {b: i for i, b in enumerate(_PALACE_BRANCHES)}

# 时辰地支 -> 索引（子=0，丑=1，...）
_HOUR_INDEX = {b: i for i, b in enumerate(_ZHI)}

# 身主：生年地支对应星曜
_BODY_LORD = {
    "子": "火星",
    "丑": "木星", "亥": "木星",
    "寅": "金星", "戌": "金星",
    "卯": "太阴", "酉": "太阴",
    "辰": "土星", "申": "土星",
    "巳": "水星", "未": "水星",
    "午": "太阳",
}

# 六十甲子纳音（完整表），用于定五行局
_NAYIN = {
    "甲子": "海中金", "乙丑": "海中金",
    "丙寅": "炉中火", "丁卯": "炉中火",
    "戊辰": "大林木", "己巳": "大林木",
    "庚午": "路旁土", "辛未": "路旁土",
    "壬申": "剑锋金", "癸酉": "剑锋金",
    "甲戌": "山头火", "乙亥": "山头火",
    "丙子": "涧下水", "丁丑": "涧下水",
    "戊寅": "城头土", "己卯": "城头土",
    "庚辰": "白蜡金", "辛巳": "白蜡金",
    "壬午": "杨柳木", "癸未": "杨柳木",
    "甲申": "泉中水", "乙酉": "泉中水",
    "丙戌": "屋上土", "丁亥": "屋上土",
    "戊子": "霹雳火", "己丑": "霹雳火",
    "庚寅": "松柏木", "辛卯": "松柏木",
    "壬辰": "长流水", "癸巳": "长流水",
    "甲午": "沙中金", "乙未": "沙中金",
    "丙申": "山下火", "丁酉": "山下火",
    "戊戌": "平地木", "己亥": "平地木",
    "庚子": "壁上土", "辛丑": "壁上土",
    "壬寅": "金箔金", "癸卯": "金箔金",
    "甲辰": "覆灯火", "乙巳": "覆灯火",
    "丙午": "天河水", "丁未": "天河水",
    "戊申": "大驿土", "己酉": "大驿土",
    "庚戌": "钗钏金", "辛亥": "钗钏金",
    "壬子": "桑柘木", "癸丑": "桑柘木",
    "甲寅": "大溪水", "乙卯": "大溪水",
    "丙辰": "沙中土", "丁巳": "沙中土",
    "戊午": "天上火", "己未": "天上火",
    "庚申": "石榴木", "辛酉": "石榴木",
    "壬戌": "大海水", "癸亥": "大海水",
}

_ELEMENT_FROM_NAYIN = {
    "海中金": "金", "剑锋金": "金", "白蜡金": "金", "沙中金": "金",
    "金箔金": "金", "钗钏金": "金", "石榴木": "金",
    "炉中火": "火", "山头火": "火", "霹雳火": "火", "山下火": "火",
    "覆灯火": "火", "天上火": "火",
    "大林木": "木", "杨柳木": "木", "松柏木": "木", "平地木": "木",
    "桑柘木": "木", "大溪水": "木",
    "路旁土": "土", "城头土": "土", "屋上土": "土", "壁上土": "土",
    "大驿土": "土", "沙中土": "土",
    "涧下水": "水", "泉中水": "水", "长流水": "水", "天河水": "水",
    "大海水": "水",
}

# 十二宫名称，以命宫为起点逆时针排列
_PALACE_NAMES = [
    "命宫", "财帛", "兄弟", "田宅", "男女", "奴仆",
    "夫妻", "疾厄", "迁移", "官禄", "福德", "相貌",
]

# 五行局 -> 起运岁数（水二局、木三局、金四局、土五局、火六局）
_ELEMENT_START_AGE = {
    "水": 2,
    "木": 3,
    "金": 4,
    "土": 5,
    "火": 6,
}

# 天干阴阳
_YANG_STEMS = {"甲", "丙", "戊", "庚", "壬"}

# 地支六合/六冲（用于流年大限互动）
_SIX_CHONG = {
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
}
_SIX_HE = {
    ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
    ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
}


def _extract_pillars(chart: str) -> Optional[Tuple[str, str, str, str]]:
    """Return (year, month, day, hour) pillars from a four-pillar string."""
    parts = chart.strip().split()
    if len(parts) != 4:
        return None
    return tuple(parts)  # type: ignore[return-value]


def _branch(pillar: str) -> str:
    return pillar[1]


def _stem(pillar: str) -> str:
    return pillar[0]


def life_palace(month_branch: str, hour_branch: str) -> str:
    """Return the life palace branch from birth month and hour branches.

    Rule: start at 寅 for the first month, count forward to birth month;
    then from that palace start at 子 hour and count backward to birth hour.
    """
    month_idx = _MONTH_INDEX.get(month_branch)
    hour_idx = _HOUR_INDEX.get(hour_branch)
    if month_idx is None or hour_idx is None:
        return ""
    idx = (month_idx - hour_idx) % 12
    return _PALACE_BRANCHES[idx]


def body_palace(month_branch: str, hour_branch: str) -> str:
    """Return the body palace branch from birth month and hour branches.

    Rule: same as life palace, but count forward for the hour.
    """
    month_idx = _MONTH_INDEX.get(month_branch)
    hour_idx = _HOUR_INDEX.get(hour_branch)
    if month_idx is None or hour_idx is None:
        return ""
    idx = (month_idx + hour_idx) % 12
    return _PALACE_BRANCHES[idx]


def body_lord(year_branch: str) -> str:
    """Return the body lord star for a birth-year branch."""
    return _BODY_LORD.get(year_branch, "")


def nayin(year_pillar: str) -> str:
    """Return the nayin element phrase for a year pillar."""
    return _NAYIN.get(year_pillar, "")


def five_element_pattern(year_pillar: str) -> str:
    """Return the five-element pattern (五行局) for a year pillar."""
    ny = nayin(year_pillar)
    return _ELEMENT_FROM_NAYIN.get(ny, "")


def twelve_palaces(life_palace_branch: str) -> Dict[str, str]:
    """Return a mapping of palace name to branch, starting from life palace.

    The 12 palaces are arranged counter-clockwise starting at the life palace.
    """
    if life_palace_branch not in _ZHI:
        return {}
    start = _ZHI.index(life_palace_branch)
    result: Dict[str, str] = {}
    for i, name in enumerate(_PALACE_NAMES):
        # counter-clockwise: 子->亥->戌->... in standard ZHI order is reverse
        idx = (start - i) % 12
        result[name] = _ZHI[idx]
    return result


def structural_profile(chart: str) -> Optional[Dict[str, Any]]:
    """Return a structural profile of a Qi Zheng chart from its bazi."""
    pillars = _extract_pillars(chart)
    if pillars is None:
        return None
    year, month, day, hour = pillars
    month_branch = _branch(month)
    hour_branch = _branch(hour)
    year_branch = _branch(year)

    lp = life_palace(month_branch, hour_branch)
    bp = body_palace(month_branch, hour_branch)
    bl = body_lord(year_branch)
    fep = five_element_pattern(year)
    palaces = twelve_palaces(lp)

    return {
        "chart": chart,
        "year_pillar": year,
        "month_pillar": month,
        "day_pillar": day,
        "hour_pillar": hour,
        "day_master": _stem(day),
        "month_branch": month_branch,
        "hour_branch": hour_branch,
        "year_branch": year_branch,
        "life_palace": lp,
        "body_palace": bp,
        "body_lord": bl,
        "nayin": nayin(year),
        "five_element_pattern": fep,
        "twelve_palaces": palaces,
    }


def profile_text(profile: Dict[str, Any]) -> str:
    """Format a structural profile as a Chinese text block for LLM prompts."""
    palaces = profile.get("twelve_palaces", {})
    palace_line = "、".join(f"{name}在{br}" for name, br in palaces.items())
    return f"""【七政四余结构事实】（由程序严格计算）
- 八字：{profile.get('chart')}
- 日主：{profile.get('day_master')}
- 年柱纳音：{profile.get('nayin')}（五行局：{profile.get('five_element_pattern')}）
- 命宫：{profile.get('life_palace')}
- 身宫：{profile.get('body_palace')}
- 身主：{profile.get('body_lord')}
- 十二宫排布：{palace_line}"""


def start_age_from_pattern(element_pattern: str) -> int:
    """Return the starting age for a given five-element pattern.

    Traditional Qi Zheng Si Yu maps the pattern to a starting age:
    水=2, 木=3, 金=4, 土=5, 火=6.
    """
    return _ELEMENT_START_AGE.get(element_pattern, 3)


def _dayun_direction(year_stem: str, gender: str) -> bool:
    """Return True if the dayun should proceed forward through palaces.

    Rule: 阳男阴女顺行，阴男阳女逆行.
    """
    yang = year_stem in _YANG_STEMS
    male = gender == "male"
    return (yang and male) or (not yang and not male)


def dayun_list(
    chart: str,
    gender: str,
    *,
    until_age: int = 80,
) -> List[Dict[str, Any]]:
    """Return the ten-year DaYun periods for a Qi Zheng chart.

    The dayun starts from the life palace, advances one palace every ten
    years, and follows the traditional forward/backward rule based on the
    year stem and gender.

    Each entry contains:
        - index: period index
        - palace: Chinese palace name
        - pillar: palace branch (地支)
        - start_age / end_age: inclusive age range
    """
    profile = structural_profile(chart)
    if profile is None:
        return []

    year_stem = _stem(profile["year_pillar"])
    life_palace_branch = profile["life_palace"]
    pattern = profile["five_element_pattern"]

    start_age = start_age_from_pattern(pattern)
    forward = _dayun_direction(year_stem, gender)

    palaces = twelve_palaces(life_palace_branch)
    palace_order = list(palaces.items())
    if not forward:
        # Keep 命宫 as the starting point, then proceed in reverse order.
        palace_order = [palace_order[0]] + palace_order[:0:-1]

    result: List[Dict[str, Any]] = []
    age = start_age
    i = 0
    while age < until_age:
        palace_name, branch = palace_order[i % 12]
        result.append(
            {
                "index": i,
                "palace": palace_name,
                "pillar": branch,
                "start_age": age,
                "end_age": age + 10,
                "start_year": None,
                "end_year": None,
            }
        )
        age += 10
        i += 1
    return result


def liunian_list(start_year: int, end_year: int) -> List[Dict[str, Any]]:
    """Return the yearly Liunian pillars for a range of years.

    Uses the same 60-year JiaZi cycle as bazi; the pillar is computed from
    the Gregorian year via a mid-year anchor to avoid Li Chun boundary issues.
    """
    from tools.bazi_ai.bazi_validator import JIAZI_PILLARS

    result: List[Dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        # Mid-year anchor avoids the Li Chun boundary.
        index = (year - 4) % 60
        pillar = JIAZI_PILLARS[index]
        result.append(
            {
                "year": year,
                "pillar": pillar,
                "stem": pillar[0],
                "branch": pillar[1],
            }
        )
    return result


def _branch_interaction(b1: str, b2: str) -> Optional[str]:
    """Describe the interaction between two branches."""
    pair = (b1, b2)
    if pair in _SIX_CHONG or pair[::-1] in _SIX_CHONG:
        return "冲"
    for he, element in _SIX_HE.items():
        if pair == he or pair[::-1] == he:
            return f"合({element})"
    return None


def yearly_relations(
    chart: str,
    dayun_pillar: str,
    liunian_pillar: str,
) -> Optional[Dict[str, Any]]:
    """Return structural relations between a chart, dayun branch, and liunian.

    This is a simplified version compared to bazi_structural.yearly_relations:
    it focuses on palace-branch interactions used in Qi Zheng Si Yu.
    """
    profile = structural_profile(chart)
    if profile is None:
        return None

    dayun_branch = dayun_pillar
    liunian_branch = liunian_pillar[1]
    life_palace_branch = profile["life_palace"]

    return {
        "dayun_pillar": dayun_pillar,
        "liunian_pillar": liunian_pillar,
        "dayun_branch": dayun_branch,
        "liunian_branch": liunian_branch,
        "dayun_life_palace_interaction": _branch_interaction(dayun_branch, life_palace_branch),
        "liunian_life_palace_interaction": _branch_interaction(liunian_branch, life_palace_branch),
        "dayun_liunian_interaction": _branch_interaction(dayun_branch, liunian_branch),
    }
