#!/usr/bin/env python3
"""择日引擎 —— 目标导向的个性化吉日推荐。

在 ``daily_fortune``(单日五行 vs 日主)之上,加日期范围遍历 + **命主用神忌神**
主信号 + 冲合加减 + 目标类型权重 + **时辰窗口**,按分排序输出。

定位(诚实):无完整黄历宜忌建除表,故择日主信号仍为**命主个人用神忌神 + 冲合**;
现已叠加**日干支神煞**(天乙贵人/文昌/禄/金舆/羊刃,确定性查表)作为黄历内核
的近似 —— 这是「个人命盘优化求解器」的差异化,且与报告用神口径(对齐穷通宝鉴
90%)一致,可信度可标 ``✅ 确定性``。

Usage::

    from datetime import date, timedelta
    from tools.bazi_ai.auspicious import auspicious_days, to_ics
    d0 = date(2026, 7, 16)
    res = auspicious_days("乙卯 戊寅 庚子 丙子", "male", "marriage",
                          d0, d0 + timedelta(days=60))
    print(to_ics(res, top_n=5))
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.bazi_ai import bazi_structural
from tools.bazi_ai.bazi_structural import shishen_for_stem
from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.calendar import daily_fortune, pillars_for_date
from tools.bazi_ai.shensha import day_shensha
from tools.bazi_ai.yongshen import resolve_yongshen

# ---------------------------------------------------------------------------
# 五行(中文)生克 —— 自定义,与 resolve_yongshen 的五行口径一致
# ---------------------------------------------------------------------------

_STEM_ELEM = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
              "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
_BRANCH_ELEM = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
                "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
                "戌": "土", "亥": "水"}
_WUXING = ["木", "火", "土", "金", "水"]
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # X 生 Y
_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 十二时辰 → (起始钟点, 结束钟点, 中文标签)。子时跨日 23–1。
_SHICHEN: List[Tuple[str, int, int, str]] = [
    ("子", 23, 1, "子时(23:00-01:00)"),
    ("丑", 1, 3, "丑时(01:00-03:00)"),
    ("寅", 3, 5, "寅时(03:00-05:00)"),
    ("卯", 5, 7, "卯时(05:00-07:00)"),
    ("辰", 7, 9, "辰时(07:00-09:00)"),
    ("巳", 9, 11, "巳时(09:00-11:00)"),
    ("午", 11, 13, "午时(11:00-13:00)"),
    ("未", 13, 15, "未时(13:00-15:00)"),
    ("申", 15, 17, "申时(15:00-17:00)"),
    ("酉", 17, 19, "酉时(17:00-19:00)"),
    ("戌", 19, 21, "戌时(19:00-21:00)"),
    ("亥", 21, 23, "亥时(21:00-23:00)"),
]

# event_type → (喜好十神, 忌讳十神, 中文标签, 默认宜, 默认忌)
# 宜/忌为事项层面的行为提示,与 daily_fortune 的通用 dos 互补。
_EventSpec = Tuple[Set[str], Set[str], str, List[str], List[str]]
_EVENT_PREF: Dict[str, _EventSpec] = {
    "marriage": (
        {"正财", "偏财", "正官", "七杀"},
        {"比肩", "劫财"},
        "嫁娶",
        ["定婚宴请、登记领证、见家长"],
        ["与前任纠缠、冲动退婚"],
    ),
    "opening": (
        {"正财", "偏财", "食神", "伤官"},
        {"比肩", "劫财"},
        "开业",
        ["挂牌开业、首单成交、招商签约"],
        ["大额负债扩张、与同行撕破脸"],
    ),
    "moving": (
        {"正印", "偏印"},
        set(),
        "入宅",
        ["乔迁入宅、安床开光、安家设位"],
        ["当日大动土、与邻里冲突"],
    ),
    "travel": (
        {"食神", "伤官"},
        {"七杀"},
        "出行",
        ["出发远行、商务出差、拜访客户"],
        ["危险地区探险、疲劳驾驶"],
    ),
    "signing": (
        {"正官", "七杀", "正印", "偏印"},
        set(),
        "签约",
        ["合同签署、协议盖章、正式备案"],
        ["口头承诺不落字、超范围担保"],
    ),
    "interview": (
        {"正官", "七杀", "正印", "偏印"},
        set(),
        "求职",
        ["面试面谈、递交材料、谈薪入职"],
        ["临阵换行、贬损前东家"],
    ),
    "surgery": (
        {"正印", "偏印", "食神"},
        {"七杀", "伤官"},
        "手术",
        ["择医问诊、复诊复查、静养调理"],
        ["强行催促手术、术后剧烈运动"],
    ),
    "investment": (
        {"正财", "偏财", "食神"},
        {"劫财", "七杀"},
        "投资",
        ["研究标的、分批建仓、复盘持仓"],
        ["杠杆梭哈、听小道消息跟风"],
    ),
}

# 男命/女命对「婚恋」十神的侧重(在通用 pref 之上微调)
_GENDER_MARRIAGE_BOOST: Dict[str, Set[str]] = {
    "male": {"正财", "偏财"},      # 男命以财为妻星
    "female": {"正官", "七杀"},    # 女命以官杀为夫星
}


# ---------------------------------------------------------------------------
# 公开 helper:任意两支关系(封装 bazi_structural 私有表)
# ---------------------------------------------------------------------------

def branch_relation(b1: str, b2: str) -> Set[str]:
    """任意两个地支的关系集合。

    返回可能含:``{"冲"}`` / ``{"六合(土)"}`` / ``{"害"}`` /
    ``{"刑(无礼之刑)"}`` / ``{"半三合(水)"}``。空集表示无特殊关系。
    """
    rels: Set[str] = set()
    pair, rpair = (b1, b2), (b2, b1)
    if pair in bazi_structural._DI_ZHI_CHONG or rpair in bazi_structural._DI_ZHI_CHONG:
        rels.add("冲")
    he = bazi_structural._DI_ZHI_LIU_HE.get(pair) or bazi_structural._DI_ZHI_LIU_HE.get(rpair)
    if he:
        rels.add(f"六合({he})")
    if pair in bazi_structural._DI_ZHI_HAI or rpair in bazi_structural._DI_ZHI_HAI:
        rels.add("害")
    xing = bazi_structural._DI_ZHI_XING.get(pair) or bazi_structural._DI_ZHI_XING.get(rpair)
    if xing:
        rels.add(f"刑({xing})")
    for ju, el in bazi_structural._DI_ZHI_SAN_HE.items():
        if b1 != b2 and b1 in ju and b2 in ju:
            rels.add(f"半三合({el})")
            break
    return rels


def event_types() -> List[Dict[str, str]]:
    """返回支持的事项类型列表 ``[{value, label}, ...]``。"""
    return [
        {"value": key, "label": spec[2]}
        for key, spec in _EVENT_PREF.items()
    ]


def _dominant_element(day_pillars: List[str]) -> str:
    """当日主导五行(中文),天干 0.5 + 地支 1.0 加权后取最大。"""
    counts = {e: 0.0 for e in _WUXING}
    for p in day_pillars:
        counts[_STEM_ELEM[p[0]]] += 0.5
        counts[_BRANCH_ELEM[p[1]]] += 1.0
    return max(counts, key=counts.get)


def _norm_gender(gender: str) -> str:
    g = (gender or "male").strip().lower()
    if g in ("female", "f", "女", "女命"):
        return "female"
    return "male"


def _hour_stem_for_day(day_stem: str, branch: str) -> str:
    """五鼠遁:由日干推算该日某时支的天干。"""
    day_stem_index = _STEMS.index(day_stem)
    branch_index = _BRANCHES.index(branch)
    start_index = (day_stem_index % 5) * 2
    return _STEMS[(start_index + branch_index) % 10]


def _score_hours(
    day_master: str,
    day_branch: str,
    year_branch: str,
    useful: List[str],
    taboo: List[str],
    today_day_gan: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """为当日十二时辰打分,返回前 top_k 吉时(降序)。

    规则(确定性,无 LLM):
    - 时支冲日支 → 重罚;冲年支 → 中罚
    - 时支五行属用神 → 加分;属忌神 → 减分
    - 时干十神助用神/食伤泄秀等轻权重加分
    """
    scored: List[Dict[str, Any]] = []
    for branch, h0, h1, label in _SHICHEN:
        score = 50.0
        reasons: List[str] = []
        elem = _BRANCH_ELEM[branch]

        # 1) 时支 vs 命主日支/年支
        for my_branch, name, clash_pen, he_bonus in [
            (day_branch, "日支", 30, 12),
            (year_branch, "年支", 15, 6),
        ]:
            for r in branch_relation(branch, my_branch):
                if r == "冲":
                    score -= clash_pen
                    reasons.append(f"时支冲{name}")
                elif r.startswith("六合") or r.startswith("半三合"):
                    score += he_bonus
                    reasons.append(f"时支与{name}{r}")
                elif r.startswith("刑"):
                    score -= 10
                    reasons.append(f"时支与{name}{r}")
                elif r == "害":
                    score -= 6
                    reasons.append(f"时支与{name}相害")

        # 2) 时支五行 vs 用神忌神
        if elem in useful:
            score += 20
            reasons.append(f"时支{elem}为用神")
        elif any(_SHENG[elem] == u for u in useful):
            score += 10
            reasons.append(f"时支{elem}生用神")
        if elem in taboo:
            score -= 18
            reasons.append(f"时支{elem}为忌神")

        # 3) 时干十神(轻权重)
        hour_stem = _hour_stem_for_day(today_day_gan, branch)
        ss = shishen_for_stem(day_master, hour_stem)
        if ss in ("正印", "偏印", "食神", "正财", "正官"):
            score += 5
            reasons.append(f"时干透{ss}")
        elif ss in ("七杀", "劫财"):
            score -= 4
            reasons.append(f"时干透{ss}")

        score_i = max(0, min(100, int(round(score))))
        # 钟点区间字符串,前端/ICS 直接用
        if h0 > h1:  # 子时跨日
            clock = f"{h0:02d}:00-次日{h1:02d}:00"
        else:
            clock = f"{h0:02d}:00-{h1:02d}:00"
        scored.append({
            "branch": branch,
            "pillar": hour_stem + branch,
            "label": label,
            "clock": clock,
            "start_hour": h0,
            "end_hour": h1,
            "score": score_i,
            "reasoning": ";".join(reasons) if reasons else "时辰平和",
            "recommended": score_i >= 60,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, top_k)]


def _score_day(
    day_master: str,
    day_branch: str,
    year_branch: str,
    useful: List[str],
    taboo: List[str],
    event_type: str,
    gender: str,
    today_day_gan: str,
    today_day_zhi: str,
    today_pillars: List[str],
    day_ss: Optional[List[Dict[str, str]]] = None,
) -> Tuple[int, List[str]]:
    """给单日打分,返回 (score 0-100, reasoning 片段列表)。"""
    dominant = _dominant_element(today_pillars)
    reasons: List[str] = []
    score = 50.0

    # 1) 用神忌神(主信号)
    if dominant in useful:
        score += 30
        reasons.append(f"当日{dominant}气当令,为命主用神")
    elif any(_SHENG[dominant] == u for u in useful):
        score += 15
        reasons.append(f"当日{dominant}生助用神{''.join(useful)}")
    if dominant in taboo:
        score -= 30
        reasons.append(f"当日{dominant}气偏重,为命主忌神")

    # 2) 目标权重(当日日干对命主的十神)
    pref, avoid, label, _, _ = _EVENT_PREF.get(
        event_type, (set(), set(), event_type, [], [])
    )
    shishen = shishen_for_stem(day_master, today_day_gan)
    if shishen in pref:
        score += 15
        reasons.append(f"当日透{shishen},利{label}")
        # 性别侧重:婚恋事项额外加权妻星/夫星
        if event_type == "marriage":
            boost = _GENDER_MARRIAGE_BOOST.get(gender, set())
            if shishen in boost:
                score += 5
                role = "妻星" if gender == "male" else "夫星"
                reasons.append(f"{role}透出,于婚恋更利")
    elif shishen in avoid:
        score -= 15
        reasons.append(f"当日透{shishen},于{label}不利")

    # 3) 冲合(当日地支 vs 命主日支 / 年支)
    for my_branch, name, clash_pen, he_pen in [
        (day_branch, "日支", 25, 12),
        (year_branch, "年支", 15, 8),
    ]:
        for r in branch_relation(today_day_zhi, my_branch):
            if r == "冲":
                score -= clash_pen
                reasons.append(f"当日支冲{name}({today_day_zhi}冲{my_branch})")
            elif r.startswith("六合") or r.startswith("半三合"):
                score += he_pen
                reasons.append(f"当日支与{name}{r}")
            elif r.startswith("刑"):
                score -= 8
                reasons.append(f"当日支与{name}{r}")
            elif r == "害":
                score -= 5
                reasons.append(f"当日支与{name}相害")

    # 4) 神煞(日干支自带,黄历确定性内核;权重保守,叠在用神/冲合之上)
    for s in day_ss or []:
        if s.get("effect") == "吉":
            score += 6
            reasons.append(f"当日{s['name']}({s.get('info', '')}),黄道吉神")
        else:
            score -= 10
            reasons.append(f"当日{s['name']}({s.get('info', '')}),宜回避")

    return max(0, min(100, int(round(score)))), reasons


def auspicious_days(
    user_bazi: str,
    gender: str = "male",
    event_type: str = "marriage",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_n: int = 10,
    hour_top_k: int = 3,
) -> Dict[str, Any]:
    """目标导向个性化吉日推荐。

    Args:
        user_bazi: 四柱八字,空格分隔。
        gender: male/female(婚恋事项会按妻星/夫星微调权重)。
        event_type: marriage / opening / moving / travel / signing / interview /
            surgery / investment。
        date_from / date_to: 推荐区间(默认今天起 60 天)。
        top_n: ``top`` 字段返回的前 N 个吉日;``days`` 始终含区间内全部天数
            (前端日历网格需要完整数据)。
        hour_top_k: 每个推荐日附带的吉时数量。

    Returns:
        ``{bazi, gender, event_type, event_label, useful_gods, taboo_gods,
        top, days, date_from, date_to}``。
        ``days`` / ``top`` 元素含 score / hours / reasoning / dos / avoids 等。
    """
    user_bazi = (user_bazi or "").strip()
    gender = _norm_gender(gender)
    date_from = date_from or date.today()
    date_to = date_to or (date_from + timedelta(days=60))
    top_n = max(1, min(int(top_n or 10), 60))
    hour_top_k = max(1, min(int(hour_top_k or 3), 12))

    try:
        pillars = extract_pillars(user_bazi)
    except (ValueError, Exception):
        return {
            "bazi": user_bazi,
            "gender": gender,
            "error": "无效的八字格式",
            "days": [],
            "top": [],
        }

    day_master = pillars[2][0]
    day_branch = pillars[2][1]
    year_branch = pillars[0][1]

    ys = resolve_yongshen(user_bazi) or {}
    useful = [e for e in (ys.get("useful_gods") or []) if e in _WUXING]
    taboo = [e for e in (ys.get("taboo_gods") or []) if e in _WUXING]
    pref, avoid, event_label, event_dos, event_avoids = _EVENT_PREF.get(
        event_type, (set(), set(), event_type, [], [])
    )
    del pref, avoid  # 评分在 _score_day 内重新取

    scored: List[Dict[str, Any]] = []
    d = date_from
    while d <= date_to:
        today = pillars_for_date(d)
        today_pillars = [today["year"], today["month"], today["day"]]
        today_day = today["day"]
        today_day_gan, today_day_zhi = today_day[0], today_day[1]

        day_ss = day_shensha(today_day_gan, today_day_zhi, gender)

        score, reasons = _score_day(
            day_master, day_branch, year_branch, useful, taboo, event_type,
            gender, today_day_gan, today_day_zhi, today_pillars, day_ss,
        )

        # 复用 daily_fortune 的单日 weather / dos / avoids,再叠加事项宜忌
        try:
            df = daily_fortune(user_bazi, d)
            weather = df.get("weather", "")
            dos = list(df.get("dos") or [])
            avoids = list(df.get("avoids") or [])
        except Exception:
            weather, dos, avoids = "", [], []
        for item in event_dos:
            if item not in dos:
                dos.append(item)
        for item in event_avoids:
            if item not in avoids:
                avoids.append(item)

        hours = _score_hours(
            day_master, day_branch, year_branch, useful, taboo,
            today_day_gan, top_k=hour_top_k,
        )

        scored.append({
            "date": d.isoformat(),
            "day_pillar": today_day,
            "score": score,
            "weather": weather,
            "shishen": shishen_for_stem(day_master, today_day_gan),
            "shensha": day_ss,
            "reasoning": ";".join(reasons) if reasons else "五行平和,无明显冲合",
            "dos": dos,
            "avoids": avoids,
            "hours": hours,
            "best_hour": hours[0] if hours else None,
            "recommended": score >= 60,
        })
        d += timedelta(days=1)

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]
    return {
        "bazi": user_bazi,
        "gender": gender,
        "event_type": event_type,
        "event_label": event_label,
        "useful_gods": useful,
        "taboo_gods": taboo,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        # 区间内全部天数(已按分降序);前端日历网格用 days,卡片用 top
        "days": scored,
        "top": top,
    }


def to_ics(
    result: Dict[str, Any],
    top_n: int = 5,
    min_score: int = 60,
) -> str:
    """把择日结果导出为 iCalendar(``.ics``)文本。

    默认取 ``top``/``days`` 中 score≥min_score 的前 top_n 日;
    每条 VEVENT 含 SUMMARY(事项+日柱)与 DESCRIPTION(理由+吉时+宜忌)。
    兼容 Outlook / Google Calendar / 苹果日历。
    """
    label = result.get("event_label") or result.get("event_type") or "择日"
    days = result.get("top") or result.get("days") or []
    selected = [d for d in days if d.get("score", 0) >= min_score][:top_n]
    if not selected:
        selected = list(days)[:top_n]

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MingMirror//Auspicious//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:命镜择日·{label}",
    ]
    for day in selected:
        date_str = str(day.get("date") or "")
        dt = date_str.replace("-", "")
        if len(dt) != 8:
            continue
        # 全日事件:DTEND = 次日
        try:
            d = date.fromisoformat(date_str)
            dt_end = (d + timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            dt_end = dt

        pillar = day.get("day_pillar") or ""
        score = day.get("score", 0)
        best = day.get("best_hour") or {}
        best_label = best.get("label") or best.get("clock") or ""
        reason = (day.get("reasoning") or "").replace("\n", " ")
        dos = "、".join(day.get("dos") or [])
        avoids = "、".join(day.get("avoids") or [])
        desc_parts = [
            f"评分:{score}",
            f"日柱:{pillar}",
            f"理由:{reason}" if reason else "",
            f"吉时:{best_label}" if best_label else "",
            f"宜:{dos}" if dos else "",
            f"忌:{avoids}" if avoids else "",
            "来源:命镜择日引擎(用神+冲合,非传统黄历)",
        ]
        description = " | ".join(p for p in desc_parts if p)
        # ICS 文本转义
        description = (
            description.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )
        summary = f"命镜择日·{label}·{pillar}({score}分)"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{date_str}-{result.get('event_type', 'day')}@mingmirror",
            f"DTSTART;VALUE=DATE:{dt}",
            f"DTEND;VALUE=DATE:{dt_end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


if __name__ == "__main__":
    d0 = date(2026, 7, 16)
    res = auspicious_days(
        "乙卯 戊寅 庚子 丙子", "male", "marriage",
        d0, d0 + timedelta(days=60), top_n=5,
    )
    print(
        f"useful={res['useful_gods']} taboo={res['taboo_gods']} "
        f"label={res['event_label']} top={len(res['top'])}/{len(res['days'])}"
    )
    for day in res["top"]:
        bh = day.get("best_hour") or {}
        print(
            f"{day['date']} {day['day_pillar']} score={day['score']:>3} "
            f"{day['weather']} {day['shishen']} | 吉时={bh.get('label', '-')} | "
            f"{day['reasoning'][:48]}"
        )
    print("--- ICS (first 600 chars) ---")
    print(to_ics(res, top_n=3)[:600])
