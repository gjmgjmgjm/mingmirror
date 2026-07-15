#!/usr/bin/env python3
"""穷通宝鉴 (Qióng Tōng Bǎo Jiàn) 调候用神 gold reference.

This is the authoritative classical source for 调候 (climate-regulation) 用神 —
independent of our own rule engine, so it can serve as a **real accuracy gold**
(not just consistency) for the 用神 layer.

Encoded from the 穷通宝鉴 core thesis (sourced, not from memory):
  - Seasonal 调候: 夏月(巳午未)离不开癸水(润)，冬月(亥子丑)离不开丙火(暖)。
  - Day-master 喜用配对 (穷通宝鉴「与十日干关系最密切的天干」):
      甲—庚、丁   乙—丙、癸   丙—壬       丁—甲、庚
      戊—甲、丙、癸   己—甲、丙、癸   庚—丁、甲
      辛—壬、甲   壬—庚(辛)   癸—辛(庚)

Source: 《穷通宝鉴》之调候喜用 (https://zhuanlan.zhihu.com/p/632927242),
原文见 ctext.org 窮通寶鑒。This is the CORE 调候 principle; the full
month-by-month 穷通宝鉴 adds further nuance not encoded here (flagged in
`coverage`). Stem 喜用 mapped to 五行 elements for comparison.

NOTE: 调候 is ONE dimension of 用神 (climate), not the whole 用神 determination.
A 用神 that matches this gold is sound on 调候 grounds; a mismatch may still be
defensible on 扶抑/通关 grounds. So this ruler measures **调候一致性**, a strong
but not complete accuracy signal.
"""
from __future__ import annotations

from typing import Set

# Day-master stem → its 穷通宝鉴 喜用 stems (converted to 五行 elements below).
_DM_PAIR_STEMS = {
    "甲": ("庚", "丁"),
    "乙": ("丙", "癸"),
    "丙": ("壬",),
    "丁": ("甲", "庚"),
    "戊": ("甲", "丙", "癸"),
    "己": ("甲", "丙", "癸"),
    "庚": ("丁", "甲"),
    "辛": ("壬", "甲"),
    "壬": ("庚",),   # 辛 secondary
    "癸": ("辛",),   # 庚 secondary
}

_STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

# Seasonal 调候: warm/dry months need 水; cold/wet months need 火.
_SUMMER = {"巳", "午", "未"}   # 火旺暖燥 → 润以癸水
_WINTER = {"亥", "子", "丑"}   # 水旺寒湿 → 暖以丙火

coverage = (
    "CORE 穷通宝鉴 调候 (seasonal 寒暖 + day-master 喜用配对). "
    "Full month-by-month nuance (e.g. 甲辰用庚丁壬、庚申用丁甲加丙) NOT encoded. "
    "Measures 调候一致性 only."
)


def tiaohou_yongshen(day_master: str, month_branch: str) -> Set[str]:
    """Return the 穷通宝鉴 调候用神 as a set of 五行 elements.

    = day-master 喜用 elements ∪ seasonal 调候 element.
    """
    gold: Set[str] = set()
    for s in _DM_PAIR_STEMS.get(day_master, ()):
        el = _STEM_ELEMENT.get(s)
        if el:
            gold.add(el)
    if month_branch in _SUMMER:
        gold.add("水")
    elif month_branch in _WINTER:
        gold.add("火")
    return gold


def tiaohou_yongshen_stems(day_master: str, month_branch: str) -> Set[str]:
    """Same, but returns the canonical 喜用 STEMS (for human-readable output)."""
    stems = set(_DM_PAIR_STEMS.get(day_master, ()))
    if month_branch in _SUMMER:
        stems.add("癸")  # 雨露润之
    elif month_branch in _WINTER:
        stems.add("丙")  # 太阳暄之
    return stems
