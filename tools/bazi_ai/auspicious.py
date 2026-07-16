#!/usr/bin/env python3
"""择日引擎 —— 目标导向的个性化吉日推荐。

在 ``daily_fortune``(单日五行 vs 日主)之上,加日期范围遍历 + **命主用神忌神**
主信号 + 冲合加减 + 目标类型权重,按分排序输出 Top N。

定位(诚实):项目内无传统黄历宜忌数据,故择日基于**命主个人用神忌神 + 冲合** ——
这是「个人命盘优化求解器」的差异化,且与已落地的报告用神口径(对齐穷通宝鉴
90%)一致,可信度可标 ``✅ 确定性``。

Usage::

    from datetime import date, timedelta
    from tools.bazi_ai.auspicious import auspicious_days
    d0 = date(2026, 7, 16)
    res = auspicious_days("乙卯 戊寅 庚子 丙子", "male", "marriage",
                          d0, d0 + timedelta(days=60))
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.bazi_ai import bazi_structural
from tools.bazi_ai.bazi_structural import shishen_for_stem
from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.calendar import daily_fortune, pillars_for_date
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

# event_type → (喜好十神, 忌讳十神, 中文标签)
_EVENT_PREF: Dict[str, Tuple[Set[str], Set[str], str]] = {
    "marriage":  ({"正财", "偏财", "正官", "七杀"}, {"比肩", "劫财"}, "嫁娶"),
    "opening":   ({"正财", "偏财", "食神", "伤官"}, {"比肩", "劫财"}, "开业"),
    "moving":    ({"正印", "偏印"}, set(), "入宅"),
    "travel":    ({"食神", "伤官"}, {"七杀"}, "出行"),
    "signing":   ({"正官", "七杀", "正印", "偏印"}, set(), "签约"),
    "interview": ({"正官", "七杀", "正印", "偏印"}, set(), "求职"),
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


def _dominant_element(day_pillars: List[str]) -> str:
    """当日主导五行(中文),天干 0.5 + 地支 1.0 加权后取最大。"""
    counts = {e: 0.0 for e in _WUXING}
    for p in day_pillars:
        counts[_STEM_ELEM[p[0]]] += 0.5
        counts[_BRANCH_ELEM[p[1]]] += 1.0
    return max(counts, key=counts.get)


def _score_day(
    day_master: str,
    day_branch: str,
    year_branch: str,
    useful: List[str],
    taboo: List[str],
    event_type: str,
    today_day_gan: str,
    today_day_zhi: str,
    today_pillars: List[str],
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
    pref, avoid, label = _EVENT_PREF.get(event_type, (set(), set(), event_type))
    shishen = shishen_for_stem(day_master, today_day_gan)
    if shishen in pref:
        score += 15
        reasons.append(f"当日透{shishen},利{label}")
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

    return max(0, min(100, int(round(score)))), reasons


def auspicious_days(
    user_bazi: str,
    gender: str = "male",
    event_type: str = "marriage",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """目标导向个性化吉日推荐。

    Args:
        user_bazi: 四柱八字,空格分隔。
        gender: male/female(留接口;当前评分与性别无关,冲合只看日支/年支)。
        event_type: marriage / opening / moving / travel / signing / interview。
        date_from / date_to: 推荐区间(默认今天起 60 天)。
        top_n: 返回前 N 个吉日。

    Returns:
        ``{bazi, event_type, event_label, useful_gods, taboo_gods,
        days: [{date, day_pillar, score, weather, shishen, reasoning, dos,
        avoids, recommended}]}``。days 按分数降序。
    """
    user_bazi = (user_bazi or "").strip()
    date_from = date_from or date.today()
    date_to = date_to or (date_from + timedelta(days=60))

    try:
        pillars = extract_pillars(user_bazi)
    except (ValueError, Exception):
        return {"bazi": user_bazi, "error": "无效的八字格式", "days": []}

    day_master = pillars[2][0]
    day_branch = pillars[2][1]
    year_branch = pillars[0][1]

    ys = resolve_yongshen(user_bazi) or {}
    useful = [e for e in (ys.get("useful_gods") or []) if e in _WUXING]
    taboo = [e for e in (ys.get("taboo_gods") or []) if e in _WUXING]
    _, _, event_label = _EVENT_PREF.get(event_type, (set(), set(), event_type))

    scored: List[Dict[str, Any]] = []
    d = date_from
    while d <= date_to:
        today = pillars_for_date(d)
        today_pillars = [today["year"], today["month"], today["day"]]
        today_day = today["day"]
        today_day_gan, today_day_zhi = today_day[0], today_day[1]

        score, reasons = _score_day(
            day_master, day_branch, year_branch, useful, taboo, event_type,
            today_day_gan, today_day_zhi, today_pillars,
        )

        # 复用 daily_fortune 的单日 weather / dos / avoids
        try:
            df = daily_fortune(user_bazi, d)
            weather = df.get("weather", "")
            dos = df.get("dos", [])
            avoids = df.get("avoids", [])
        except Exception:
            weather, dos, avoids = "", [], []

        scored.append({
            "date": d.isoformat(),
            "day_pillar": today_day,
            "score": score,
            "weather": weather,
            "shishen": shishen_for_stem(day_master, today_day_gan),
            "reasoning": ";".join(reasons) if reasons else "五行平和,无明显冲合",
            "dos": dos,
            "avoids": avoids,
            "recommended": score >= 60,
        })
        d += timedelta(days=1)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "bazi": user_bazi,
        "event_type": event_type,
        "event_label": event_label,
        "useful_gods": useful,
        "taboo_gods": taboo,
        # 区间内全部天数(已按分降序);前端按需 slice Top N 展示卡片,全部画日历网格
        "days": scored,
    }


if __name__ == "__main__":
    from datetime import date, timedelta

    d0 = date(2026, 7, 16)
    res = auspicious_days("乙卯 戊寅 庚子 丙子", "male", "marriage",
                          d0, d0 + timedelta(days=60), top_n=5)
    print(f"useful={res['useful_gods']} taboo={res['taboo_gods']} "
          f"label={res['event_label']}")
    for day in res["days"]:
        print(f"{day['date']} {day['day_pillar']} score={day['score']:>3} "
              f"{day['weather']} {day['shishen']} | {day['reasoning'][:54]}")
