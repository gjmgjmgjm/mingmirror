#!/usr/bin/env python3
"""合婚引擎 —— 双盘结构性匹配(零 LLM)。

基于双方用神/日干十神/夫妻宫冲合/地支刑冲合害/配偶星质量/身强弱互补,
输出 0-100 合婚指数与分维雷达、冲突/助力列表。

诚实定位:传统合婚流派极多,本模块只做**可复核的结构信号加权**,
不声称替代完整合婚术数;适合沙盒 A/B 与 API ``/bazi/compatibility``。

Usage::

    from tools.bazi_ai.hehun import compare_charts
    r = compare_charts("乙卯 戊寅 庚子 丙子", "male",
                      "甲子 丙寅 戊辰 壬子", "female")
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.bazi_ai.auspicious import auspicious_days, branch_relation, to_ics
from tools.bazi_ai.bazi_structural import (
    liuqin_profile,
    shishen_for_stem,
    structural_profile,
)
from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.yongshen import resolve_yongshen

_STEM_ELEM = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
_BRANCH_ELEM = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_TIAN_GAN_HE = {
    frozenset(("甲", "己")): "土",
    frozenset(("乙", "庚")): "金",
    frozenset(("丙", "辛")): "水",
    frozenset(("丁", "壬")): "木",
    frozenset(("戊", "癸")): "火",
}
_WUXING = ["木", "火", "土", "金", "水"]


def _norm_gender(g: str) -> str:
    g = (g or "male").strip().lower()
    if g in ("female", "f", "女", "女命"):
        return "female"
    return "male"


def _elem_weights(stems: List[str], branches: List[str]) -> Dict[str, float]:
    w = {e: 0.0 for e in _WUXING}
    for s in stems:
        w[_STEM_ELEM[s]] += 0.5
    for b in branches:
        w[_BRANCH_ELEM[b]] += 1.0
    return w


def _dominant_elems(weights: Dict[str, float], top_n: int = 2) -> List[str]:
    ordered = sorted(weights.items(), key=lambda kv: -kv[1])
    return [e for e, _ in ordered[:top_n] if _ > 0]


def _score_yongshen(
    useful_a: List[str], taboo_a: List[str], weights_b: Dict[str, float],
    useful_b: List[str], taboo_b: List[str], weights_a: Dict[str, float],
) -> Tuple[int, List[str], List[str]]:
    """用神亲和:对方旺气落在我用神上加分,落在忌神上减分(双向)。"""
    notes_pos: List[str] = []
    notes_neg: List[str] = []
    score = 50.0
    dom_b = _dominant_elems(weights_b)
    dom_a = _dominant_elems(weights_a)

    for el in dom_b:
        if el in useful_a:
            score += 12
            notes_pos.append(f"乙方旺{el}合甲方用神")
        elif el in taboo_a:
            score -= 12
            notes_neg.append(f"乙方旺{el}触甲方忌神")
        elif any(_SHENG[el] == u for u in useful_a):
            score += 6
            notes_pos.append(f"乙方旺{el}生助甲方用神")

    for el in dom_a:
        if el in useful_b:
            score += 12
            notes_pos.append(f"甲方旺{el}合乙方用神")
        elif el in taboo_b:
            score -= 12
            notes_neg.append(f"甲方旺{el}触乙方忌神")
        elif any(_SHENG[el] == u for u in useful_b):
            score += 6
            notes_pos.append(f"甲方旺{el}生助乙方用神")

    return max(0, min(100, int(round(score)))), notes_pos, notes_neg


def _score_day_stem(dm_a: str, dm_b: str) -> Tuple[int, List[str], List[str]]:
    """日干关系:五合 / 生 / 克 / 比和。"""
    pos: List[str] = []
    neg: List[str] = []
    score = 50
    he = _TIAN_GAN_HE.get(frozenset((dm_a, dm_b)))
    if he:
        score += 25
        pos.append(f"日干{dm_a}{dm_b}五合化{he}")
        return max(0, min(100, score)), pos, neg

    ea, eb = _STEM_ELEM[dm_a], _STEM_ELEM[dm_b]
    if ea == eb:
        score += 8
        pos.append(f"日主同气{ea}(比和)")
    elif _SHENG[ea] == eb:
        score += 15
        pos.append(f"甲生日主{ea}生乙{eb}")
    elif _SHENG[eb] == ea:
        score += 15
        pos.append(f"乙生日主{eb}生甲{ea}")
    elif _KE[ea] == eb:
        score -= 15
        neg.append(f"甲日主{ea}克乙{eb}")
    elif _KE[eb] == ea:
        score -= 15
        neg.append(f"乙日主{eb}克甲{ea}")

    # 十神视角:甲看乙日干
    ss = shishen_for_stem(dm_a, dm_b)
    if ss in ("正财", "正官", "正印", "食神"):
        score += 5
        pos.append(f"甲见乙日干为{ss}")
    elif ss in ("七杀", "劫财"):
        score -= 5
        neg.append(f"甲见乙日干为{ss}")

    return max(0, min(100, score)), pos, neg


def _score_branches(
    branches_a: List[str], branches_b: List[str]
) -> Tuple[int, List[str], List[str]]:
    """四柱地支交叉:日支(夫妻宫)权重最高,冲刑害减分,合加分。"""
    pos: List[str] = []
    neg: List[str] = []
    score = 50.0

    # 夫妻宫:双方日支
    day_a, day_b = branches_a[2], branches_b[2]
    for r in branch_relation(day_a, day_b):
        if r == "冲":
            score -= 20
            neg.append(f"夫妻宫相冲({day_a}冲{day_b})")
        elif r.startswith("六合") or r.startswith("半三合"):
            score += 18
            pos.append(f"夫妻宫{r}({day_a}/{day_b})")
        elif r.startswith("刑"):
            score -= 12
            neg.append(f"夫妻宫{r}")
        elif r == "害":
            score -= 8
            neg.append("夫妻宫相害")

    # 日支 vs 对方年/月支(父母/社会宫)
    for other_name, other_br, pen_he, pen_ch in [
        ("年支", branches_b[0], 6, 8),
        ("月支", branches_b[1], 8, 10),
    ]:
        for r in branch_relation(day_a, other_br):
            if r == "冲":
                score -= pen_ch * 0.5
                neg.append(f"甲日支冲乙{other_name}")
            elif r.startswith("六合") or r.startswith("半三合"):
                score += pen_he * 0.5
                pos.append(f"甲日支合乙{other_name}")

    for other_name, other_br, pen_he, pen_ch in [
        ("年支", branches_a[0], 6, 8),
        ("月支", branches_a[1], 8, 10),
    ]:
        for r in branch_relation(day_b, other_br):
            if r == "冲":
                score -= pen_ch * 0.5
                neg.append(f"乙日支冲甲{other_name}")
            elif r.startswith("六合") or r.startswith("半三合"):
                score += pen_he * 0.5
                pos.append(f"乙日支合甲{other_name}")

    # 全盘支交叉(去重日支对)
    clash = he = xing = hai = 0
    seen: Set[Tuple[str, str, str]] = set()
    for i, ba in enumerate(branches_a):
        for j, bb in enumerate(branches_b):
            key = tuple(sorted((ba, bb))) + (f"{i}-{j}",)
            if key in seen:
                continue
            seen.add(key)
            for r in branch_relation(ba, bb):
                if r == "冲":
                    clash += 1
                elif r.startswith("六合") or r.startswith("半三合"):
                    he += 1
                elif r.startswith("刑"):
                    xing += 1
                elif r == "害":
                    hai += 1
    score += min(12, he * 3)
    score -= min(15, clash * 4)
    score -= min(8, xing * 2)
    score -= min(6, hai * 2)
    if he:
        pos.append(f"四柱交叉合/半合×{he}")
    if clash:
        neg.append(f"四柱交叉冲×{clash}")

    return max(0, min(100, int(round(score)))), pos, neg


def _score_spouse_star(lq_a: dict, lq_b: dict) -> Tuple[int, List[str], List[str]]:
    pos: List[str] = []
    neg: List[str] = []
    score = 50
    for label, lq in (("甲", lq_a), ("乙", lq_b)):
        sp = lq.get("spouse") or {}
        if not sp.get("exists"):
            score -= 8
            neg.append(f"{label}方配偶星不现")
        elif sp.get("strength") == "强":
            score += 12
            pos.append(f"{label}方配偶星强({sp.get('star', '')})")
        else:
            score -= 4
            neg.append(f"{label}方配偶星弱({sp.get('star', '')})")
    return max(0, min(100, score)), pos, neg


def _score_strength_balance(str_a: str, str_b: str) -> Tuple[int, List[str], List[str]]:
    """身强身弱互补略加分,同极旺略减分。"""
    pos: List[str] = []
    neg: List[str] = []
    score = 50
    a_strong = "强" in (str_a or "")
    b_strong = "强" in (str_b or "")
    a_weak = "弱" in (str_a or "")
    b_weak = "弱" in (str_b or "")
    if (a_strong and b_weak) or (a_weak and b_strong):
        score += 15
        pos.append("身强身弱互补,有帮扶之象")
    elif a_strong and b_strong:
        score -= 5
        neg.append("双方皆偏旺,易各持己见")
    elif a_weak and b_weak:
        score -= 5
        neg.append("双方皆偏弱,外力依赖高")
    else:
        score += 5
        pos.append("旺衰较为平和")
    return max(0, min(100, score)), pos, neg


def joint_auspicious_days(
    bazi_a: str,
    gender_a: str = "male",
    bazi_b: str = "",
    gender_b: str = "female",
    event_type: str = "marriage",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_n: int = 8,
) -> Dict[str, Any]:
    """双方共同择日:取两人单盘择日分的调和平均,并要求双方都不过差。

    joint_score = round(0.5 * a + 0.5 * b); 若任一方 < 45 再扣 10。
    返回 ``{days, top, event_type, event_label}`` 与单盘 auspicious 对齐字段。
    """
    date_from = date_from or date.today()
    date_to = date_to or (date_from + timedelta(days=60))
    top_n = max(1, min(int(top_n or 8), 30))

    ra = auspicious_days(
        bazi_a, gender_a, event_type, date_from, date_to, top_n=60, hour_top_k=2
    )
    rb = auspicious_days(
        bazi_b, gender_b, event_type, date_from, date_to, top_n=60, hour_top_k=2
    )
    if ra.get("error") or rb.get("error"):
        return {
            "error": ra.get("error") or rb.get("error") or "择日失败",
            "days": [],
            "top": [],
        }

    by_b = {d["date"]: d for d in (rb.get("days") or [])}
    joint: List[Dict[str, Any]] = []
    for da in ra.get("days") or []:
        db = by_b.get(da["date"])
        if not db:
            continue
        sa, sb = int(da.get("score") or 0), int(db.get("score") or 0)
        score = int(round(0.5 * sa + 0.5 * sb))
        if sa < 45 or sb < 45:
            score = max(0, score - 10)
        reasons = []
        if da.get("reasoning"):
            reasons.append(f"甲:{da['reasoning']}")
        if db.get("reasoning"):
            reasons.append(f"乙:{db['reasoning']}")
        # 吉时:取双方 best_hour 中分数更高者;若冲突则标双方
        ha = da.get("best_hour") or {}
        hb = db.get("best_hour") or {}
        best = ha if (ha.get("score") or 0) >= (hb.get("score") or 0) else hb
        joint.append({
            "date": da["date"],
            "day_pillar": da.get("day_pillar") or db.get("day_pillar") or "",
            "score": score,
            "score_a": sa,
            "score_b": sb,
            "weather": da.get("weather") or db.get("weather") or "",
            "reasoning": " | ".join(reasons) if reasons else "双方五行平和",
            "dos": list(dict.fromkeys((da.get("dos") or []) + (db.get("dos") or [])))[:4],
            "avoids": list(dict.fromkeys(
                (da.get("avoids") or []) + (db.get("avoids") or [])
            ))[:4],
            "best_hour": best or None,
            "hour_a": ha or None,
            "hour_b": hb or None,
            "recommended": score >= 60 and sa >= 50 and sb >= 50,
        })

    joint.sort(key=lambda x: (x["score"], x["score_a"] + x["score_b"]), reverse=True)
    return {
        "event_type": ra.get("event_type") or event_type,
        "event_label": ra.get("event_label") or event_type,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": joint,
        "top": joint[:top_n],
        "useful_gods_a": ra.get("useful_gods") or [],
        "useful_gods_b": rb.get("useful_gods") or [],
    }


def compare_charts(
    bazi_a: str,
    gender_a: str = "male",
    bazi_b: str = "",
    gender_b: str = "female",
    *,
    include_joint_days: bool = False,
    include_ics: bool = False,
    event_type: str = "marriage",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_n: int = 8,
) -> Dict[str, Any]:
    """双盘合婚结构评分。

    Returns:
        score / level / dimensions / supports / conflicts / profiles / summary
        可选 joint_days / joint_top / ics(共同择日)。
    """
    bazi_a = (bazi_a or "").strip()
    bazi_b = (bazi_b or "").strip()
    gender_a = _norm_gender(gender_a)
    gender_b = _norm_gender(gender_b)

    try:
        pillars_a = extract_pillars(bazi_a)
        pillars_b = extract_pillars(bazi_b)
    except (ValueError, Exception) as exc:
        return {"error": f"无效八字: {exc}", "score": 0, "dimensions": {}, "days": []}

    prof_a = structural_profile(bazi_a) or {}
    prof_b = structural_profile(bazi_b) or {}
    lq_a = liuqin_profile(bazi_a, gender=gender_a) or {}
    lq_b = liuqin_profile(bazi_b, gender=gender_b) or {}
    ys_a = resolve_yongshen(bazi_a) or {}
    ys_b = resolve_yongshen(bazi_b) or {}

    stems_a = [p[0] for p in pillars_a]
    stems_b = [p[0] for p in pillars_b]
    branches_a = [p[1] for p in pillars_a]
    branches_b = [p[1] for p in pillars_b]
    w_a = _elem_weights(stems_a, branches_a)
    w_b = _elem_weights(stems_b, branches_b)

    useful_a = [e for e in (ys_a.get("useful_gods") or []) if e in _WUXING]
    taboo_a = [e for e in (ys_a.get("taboo_gods") or []) if e in _WUXING]
    useful_b = [e for e in (ys_b.get("useful_gods") or []) if e in _WUXING]
    taboo_b = [e for e in (ys_b.get("taboo_gods") or []) if e in _WUXING]

    dim_scores: Dict[str, int] = {}
    supports: List[str] = []
    conflicts: List[str] = []

    s, p, n = _score_yongshen(useful_a, taboo_a, w_b, useful_b, taboo_b, w_a)
    dim_scores["yongshen_affinity"] = s
    supports.extend(p)
    conflicts.extend(n)

    s, p, n = _score_day_stem(stems_a[2], stems_b[2])
    dim_scores["day_stem"] = s
    supports.extend(p)
    conflicts.extend(n)

    s, p, n = _score_branches(branches_a, branches_b)
    dim_scores["branch_harmony"] = s
    supports.extend(p)
    conflicts.extend(n)

    s, p, n = _score_spouse_star(lq_a, lq_b)
    dim_scores["spouse_star"] = s
    supports.extend(p)
    conflicts.extend(n)

    s, p, n = _score_strength_balance(
        str(prof_a.get("strength") or ""), str(prof_b.get("strength") or "")
    )
    dim_scores["strength_balance"] = s
    supports.extend(p)
    conflicts.extend(n)

    # 加权总分
    weights = {
        "yongshen_affinity": 0.28,
        "day_stem": 0.18,
        "branch_harmony": 0.28,
        "spouse_star": 0.14,
        "strength_balance": 0.12,
    }
    total = sum(dim_scores[k] * weights[k] for k in weights)
    score = int(round(max(0, min(100, total))))

    if score >= 80:
        level = "上等良配"
    elif score >= 65:
        level = "较好匹配"
    elif score >= 50:
        level = "中平可合"
    elif score >= 35:
        level = "多有摩擦"
    else:
        level = "冲克较重"

    dim_labels = {
        "yongshen_affinity": "用神亲和",
        "day_stem": "日干关系",
        "branch_harmony": "地支和谐",
        "spouse_star": "配偶星",
        "strength_balance": "旺衰互补",
    }
    dimensions = [
        {
            "key": k,
            "label": dim_labels[k],
            "score": dim_scores[k],
            "weight": weights[k],
        }
        for k in weights
    ]

    summary_parts = [
        f"合婚指数 {score}（{level}）",
        f"甲{stems_a[2]}{branches_a[2]}日主 / 乙{stems_b[2]}{branches_b[2]}日主",
    ]
    if supports:
        summary_parts.append("助力:" + "；".join(supports[:3]))
    if conflicts:
        summary_parts.append("冲突:" + "；".join(conflicts[:3]))

    profiles = {
        "a": {
            "bazi": bazi_a,
            "gender": gender_a,
            "day_master": stems_a[2],
            "day_branch": branches_a[2],
            "strength": prof_a.get("strength"),
            "useful_gods": useful_a,
            "taboo_gods": taboo_a,
            "spouse_star": (lq_a.get("spouse") or {}).get("star"),
            "spouse_strength": (lq_a.get("spouse") or {}).get("strength"),
        },
        "b": {
            "bazi": bazi_b,
            "gender": gender_b,
            "day_master": stems_b[2],
            "day_branch": branches_b[2],
            "strength": prof_b.get("strength"),
            "useful_gods": useful_b,
            "taboo_gods": taboo_b,
            "spouse_star": (lq_b.get("spouse") or {}).get("star"),
            "spouse_strength": (lq_b.get("spouse") or {}).get("strength"),
        },
    }

    reading = _build_reading(
        score=score,
        level=level,
        dimensions=dimensions,
        supports=supports,
        conflicts=conflicts,
        profiles=profiles,
    )

    result: Dict[str, Any] = {
        "score": score,
        "level": level,
        "dimensions": dimensions,
        "supports": supports,
        "conflicts": conflicts,
        "summary": "。".join(summary_parts) + "。",
        "reading": reading,
        "trust": "certain",
        "note": "结构性评分(用神/日干/地支/配偶星/旺衰),非传统合婚全书;重大决策请多方参照。",
        "profiles": profiles,
    }

    if include_joint_days or include_ics:
        joint = joint_auspicious_days(
            bazi_a,
            gender_a,
            bazi_b,
            gender_b,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
            top_n=top_n,
        )
        if not joint.get("error"):
            result["joint_days"] = joint.get("days") or []
            result["joint_top"] = joint.get("top") or []
            result["joint_event_label"] = joint.get("event_label")
            if include_ics:
                # 复用 to_ics:需要 days/top + event_label/event_type
                ics_payload = {
                    "event_type": joint.get("event_type") or event_type,
                    "event_label": f"合婚·{joint.get('event_label') or event_type}",
                    "top": joint.get("top") or [],
                    "days": joint.get("days") or [],
                }
                result["ics"] = to_ics(ics_payload, top_n=top_n, min_score=55)

    return result


def _build_reading(
    score: int,
    level: str,
    dimensions: List[Dict[str, Any]],
    supports: List[str],
    conflicts: List[str],
    profiles: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministic narrative layer (zero LLM) for product copy."""
    pa, pb = profiles["a"], profiles["b"]
    dim_by_key = {d["key"]: d for d in dimensions}

    def _tone(sc: int) -> str:
        if sc >= 70:
            return "偏利"
        if sc >= 50:
            return "中平"
        return "需谨慎"

    sections = [
        {
            "id": "overview",
            "title": "总评",
            "text": (
                f"双方合婚指数 {score}，总评「{level}」。"
                f"甲为{pa.get('day_master')}{pa.get('day_branch')}日主"
                f"（{(pa.get('strength') or '旺衰未详')}），"
                f"乙为{pb.get('day_master')}{pb.get('day_branch')}日主"
                f"（{(pb.get('strength') or '旺衰未详')}）。"
            ),
        },
        {
            "id": "yongshen",
            "title": "用神与五行",
            "text": (
                f"用神亲和{_tone(dim_by_key.get('yongshen_affinity', {}).get('score', 50))}："
                f"甲方用神{('、'.join(pa.get('useful_gods') or []) or '未明')}，"
                f"忌神{('、'.join(pa.get('taboo_gods') or []) or '未明')}；"
                f"乙方用神{('、'.join(pb.get('useful_gods') or []) or '未明')}，"
                f"忌神{('、'.join(pb.get('taboo_gods') or []) or '未明')}。"
                "若一方旺气正落对方用神，相处中易有助力；若触忌神，则日常摩擦更易被放大。"
            ),
        },
        {
            "id": "palace",
            "title": "夫妻宫与日干",
            "text": (
                f"日干关系{_tone(dim_by_key.get('day_stem', {}).get('score', 50))}，"
                f"地支和谐{_tone(dim_by_key.get('branch_harmony', {}).get('score', 50))}。"
                f"甲夫妻宫在{pa.get('day_branch')}，乙在{pb.get('day_branch')}；"
                "日支冲克提示亲密关系中的节奏冲突，六合/半合则利于磨合与承诺。"
            ),
        },
        {
            "id": "spouse_star",
            "title": "配偶星",
            "text": (
                f"甲方配偶星{pa.get('spouse_star') or '不显'}"
                f"（{pa.get('spouse_strength') or '—'}），"
                f"乙方配偶星{pb.get('spouse_star') or '不显'}"
                f"（{pb.get('spouse_strength') or '—'}）。"
                "双方配偶星皆有力时，传统上更易「见得到、留得住」；"
                "一方虚浮时，需用沟通与现实经营补结构不足。"
            ),
        },
    ]

    advice: List[str] = []
    if score >= 65:
        advice.append("结构面整体相助，适合在沟通中明确共同目标与节奏。")
    elif score >= 50:
        advice.append("结构面中平，重大决策宜选双方用神较顺的时间窗口。")
    else:
        advice.append("冲克信号偏多，建议先处理边界与期待，再谈长期承诺。")
    if conflicts:
        advice.append("优先化解：" + "；".join(conflicts[:2]) + "。")
    if supports:
        advice.append("可放大的助力：" + "；".join(supports[:2]) + "。")
    advice.append("本解读为确定性结构层叙述，不构成情感或法律建议。")

    return {
        "sections": sections,
        "advice": advice,
        "markdown": _reading_to_markdown(score, level, sections, advice),
    }


def _reading_to_markdown(
    score: int,
    level: str,
    sections: List[Dict[str, str]],
    advice: List[str],
) -> str:
    lines = [f"# 合婚解读 · {score}分 · {level}", ""]
    for sec in sections:
        lines.append(f"## {sec['title']}")
        lines.append(sec["text"])
        lines.append("")
    lines.append("## 行动建议")
    for item in advice:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    r = compare_charts(
        "乙卯 戊寅 庚子 丙子", "male",
        "甲子 丙寅 戊辰 壬子", "female",
    )
    print(r["score"], r["level"])
    print(r["summary"])
    for d in r["dimensions"]:
        print(f"  {d['label']}: {d['score']}")
