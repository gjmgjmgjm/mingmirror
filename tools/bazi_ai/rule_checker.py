#!/usr/bin/env python3
"""
rule_checker.py — lightweight rule-based sanity checks for bazi analysis output.

This module guards against obvious LLM hallucinations by verifying that the
reported day-master strength, useful gods, and taboo gods are consistent with
basic bazi theory (seasonal strength, five-element relationships).
"""

from typing import Dict, List, Optional, Tuple

from tools.bazi_ai.bazi_validator import extract_pillars

# 天干 -> (阴阳, 五行)
STEM_ATTR = {
    "甲": (0, "木"),
    "乙": (1, "木"),
    "丙": (0, "火"),
    "丁": (1, "火"),
    "戊": (0, "土"),
    "己": (1, "土"),
    "庚": (0, "金"),
    "辛": (1, "金"),
    "壬": (0, "水"),
    "癸": (1, "水"),
}

# 地支 -> 五行（本气）
BRANCH_ELEM = {
    "子": "水",
    "丑": "土",
    "寅": "木",
    "卯": "木",
    "辰": "土",
    "巳": "火",
    "午": "火",
    "未": "土",
    "申": "金",
    "酉": "金",
    "戌": "土",
    "亥": "水",
}

# 月令季节旺衰：地支 -> 日主五行的当令状态
# strong = 月令生助日主五行，weak = 月令克泄耗日主五行
SEASONAL_STRENGTH: Dict[str, Dict[str, str]] = {
    # 木旺于春
    "寅": {"木": "strong", "火": "medium", "土": "weak", "金": "weak", "水": "medium"},
    "卯": {"木": "strong", "火": "medium", "土": "weak", "金": "weak", "水": "medium"},
    # 火旺于夏
    "巳": {"火": "strong", "土": "medium", "金": "weak", "水": "weak", "木": "medium"},
    "午": {"火": "strong", "土": "medium", "金": "weak", "水": "weak", "木": "medium"},
    # 金旺于秋
    "申": {"金": "strong", "水": "medium", "木": "weak", "火": "weak", "土": "medium"},
    "酉": {"金": "strong", "水": "medium", "木": "weak", "火": "weak", "土": "medium"},
    # 水旺于冬
    "子": {"水": "strong", "木": "medium", "火": "weak", "土": "weak", "金": "medium"},
    "亥": {"水": "strong", "木": "medium", "火": "weak", "土": "weak", "金": "medium"},
    # 土旺于四季
    "辰": {"土": "strong", "金": "medium", "水": "weak", "木": "weak", "火": "medium"},
    "戌": {"土": "strong", "金": "medium", "水": "weak", "木": "weak", "火": "medium"},
    "丑": {"土": "strong", "金": "medium", "水": "weak", "木": "weak", "火": "medium"},
    "未": {"土": "strong", "火": "medium", "木": "weak", "金": "weak", "水": "medium"},
}

# 五行生克
PRODUCE = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONQUER = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def _element_relation(god_elem: str, day_elem: str) -> str:
    """Return 'produce', 'conquer', 'produced_by', 'conquered_by', or 'same'."""
    if god_elem == day_elem:
        return "same"
    if PRODUCE.get(day_elem) == god_elem:
        return "produce"
    if CONQUER.get(day_elem) == god_elem:
        return "conquer"
    if PRODUCE.get(god_elem) == day_elem:
        return "produced_by"
    if CONQUER.get(god_elem) == day_elem:
        return "conquered_by"
    return "neutral"


def check_day_master_strength(bazi: str, claimed_strength: Optional[str]) -> List[str]:
    """Check whether claimed day-master strength aligns with seasonal strength."""
    warnings = []
    if not claimed_strength:
        return warnings

    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return warnings

    day_stem = pillars[2][0]
    month_branch = pillars[1][1]
    day_elem = STEM_ATTR.get(day_stem, (None, None))[1]
    seasonal = SEASONAL_STRENGTH.get(month_branch, {}).get(day_elem)

    if seasonal == "strong" and claimed_strength in ("身弱", "从弱"):
        warnings.append(
            f"日主{day_stem}（{day_elem}）生于{month_branch}月当令，标注为{claimed_strength}可能偏低"
        )
    elif seasonal == "weak" and claimed_strength in ("身强", "从旺"):
        warnings.append(
            f"日主{day_stem}（{day_elem}）生于{month_branch}月失令，标注为{claimed_strength}可能偏高"
        )
    return warnings


def check_useful_gods(bazi: str, useful_gods: List[str], taboo_gods: List[str]) -> List[str]:
    """Check that useful/taboo gods roughly follow five-element logic."""
    warnings = []
    if not useful_gods or not taboo_gods:
        return warnings

    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return warnings

    day_stem = pillars[2][0]
    day_elem = STEM_ATTR.get(day_stem, (None, None))[1]

    for god in useful_gods:
        god_elem = STEM_ATTR.get(god, (None, None))[1]
        if not god_elem:
            continue
        rel = _element_relation(god_elem, day_elem)
        # 用神通常应是生助日主（印比）或制化忌神（食伤财官适度）
        if rel in ("conquer", "conquered_by"):
            warnings.append(f"用神 {god}（{god_elem}）与日主 {day_stem}（{day_elem}）为克耗关系，请复核")

    for god in taboo_gods:
        god_elem = STEM_ATTR.get(god, (None, None))[1]
        if not god_elem:
            continue
        rel = _element_relation(god_elem, day_elem)
        if rel == "same":
            warnings.append(f"忌神 {god} 与日主 {day_stem} 同五行，通常不应为忌")

    return warnings


def check_analysis(result: Dict) -> Tuple[Dict, List[str]]:
    """Return (sanitized_result, warnings). Adds a `rule_warnings` field."""
    bazi = result.get("basic_info", {}).get("bazi", "")
    if not bazi:
        return result, []

    basic = result.get("basic_info", {})
    warnings = []
    warnings.extend(check_day_master_strength(bazi, basic.get("day_master_strength")))
    warnings.extend(check_useful_gods(bazi, basic.get("useful_gods", []), basic.get("taboo_gods", [])))

    if warnings:
        result["rule_warnings"] = warnings
    return result, warnings
