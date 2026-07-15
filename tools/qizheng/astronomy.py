"""Astronomical calculations for Qi Zheng Si Yu (七政四余).

This module wraps the Swiss Ephemeris (`pyswisseph`) to compute the real
positions of the seven governors, four remainders, the ascendant, the midheaven
and the twelve houses.  It is kept intentionally free of interpretation logic;
see `star_tables.py` and `patterns.py` for that.

`pyswisseph` is an optional dependency.  If it is not installed, every
function that needs ephemeris data raises ``ImportError`` with installation
instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import tools.qizheng.star_tables as star_tables
from tools.qizheng.star_tables import (
    ALL_BODIES,
    EARTHLY_BRANCHES,
    PALACE_LORD,
    PALACE_NAMES,
    SEVEN_GOVERNORS,
    ZODIAC_SIGNS,
    ZODIAC_TO_BRANCH,
    body_dignity,
    mansion_for_degree,
    twelve_palaces,
)

# Supported precession modes.  The offset is the ayanamsha value to subtract
# from tropical longitude to obtain sidereal longitude for 28-mansion mapping.
PRECESSION_MODES: Tuple[str, ...] = (
    "tropical",
    "sidereal_lahiri",
    "sidereal_fagan_bradley",
    "sidereal_raman",
    "sidereal_de_luce",
)


class SwissEphMissingError(ImportError):
    """Raised when pyswisseph is required but not installed."""

    def __init__(self) -> None:
        super().__init__(
            "七政四余天文计算需要安装 pyswisseph。"
            "请运行：pip install -r requirements-qizheng.txt"
        )


def _swe() -> Any:
    try:
        import swisseph as swe  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SwissEphMissingError() from exc
    return swe


def _normalize_degree(degree: float) -> float:
    """Normalise an ecliptic longitude to [0, 360)."""
    degree = degree % 360.0
    if degree < 0.0:
        degree += 360.0
    return degree


def julian_day_ut(dt_utc: datetime) -> float:
    """Return the Julian Day in UT for a UTC datetime."""
    swe = _swe()
    return float(
        swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                   dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)
    )


def _to_utc(
    dt: datetime,
    timezone_offset_hours: Optional[float] = None,
) -> datetime:
    """Convert a datetime to UTC.

    If *dt* already has tzinfo, it is converted directly and the offset is
    ignored.  Otherwise *dt* is treated as local time with the supplied offset
    (default +8, 东八区).
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    offset = timezone_offset_hours if timezone_offset_hours is not None else 8.0
    return dt - timedelta(hours=offset)


def _precession_offset(jd_ut: float, mode: str) -> float:
    """Return the ayanamsha offset for the given precession *mode*.

    ``tropical`` returns 0.  Sidereal modes use ``pyswisseph``'s ayanamsha
    calculation.  Unknown modes fall back to tropical.

    Note: this version of ``pyswisseph`` requires setting the sidereal mode
    globally with ``set_sid_mode`` before reading the ayanamsha.
    """
    if mode == "tropical":
        return 0.0
    swe = _swe()
    sidm = {
        "sidereal_lahiri": getattr(swe, "SIDM_LAHIRI", 1),
        "sidereal_fagan_bradley": getattr(swe, "SIDM_FAGAN_BRADLEY", 0),
        "sidereal_raman": getattr(swe, "SIDM_RAMAN", 3),
        "sidereal_de_luce": getattr(swe, "SIDM_DE_LUCE", 4),
    }.get(mode)
    if sidm is None:
        return 0.0
    swe.set_sid_mode(sidm)
    return float(swe.get_ayanamsa(jd_ut))


def zodiac_sign(degree: float) -> str:
    """Return the Chinese zodiac sign name for a tropical longitude."""
    return ZODIAC_SIGNS[int(_normalize_degree(degree) / 30.0) % 12]


def _house_index(degree: float, cusps: List[float]) -> int:
    """Return the 1-based house index containing *degree*.

    *cusps* must contain 12 cusp longitudes (index 0..11).  This mirrors the
    house-finding logic used by Moira: houses may wrap across 0°.
    """
    degree = _normalize_degree(degree)
    last = _normalize_degree(cusps[-1])
    for i, cusp in enumerate(cusps):
        pos = _normalize_degree(cusp)
        if pos > last:
            # normal forward house
            if last <= degree < pos:
                return i + 1
        else:
            # house wraps across 0°
            if degree >= last or degree < pos:
                return i + 1
        last = pos
    # Fallback: should not happen for valid cusps.
    return 1


def compute_houses(jd_ut: float, latitude: float, longitude: float) -> List[float]:
    """Return the 12 house cusp longitudes using the Placidus system."""
    swe = _swe()
    cusps, _ = swe.houses(jd_ut, latitude, longitude, b"P")
    # swe.houses returns a sequence where index 0 is usually 0.0 and the
    # actual 12 cusps are at indices 1..12.  Normalise to a plain 12-list.
    if len(cusps) >= 13:
        return [_normalize_degree(float(cusps[i])) for i in range(1, 13)]
    return [_normalize_degree(float(v)) for v in cusps[:12]]


def compute_asc_mc(jd_ut: float, latitude: float, longitude: float) -> Tuple[float, float]:
    """Return (ascendant, midheaven) in tropical longitude."""
    swe = _swe()
    _, ascmc = swe.houses(jd_ut, latitude, longitude, b"P")
    return (_normalize_degree(float(ascmc[0])),
            _normalize_degree(float(ascmc[1])))


@dataclass(frozen=True)
class BodyInfo:
    name: str
    longitude: float
    zodiac: str
    mansion: str
    house: int
    element: str
    auspicious: str
    dignity: str  # 庙/旺/乐/陷/得地/平
    rulership: str  # 入垣 / 不入垣
    exaltation: str  # 升殿 / 不升殿
    strength: str  # 综合强弱
    speed: float  # daily motion in degrees
    speed_state: str  # 顺行 / 逆行 / 留
    is_retrograde: bool


_BODY_TO_SWE = {
    "太阳": "SUN",
    "太阴": "MOON",
    "水星": "MERCURY",
    "金星": "VENUS",
    "火星": "MARS",
    "木星": "JUPITER",
    "土星": "SATURN",
}

# 紫气授时历算法常数（参考 research/qizheng-ref/src/four_remnants.py）
_JD_EPOCH_ZIQI = 2188918.5622222223
_ZIQI_NU_START = 108.49
_ZIQI_DEGREE_IN_STAR = 2.0
_ZIQI_ANNUAL_DEGREE = 13.050460
_ZIQI_DAILY_DEGREE = _ZIQI_ANNUAL_DEGREE / 365.2425
_ZIQI_MODERN_RATIO = 360.0 / 365.25


def _compute_ziqi_longitude(jd_ut: float) -> float:
    """Return the longitude of 紫气 using the Shoushi-li algorithm.

    This matches the reference implementation in ``research/qizheng-ref``:
    epoch at 1280-12-14 01:29:36 UTC, 紫气 at 女宿2度, period 28 years.
    """
    epoch_pos = _ZIQI_NU_START + _ZIQI_DEGREE_IN_STAR
    days_elapsed = jd_ut - _JD_EPOCH_ZIQI
    total_ancient_deg = epoch_pos + days_elapsed * _ZIQI_DAILY_DEGREE
    modern_deg = (total_ancient_deg * _ZIQI_MODERN_RATIO) % 360.0
    return modern_deg


def _compute_body_longitude(jd_ut: float, body: str) -> Tuple[float, float]:
    """Return (longitude, daily_speed) for a named body.

    The four remainders are derived from the lunar node/apogee, except 紫气
    which uses the traditional Shoushi-li algorithm.
    """
    swe = _swe()
    if body == "罗睺":
        res = swe.calc_ut(jd_ut, swe.TRUE_NODE)
        lon = float(res[0][0])
        return lon, float(res[0][3])
    if body == "计都":
        lon, _ = _compute_body_longitude(jd_ut, "罗睺")
        return _normalize_degree(lon + 180.0), 0.0
    if body == "月孛":
        res = swe.calc_ut(jd_ut, swe.MEAN_APOG)
        lon = float(res[0][0])
        return lon, float(res[0][3])
    if body == "紫气":
        return _compute_ziqi_longitude(jd_ut), 0.0

    attr = _BODY_TO_SWE.get(body)
    if attr is None:  # pragma: no cover
        raise ValueError(f"Unknown body: {body}")
    swe_body = getattr(swe, attr)
    res = swe.calc_ut(jd_ut, swe_body)
    return float(res[0][0]), float(res[0][3])


def _speed_state(speed: float) -> Tuple[str, bool]:
    """Return (speed_state, is_retrograde)."""
    if abs(speed) < 0.05:
        return "留", False
    if speed < 0.0:
        return "逆行", True
    return "顺行", False


def compute_bodies(
    jd_ut: float,
    latitude: float,
    longitude: float,
    precession_offset: float = 0.0,
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Dict[str, BodyInfo]:
    """Compute positions of all seven governors and four remainders."""
    cusps = compute_houses(jd_ut, latitude, longitude)
    ascendant_branch = ZODIAC_TO_BRANCH.get(zodiac_sign(cusps[0]), "子")
    palace_branches = twelve_palaces(ascendant_branch)
    result: Dict[str, BodyInfo] = {}
    for body in ALL_BODIES:
        lon, speed = _compute_body_longitude(jd_ut, body)
        lon = _normalize_degree(lon)
        zodiac = zodiac_sign(lon)
        mansion = mansion_for_degree(lon, precession_offset)
        house = _house_index(lon, cusps)
        element = star_tables.BODY_ELEMENT[body]
        auspicious = star_tables.BODY_AUSPICIOUS[body]
        dignity = "平"
        rulership = "不入垣"
        exaltation = "不升殿"
        strength = "平"
        if body in SEVEN_GOVERNORS:
            palace_name = PALACE_NAMES[(house - 1) % 12]
            branch = palace_branches.get(palace_name, EARTHLY_BRANCHES[(house - 1) % 12])
            dignity = body_dignity(body, branch, dignity_table)
            rulership = star_tables.body_rulership(body, branch)
            exaltation = star_tables.body_exaltation(body, mansion)
            strength = star_tables.body_strength(body, branch, mansion, dignity_table)
        speed_state, retro = _speed_state(speed)
        result[body] = BodyInfo(
            name=body,
            longitude=lon,
            zodiac=zodiac,
            mansion=mansion,
            house=house,
            element=element,
            auspicious=auspicious,
            dignity=dignity,
            rulership=rulership,
            exaltation=exaltation,
            strength=strength,
            speed=speed,
            speed_state=speed_state,
            is_retrograde=retro,
        )
    return result


@dataclass(frozen=True)
class HouseInfo:
    index: int  # 1-based
    cusp: float
    zodiac: str
    mansion: str
    palace: str  # 命宫/财帛/... when the ascendant is house 1
    lord: str  # 宫主星


def compute_house_info(
    jd_ut: float,
    latitude: float,
    longitude: float,
    palace_names: Optional[List[str]] = None,
    precession_offset: float = 0.0,
) -> List[HouseInfo]:
    """Return the 12 houses enriched with zodiac, mansion and palace data."""
    names = palace_names or PALACE_NAMES
    cusps = compute_houses(jd_ut, latitude, longitude)
    ascendant_branch = ZODIAC_TO_BRANCH.get(zodiac_sign(cusps[0]), "子")
    palace_branches = twelve_palaces(ascendant_branch)
    houses: List[HouseInfo] = []
    for i, cusp in enumerate(cusps, start=1):
        palace = names[(i - 1) % 12]
        branch = palace_branches.get(palace, EARTHLY_BRANCHES[(i - 1) % 12])
        houses.append(
            HouseInfo(
                index=i,
                cusp=cusp,
                zodiac=zodiac_sign(cusp),
                mansion=mansion_for_degree(cusp, precession_offset),
                palace=palace,
                lord=PALACE_LORD[branch],
            )
        )
    return houses


def astro_profile(
    birth_datetime: datetime,
    latitude: float,
    longitude: float,
    timezone_offset_hours: Optional[float] = None,
    precession_mode: str = "tropical",
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Dict[str, Any]:
    """Return a full astronomical profile for a birth datetime and location.

    *precession_mode* controls how the 28 lunar mansions are mapped:

    - ``tropical`` (default): no precession correction.
    - ``sidereal_lahiri`` / ``sidereal_fagan_bradley`` / ``sidereal_raman`` /
      ``sidereal_de_luce``: subtract the corresponding ayanamsha before
      looking up the mansion.

    *dignity_table* selects the planetary dignity tradition.  Defaults to the
    built-in ``MIAO_WANG`` table; pass ``MIAO_WANG_YANG`` for the Yang
    Guozheng school table.

    Zodiac signs and house cusps remain tropical; only the 28-mansion lookup
    is affected by this switch.

    The returned dictionary is serialisable and intended to be passed into the
    LLM prompts as the single source of astrological truth.
    """
    utc_dt = _to_utc(birth_datetime, timezone_offset_hours)
    jd_ut = julian_day_ut(utc_dt)
    offset = _precession_offset(jd_ut, precession_mode)
    asc, mc = compute_asc_mc(jd_ut, latitude, longitude)
    houses = compute_house_info(jd_ut, latitude, longitude, precession_offset=offset)
    bodies = compute_bodies(
        jd_ut,
        latitude,
        longitude,
        precession_offset=offset,
        dignity_table=dignity_table,
    )

    body_dict: Dict[str, Dict[str, Any]] = {}
    for name, info in bodies.items():
        body_dict[name] = {
            "longitude": round(info.longitude, 4),
            "zodiac": info.zodiac,
            "mansion": info.mansion,
            "house": info.house,
            "element": info.element,
            "auspicious": info.auspicious,
            "dignity": info.dignity,
            "rulership": info.rulership,
            "exaltation": info.exaltation,
            "strength": info.strength,
            "speed": round(info.speed, 4),
            "speed_state": info.speed_state,
            "is_retrograde": info.is_retrograde,
            "house_palace": star_tables.PALACE_NAMES[(info.house - 1) % 12],
        }

    house_dict: List[Dict[str, Any]] = []
    for h in houses:
        house_dict.append(
            {
                "index": h.index,
                "cusp": round(h.cusp, 4),
                "zodiac": h.zodiac,
                "mansion": h.mansion,
                "palace": h.palace,
                "lord": h.lord,
            }
        )

    return {
        "birth_datetime_local": birth_datetime.isoformat(),
        "birth_datetime_utc": utc_dt.isoformat(),
        "timezone_offset_hours": timezone_offset_hours,
        "precession_mode": precession_mode,
        "precession_offset_degrees": round(offset, 4),
        "location": {"latitude": latitude, "longitude": longitude},
        "julian_day_ut": jd_ut,
        "ascendant": round(asc, 4),
        "ascendant_zodiac": zodiac_sign(asc),
        "ascendant_mansion": mansion_for_degree(asc, offset),
        "midheaven": round(mc, 4),
        "midheaven_zodiac": zodiac_sign(mc),
        "midheaven_mansion": mansion_for_degree(mc, offset),
        "houses": house_dict,
        "bodies": body_dict,
    }


