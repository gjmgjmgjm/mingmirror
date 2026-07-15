"""Aspect and pattern detection for Qi Zheng Si Yu (七政四余).

All calculations are purely geometric: they take the ecliptic longitudes
computed by `astronomy.py` and return human-readable aspects and classical
patterns.
"""

from typing import Dict, List, Optional

from tools.qizheng.star_tables import (
    ASPECTS,
    PALACE_LORD,
    PALACE_NAMES,
    PATTERN_CATALOG,
    SEVEN_GOVERNORS,
    angular_gap,
)


def compute_aspects(positions: Dict[str, float]) -> List[Dict[str, object]]:
    """Return major aspects between all pairs of bodies.

    *positions* maps body name to ecliptic longitude.
    """
    aspects: List[Dict[str, object]] = []
    bodies = list(positions.keys())
    for i, a in enumerate(bodies):
        for b in bodies[i + 1 :]:
            gap = angular_gap(positions[a], positions[b])
            for name, angle, orb, auspicious in ASPECTS:
                if abs(gap - angle) <= orb:
                    aspects.append(
                        {
                            "bodies": [a, b],
                            "aspect": name,
                            "angle": round(gap, 2),
                            "orb": round(abs(gap - angle), 2),
                            "auspicious": auspicious,
                        }
                    )
                    break
    return aspects


def _body_in_house(body_house: Dict[str, int], body: str, palace: str) -> bool:
    """Check whether *body* falls in the named palace."""
    if body not in body_house:
        return False
    return PALACE_NAMES[(body_house[body] - 1) % 12] == palace


def _houses_are_trine(h1: int, h2: int) -> bool:
    """Return True if two 1-based house indices are in trine (4 houses apart)."""
    return ((h1 - h2) % 12) in (4, 8)


def _houses_are_opposite(h1: int, h2: int) -> bool:
    return ((h1 - h2) % 12) == 6


def _houses_are_sextile(h1: int, h2: int) -> bool:
    return ((h1 - h2) % 12) in (2, 10)


def _palace_branch(palace_branches: Dict[str, str], palace: str) -> str:
    return palace_branches.get(palace, "")


def _lord_of_palace(palace_branches: Dict[str, str], palace: str) -> str:
    branch = _palace_branch(palace_branches, palace)
    return PALACE_LORD.get(branch, "")


def _body_in_palace(body_houses: Dict[str, int], body: str, palace: str) -> bool:
    return _body_in_house(body_houses, body, palace)


def _body_in_palaces(body_houses: Dict[str, int], body: str, palaces) -> bool:
    if body not in body_houses:
        return False
    return PALACE_NAMES[(body_houses[body] - 1) % 12] in palaces


def _is_strong(strength: str) -> bool:
    return strength in ("庙", "旺", "乐", "入垣升殿", "入垣", "升殿")


def detect_patterns(
    body_houses: Dict[str, int],
    body_positions: Dict[str, float],
    body_strengths: Optional[Dict[str, str]] = None,
    palace_branches: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Detect classical Qi Zheng patterns from body houses and longitudes.

    *body_strengths* maps body names to their combined strength label.
    *palace_branches* maps palace name to earthly branch for palace-lord checks.

    Returns a list of {"name": ..., "description": ...}.
    """
    body_strengths = body_strengths or {}
    palace_branches = palace_branches or {}
    patterns: List[Dict[str, str]] = []


    # 日月并明 / 日月拱照 / 日月合璧
    if "太阳" in body_positions and "太阴" in body_positions:
        sun_h = body_houses.get("太阳", 0)
        moon_h = body_houses.get("太阴", 0)
        gap = angular_gap(body_positions["太阳"], body_positions["太阴"])
        if gap < 10.0:
            patterns.append(
                {"name": "日月合璧", "description": PATTERN_CATALOG["日月合璧"]}
            )
        elif _houses_are_trine(sun_h, moon_h) or (110.0 <= gap <= 130.0):
            patterns.append(
                {"name": "日月拱照", "description": PATTERN_CATALOG["日月拱照"]}
            )
        elif _body_in_house(body_houses, "太阳", "命宫") or _body_in_house(
            body_houses, "太阴", "命宫"
        ):
            patterns.append(
                {"name": "日月并明", "description": PATTERN_CATALOG["日月并明"]}
            )

        # 君臣庆会：日月同宫或三合，且至少一个强状态
        if (
            _body_in_house(body_houses, "太阳", "命宫")
            or _body_in_house(body_houses, "太阴", "命宫")
            or _houses_are_trine(sun_h, moon_h)
            or _houses_are_opposite(sun_h, moon_h)
        ):
            if _is_strong(body_strengths.get("太阳", "")) or _is_strong(
                body_strengths.get("太阴", "")
            ):
                patterns.append(
                    {"name": "君臣庆会", "description": PATTERN_CATALOG["君臣庆会"]}
                )

    # 金水相生 / 金水会垣
    if "金星" in body_positions and "水星" in body_positions:
        venus_h = body_houses.get("金星", 0)
        mercury_h = body_houses.get("水星", 0)
        gap = angular_gap(body_positions["金星"], body_positions["水星"])
        if gap < 30.0:
            patterns.append(
                {"name": "金水相生", "description": PATTERN_CATALOG["金水相生"]}
            )
            # 金水会垣：同宫且地支在辰酉巳申
            if venus_h == mercury_h and palace_branches:
                branch = _palace_branch(palace_branches, PALACE_NAMES[(venus_h - 1) % 12])
                if branch in {"辰", "酉", "巳", "申"}:
                    patterns.append(
                        {"name": "金水会垣", "description": PATTERN_CATALOG["金水会垣"]}
                    )

    # 木火通明
    if "木星" in body_positions and "火星" in body_positions:
        jupiter_h = body_houses.get("木星", 0)
        mars_h = body_houses.get("火星", 0)
        gap = angular_gap(body_positions["木星"], body_positions["火星"])
        if gap < 30.0 or _houses_are_trine(jupiter_h, mars_h):
            patterns.append(
                {"name": "木火通明", "description": PATTERN_CATALOG["木火通明"]}
            )

    # 土金相生
    if "土星" in body_positions and "金星" in body_positions:
        saturn_h = body_houses.get("土星", 0)
        venus_h = body_houses.get("金星", 0)
        gap = angular_gap(body_positions["土星"], body_positions["金星"])
        if gap < 30.0 or _houses_are_trine(saturn_h, venus_h):
            patterns.append(
                {"name": "土金相生", "description": PATTERN_CATALOG["土金相生"]}
            )

    # 火土相刑 / 火土相刑
    if "火星" in body_positions and "土星" in body_positions:
        gap = angular_gap(body_positions["火星"], body_positions["土星"])
        if 170.0 <= gap <= 190.0:
            patterns.append(
                {"name": "火土相刑", "description": PATTERN_CATALOG["火土相刑"]}
            )

    # 木气朝垣（木星入命宫）
    if _body_in_house(body_houses, "木星", "命宫"):
        patterns.append(
            {"name": "木气朝垣", "description": PATTERN_CATALOG["木气朝垣"]}
        )

    # 官福朝拱：官禄、福德二宫主星三方或对照拱照命宫
    if palace_branches:
        guan_lord = _lord_of_palace(palace_branches, "官禄")
        fu_lord = _lord_of_palace(palace_branches, "福德")
        if guan_lord and fu_lord:
            guan_h = body_houses.get(guan_lord, 0)
            fu_h = body_houses.get(fu_lord, 0)
            if (_houses_are_trine(guan_h, 1) or _houses_are_opposite(guan_h, 1)) and (
                _houses_are_trine(fu_h, 1) or _houses_are_opposite(fu_h, 1)
            ):
                patterns.append(
                    {"name": "官福朝拱", "description": PATTERN_CATALOG["官福朝拱"]}
                )

    # 紫气临命 / 紫气朝垣
    if _body_in_house(body_houses, "紫气", "命宫"):
        patterns.append(
            {"name": "紫气临命", "description": PATTERN_CATALOG["紫气临命"]}
        )
    elif _body_in_house(body_houses, "紫气", "官禄"):
        patterns.append(
            {"name": "紫气朝垣", "description": PATTERN_CATALOG["紫气朝垣"]}
        )

    # 月孛守命
    if _body_in_house(body_houses, "月孛", "命宫"):
        patterns.append(
            {"name": "月孛守命", "description": PATTERN_CATALOG["月孛守命"]}
        )

    # 罗计夹命 / 罗计拦截：罗睺、计都分别在命宫前后一宫夹命
    if "罗睺" in body_houses and "计都" in body_houses:
        rh = body_houses["罗睺"]
        jd = body_houses["计都"]
        ming = 1  # 命宫固定为第 1 宫
        if (abs((rh - ming) % 12) == 11 and abs((jd - ming) % 12) == 1) or (
            abs((rh - ming) % 12) == 1 and abs((jd - ming) % 12) == 11
        ):
            patterns.append(
                {"name": "罗计夹命", "description": PATTERN_CATALOG["罗计夹命"]}
            )
            patterns.append(
                {"name": "罗计拦截", "description": PATTERN_CATALOG["罗计拦截"]}
            )

    # 五星连珠：七政中任意三星同宫
    governor_houses = {b: body_houses[b] for b in SEVEN_GOVERNORS if b in body_houses}
    house_counts: Dict[int, List[str]] = {}
    for b, h in governor_houses.items():
        house_counts.setdefault(h, []).append(b)
    for h, stars in house_counts.items():
        if len(stars) >= 3:
            palace = PALACE_NAMES[(h - 1) % 12]
            patterns.append(
                {
                    "name": "五星连珠",
                    "description": f"{'、'.join(stars)}聚于{palace}，能量集中",
                }
            )

    # 土计掩月
    if (
        "土星" in body_houses
        and "计都" in body_houses
        and "太阴" in body_houses
    ):
        if body_houses["土星"] == body_houses["太阴"] and body_houses["计都"] in (
            body_houses["太阴"],
            (body_houses["太阴"] + 6 - 1) % 12 + 1,
        ):
            patterns.append(
                {"name": "土计掩月", "description": PATTERN_CATALOG["土计掩月"]}
            )

    return patterns
