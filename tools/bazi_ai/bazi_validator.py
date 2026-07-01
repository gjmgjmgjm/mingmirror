#!/usr/bin/env python3
"""
bazi_validator.py — validate and normalize 八字 (four-pillar) strings.

A valid bazi must:
    1. Contain exactly four pillars.
    2. Each pillar must be a real combination from the 60 JiaZi cycle.
    3. Pillars appear in year/month/day/hour order.

This module is intentionally separate from the OCR extractor so that the
AI engine and case builder can reject garbage input before spending tokens
or polluting the retrieval index.
"""

import re
from typing import List, Optional, Tuple

STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# The 60 valid sexagenary pillars, in traditional JiaZi order.
JIAZI_PILLARS: Tuple[str, ...] = tuple(
    STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)
)
VALID_PILLARS = set(JIAZI_PILLARS)

_PILLAR_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")


def is_valid_pillar(pillar: str) -> bool:
    """Return True if *pillar* is one of the 60 valid stem-branch pairs."""
    return len(pillar) == 2 and pillar in VALID_PILLARS


def normalize_bazi(bazi: Optional[str]) -> Optional[str]:
    """Normalize spacing and return a canonical ``年 月 日 时`` string.

    Returns None if the input does not contain four valid pillars.
    """
    if not bazi or not isinstance(bazi, str):
        return None
    pillars = _PILLAR_RE.findall(bazi)
    if len(pillars) != 4:
        return None
    if not all(is_valid_pillar(p) for p in pillars):
        return None
    return " ".join(pillars)


def validate_bazi(bazi: Optional[str]) -> bool:
    """Return True if *bazi* is a syntactically valid four-pillar chart."""
    return normalize_bazi(bazi) is not None


def extract_pillars(bazi: str) -> List[str]:
    """Extract the four valid pillars from *bazi*.

    Raises ValueError if the input is not a valid four-pillar string.
    """
    normalized = normalize_bazi(bazi)
    if normalized is None:
        raise ValueError(f"无效的八字：{bazi!r}")
    return normalized.split()


def day_master(bazi: str) -> Optional[str]:
    """Return the day stem (日主) of a valid bazi, or None if invalid."""
    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return None
    return pillars[2][0]


def month_branch(bazi: str) -> Optional[str]:
    """Return the month branch (月令) of a valid bazi, or None if invalid."""
    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return None
    return pillars[1][1]
