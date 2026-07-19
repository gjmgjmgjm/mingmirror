#!/usr/bin/env python3
"""
calendar.py — Gregorian / lunar → 八字 pillar conversion.

Uses the `sxtwl` library for accurate solar-term-based month pillars and
lunar-to-solar conversion. Falls back to a simplified approximation only when
`sxtwl` is not installed.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from tools.bazi_ai.bazi_validator import BRANCHES, JIAZI_PILLARS, STEMS

_JIE_INDICES = {1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23}

try:
    import sxtwl

    _SXTWL_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    sxtwl = None  # type: ignore
    _SXTWL_AVAILABLE = False

STEM_ELEMENTS: Dict[str, str] = {
    "甲": "wood",
    "乙": "wood",
    "丙": "fire",
    "丁": "fire",
    "戊": "earth",
    "己": "earth",
    "庚": "metal",
    "辛": "metal",
    "壬": "water",
    "癸": "water",
}

BRANCH_ELEMENTS: Dict[str, str] = {
    "子": "water",
    "丑": "earth",
    "寅": "wood",
    "卯": "wood",
    "辰": "earth",
    "巳": "fire",
    "午": "fire",
    "未": "earth",
    "申": "metal",
    "酉": "metal",
    "戌": "earth",
    "亥": "water",
}

_ELEMENT_LABELS = {
    "wood": "木",
    "fire": "火",
    "earth": "土",
    "metal": "金",
    "water": "水",
}

_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# Reference: 1900-01-31 is taken as 甲戌日 (JiaXu). This anchor is consistent
# with several perpetual-calendar tables. The day pillar cycles every 60 days.
_REFERENCE_DATE = date(1900, 1, 31)
_REFERENCE_DAY_INDEX = JIAZI_PILLARS.index("甲戌")


def _gz_to_pillar(gz) -> str:
    return _GAN[gz.tg] + _ZHI[gz.dz]


def _sxtwl_day(d: date):
    if not _SXTWL_AVAILABLE:
        raise RuntimeError("sxtwl is not installed")
    return sxtwl.fromSolar(d.year, d.month, d.day)


def day_pillar(d: date) -> str:
    """Return the day pillar (e.g. 甲戌) for a Gregorian date."""
    if _SXTWL_AVAILABLE:
        return _gz_to_pillar(_sxtwl_day(d).getDayGZ())
    days = (d - _REFERENCE_DATE).days
    index = (days + _REFERENCE_DAY_INDEX) % 60
    return JIAZI_PILLARS[index]


def year_pillar(d: date) -> str:
    """Return the year pillar for a Gregorian date."""
    if _SXTWL_AVAILABLE:
        return _gz_to_pillar(_sxtwl_day(d).getYearGZ())
    year = d.year
    if d.month < 2 or (d.month == 2 and d.day < 4):
        year -= 1
    stem = STEMS[(year - 4) % 10]
    branch = BRANCHES[(year - 4) % 12]
    return stem + branch


def month_pillar(d: date) -> str:
    """Return the month pillar for a Gregorian date."""
    if _SXTWL_AVAILABLE:
        return _gz_to_pillar(_sxtwl_day(d).getMonthGZ())
    month_branch = BRANCHES[(d.month + 1) % 12]
    year_stem_index = STEMS.index(year_pillar(d)[0])
    month_stem_start = [2, 14, 26, 8, 20, 32, 4, 16, 28, 0][year_stem_index]
    month_stem = STEMS[(month_stem_start + d.month - 1) % 10]
    return month_stem + month_branch


def hour_pillar(dt: datetime) -> str:
    """Return the hour pillar for a Gregorian datetime.

    When late-子时归次日 is enabled, the day stem used for 五鼠遁 must match
    the (possibly next-day) day pillar — not the civil calendar date alone.
    """
    if _SXTWL_AVAILABLE:
        # sxtwl.getShiGz already treats hour>=23 with next-day stem semantics.
        day = _sxtwl_day(dt.date())
        return _gz_to_pillar(sxtwl.getShiGz(day.getDayGZ().tg, dt.hour))
    hour = dt.hour
    branch_index = ((hour + 1) // 2) % 12
    branch = BRANCHES[branch_index]
    day_date = dt.date()
    if _ZI_HOUR_NEXT_DAY and hour >= 23:
        from datetime import timedelta

        day_date = day_date + timedelta(days=1)
    day_stem = day_pillar(day_date)[0]
    day_stem_index = STEMS.index(day_stem)
    start_index = (day_stem_index % 5) * 2
    stem = STEMS[(start_index + branch_index) % 10]
    return stem + branch


def lunar_to_solar(
    lunar_year: int, lunar_month: int, lunar_day: int, leap: bool = False
) -> date:
    """Convert a lunar date to the corresponding Gregorian date."""
    if not _SXTWL_AVAILABLE:
        raise RuntimeError("sxtwl is required for lunar conversion")
    lunar = sxtwl.fromLunar(lunar_year, lunar_month, lunar_day, leap)
    return date(lunar.getSolarYear(), lunar.getSolarMonth(), lunar.getSolarDay())


def solar_to_lunar(d: date) -> Tuple[int, int, int, bool]:
    """Convert a Gregorian date to the corresponding lunar date."""
    if not _SXTWL_AVAILABLE:
        raise RuntimeError("sxtwl is required for lunar conversion")
    solar = _sxtwl_day(d)
    return (
        solar.getLunarYear(),
        solar.getLunarMonth(),
        solar.getLunarDay(),
        solar.isLunarLeap(),
    )


def pillars_for_date(d: date) -> Dict[str, str]:
    """Return year/month/day pillars for a Gregorian date."""
    return {
        "year": year_pillar(d),
        "month": month_pillar(d),
        "day": day_pillar(d),
    }


# 子时（23:00-24:00）日柱取次日的 convention toggle.
# False = 早子时仍属当日（日柱不变，日界在 00:00）；
# True（默认）= 日柱在 23:00 子时即进入次日（与 iztro / MingLi-Bench / 多数现代排盘一致）。
# 两种各有命理依据；默认采用 True，与赛事 gold 及主流排盘对齐。
# 历史：曾默认 False（保守当日），validate_chart ruler 发现该默认与 iztro/MingLi
# 在所有子时命例上系统性分歧（如 case_9 23:15、case_28 23:34），故改为 True。
_ZI_HOUR_NEXT_DAY = True


def set_zi_hour_next_day(enabled: bool) -> None:
    global _ZI_HOUR_NEXT_DAY
    _ZI_HOUR_NEXT_DAY = bool(enabled)


def pillars_for_datetime(dt: datetime) -> Dict[str, str]:
    """Return year/month/day/hour pillars for a Gregorian datetime."""
    d = dt.date()
    if _ZI_HOUR_NEXT_DAY and dt.hour >= 23:
        from datetime import timedelta

        d = d + timedelta(days=1)  # 子时归次日：日/月/年柱按次日重算
    return {
        **pillars_for_date(d),
        "hour": hour_pillar(dt),
    }


def pillars_for_lunar_datetime(
    lunar_year: int,
    lunar_month: int,
    lunar_day: int,
    hour: int,
    minute: int = 0,
    leap: bool = False,
) -> Dict[str, str]:
    """Return year/month/day/hour pillars for a lunar datetime."""
    solar_date = lunar_to_solar(lunar_year, lunar_month, lunar_day, leap)
    return pillars_for_datetime(datetime(solar_date.year, solar_date.month, solar_date.day, hour, minute))


def solar_birth_datetime(
    birth_date: str, birth_time: str = "00:00", calendar_type: str = "solar"
) -> Optional[datetime]:
    """Convert birth date/time strings to a solar datetime.

    *birth_date* is expected as ``YYYY-MM-DD``. *birth_time* as ``HH:MM``.
    For lunar input, the date is converted to the corresponding solar date.
    """
    try:
        year, month, day = map(int, birth_date.split("-"))
        hour, minute = 0, 0
        if birth_time:
            hour, minute = map(int, birth_time.split(":")[:2])
    except (ValueError, AttributeError):
        return None

    if calendar_type == "lunar":
        try:
            solar_date = lunar_to_solar(year, month, day)
        except Exception:
            return None
    else:
        solar_date = date(year, month, day)

    return datetime(solar_date.year, solar_date.month, solar_date.day, hour, minute)


def _jd_to_datetime(jd: float) -> datetime:
    dd = sxtwl.JD2DD(jd)
    return datetime(
        int(dd.Y),
        int(dd.M),
        int(dd.D),
        int(dd.h),
        int(dd.m),
        int(dd.s),
    )


def _next_jie_after(dt: datetime) -> Optional[datetime]:
    """Return the next 节 (solar month start) strictly after dt."""
    if not _SXTWL_AVAILABLE:
        return None
    day = sxtwl.fromSolar(dt.year, dt.month, dt.day)
    for offset in range(120):
        cur = day if offset == 0 else day.after(offset)
        if cur.hasJieQi() and cur.getJieQi() in _JIE_INDICES:
            jdt = _jd_to_datetime(cur.getJieQiJD())
            if jdt > dt:
                return jdt
    return None


def _prev_jie_before(dt: datetime) -> Optional[datetime]:
    """Return the previous 节 strictly before dt."""
    if not _SXTWL_AVAILABLE:
        return None
    day = sxtwl.fromSolar(dt.year, dt.month, dt.day)
    for offset in range(120):
        cur = day if offset == 0 else day.before(offset)
        if cur.hasJieQi() and cur.getJieQi() in _JIE_INDICES:
            jdt = _jd_to_datetime(cur.getJieQiJD())
            if jdt < dt:
                return jdt
    return None


def _start_age(birth_dt: datetime, forward: bool) -> Tuple[int, int]:
    """Return (years, months) of the dayun start age.

    3 days = 1 year, 1 day = 4 months.
    """
    target = _next_jie_after(birth_dt) if forward else _prev_jie_before(birth_dt)
    if target is None:
        return 0, 0
    delta = target - birth_dt if forward else birth_dt - target
    days = max(0, int(delta.total_seconds() // 86400))
    years = days // 3
    months = (days % 3) * 4
    return years, months


def dayun_list(
    bazi: str,
    gender: str,
    birth_date: str,
    birth_time: str = "00:00",
    calendar_type: str = "solar",
    until_age: int = 80,
) -> List[Dict]:
    """Return the ten-year DaYun periods for a chart.

    Direction rule: 阳男阴女顺排，阴男阳女逆排.
    If birth info is missing/invalid, starts at age 0 from the month pillar.
    """
    from tools.bazi_ai.bazi_validator import extract_pillars

    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return []

    year_stem, month_pillar = pillars[0][0], pillars[1]
    birth_dt = solar_birth_datetime(birth_date, birth_time, calendar_type)
    # Empty/unknown must NOT fall through as female (old bug: `in (...)` was False).
    gender_norm = (gender or "").strip()
    female_tokens = {"female", "女", "f", "F", "woman"}
    if gender_norm in female_tokens:
        _male = False
    else:
        # male / 男 / empty / unknown → male direction (safe default)
        _male = True

    if birth_dt is None:
        start_years, start_months = 0, 0
        forward = True
    else:
        yang = year_stem in {"甲", "丙", "戊", "庚", "壬"}
        forward = (yang and _male) or (not yang and not _male)
        start_years, start_months = _start_age(birth_dt, forward)

    try:
        start_idx = JIAZI_PILLARS.index(month_pillar)
    except ValueError:
        return []

    start_age = start_years + start_months / 12.0
    result: List[Dict] = []
    i = 0
    while start_age + i * 10 < until_age:
        # 大运从月柱起排：第一步为月柱的下一步（顺行/逆行）
        idx = (start_idx + i + 1) % 60 if forward else (start_idx - i - 1) % 60
        period_start = round(start_age + i * 10, 2)
        period_end = round(period_start + 10, 2)
        result.append(
            {
                "index": i,
                "pillar": JIAZI_PILLARS[idx],
                "start_age": period_start,
                "end_age": period_end,
                "start_year": None,  # populated by caller if birth year known
                "end_year": None,
            }
        )
        i += 1
    return result


def liunian_list(
    start_year: int,
    end_year: int,
) -> List[Dict]:
    """Return the yearly Liunian pillars for a range of years."""
    result: List[Dict] = []
    for year in range(start_year, end_year + 1):
        # Use mid-year to safely pass Li Chun boundary.
        pillar = year_pillar(date(year, 6, 15))
        result.append(
            {
                "year": year,
                "pillar": pillar,
                "stem": pillar[0],
                "branch": pillar[1],
            }
        )
    return result


def _element_counts(pillars: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {e: 0 for e in _ELEMENT_LABELS}
    for p in pillars:
        counts[STEM_ELEMENTS[p[0]]] += 1
        counts[BRANCH_ELEMENTS[p[1]]] += 1
    return counts


def daily_fortune(
    user_bazi: str,
    target_date: Optional[date] = None,
) -> Dict:
    """Generate a simplified daily fortune reading for a user's chart."""
    from tools.bazi_ai.bazi_validator import extract_pillars

    target_date = target_date or datetime.now().date()
    today = pillars_for_date(target_date)
    today_pillars = list(today.values())

    try:
        user_pillars = extract_pillars(user_bazi)
    except ValueError:
        return {
            "date": target_date.isoformat(),
            "error": "无效的八字格式",
        }

    user_day_master = user_pillars[2][0]
    user_day_master_element = STEM_ELEMENTS[user_day_master]

    today_elements = _element_counts(today_pillars)
    total = sum(today_elements.values())
    energy = {
        element: round((count / total) * 100) if total else 0
        for element, count in today_elements.items()
    }

    dominant = max(today_elements, key=today_elements.get)
    supportive = {
        "wood": ["water"],
        "fire": ["wood"],
        "earth": ["fire"],
        "metal": ["earth"],
        "water": ["metal"],
    }
    opposing = {
        "wood": ["metal"],
        "fire": ["water"],
        "earth": ["wood"],
        "metal": ["fire"],
        "water": ["earth"],
    }

    if dominant == user_day_master_element:
        weather = "晴"
        weather_label = "日主当令"
        description = f"今日{dominant}气充沛，与日主{user_day_master}（{_ELEMENT_LABELS[user_day_master_element]}）同频，行动力强。"
    elif dominant in supportive.get(user_day_master_element, []):
        weather = "多云"
        weather_label = "得生助"
        description = f"今日{_ELEMENT_LABELS[dominant]}旺相，生助日主，适合推进重要事项。"
    elif dominant in opposing.get(user_day_master_element, []):
        weather = "雨"
        weather_label = "受克制"
        description = f"今日{_ELEMENT_LABELS[dominant]}气偏重，日主受克，宜稳守、忌冒进。"
    else:
        weather = "阴"
        weather_label = "平"
        description = "今日五行相对平衡，无明显冲克，宜处理日常事务。"

    if weather in ("晴", "多云"):
        dos = ["推进计划、签约谈判、主动沟通"]
        avoids = ["过度消耗、贪多求快"]
    elif weather == "雨":
        dos = ["整理内务、学习复盘、保守理财"]
        avoids = ["大额投资、冲动决策、与人争执"]
    else:
        dos = ["按部就班、维护关系、健康管理"]
        avoids = ["激进变动、透支精力"]

    return {
        "date": target_date.isoformat(),
        "today_pillars": today,
        "user_day_master": user_day_master,
        "user_day_master_element": user_day_master_element,
        "weather": weather,
        "weather_label": weather_label,
        "description": description,
        "energy": energy,
        "dos": dos,
        "avoids": avoids,
    }
