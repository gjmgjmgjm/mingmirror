#!/usr/bin/env python3
"""Pure-rule year shortlist critic (zero LLM / zero API).

Given a question + options, ``rank_year_candidates`` builds a shortlist.
``structural_critic_pick`` then re-ranks the shortlist with extra structural
signals (大运干支贴合、驿马引动、分数 margin) and returns a single letter.

Use for offline MCQ eval and as a hard override when confidence is high.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from tools.bazi_ai.calendar import dayun_list
from tools.bazi_ai.rule_reasoner import (
    Candidate,
    RuleReasoner,
    is_year_asking_question,
    rank_year_candidates,
)

_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"

# 年支 → 驿马
_YIMA = {
    "申": "寅",
    "子": "寅",
    "辰": "寅",
    "寅": "申",
    "午": "申",
    "戌": "申",
    "巳": "亥",
    "酉": "亥",
    "丑": "亥",
    "亥": "巳",
    "卯": "巳",
    "未": "巳",
}


def _year_pillar_approx(year: int) -> str:
    """Gregorian year → 年柱 (立春近似：整年用该公历年干支)."""
    idx = (int(year) - 1984) % 60
    return _STEMS[idx % 10] + _BRANCHES[idx % 12]


def _extract_years(text: str) -> List[int]:
    return [int(y) for y in re.findall(r"(?:19|20)\d{2}", text or "")]


def _letter_of(option: str) -> str:
    m = re.match(r"\s*([A-Da-d])", option or "")
    return m.group(1).upper() if m else ""


def structural_critic_score(
    cand: Candidate,
    *,
    bazi: str,
    gender: str,
    birth_date: str,
    birth_time: str = "00:00",
    birth_year: int = 0,
) -> float:
    """Re-score one shortlist candidate with extra structural bonuses."""
    score = float(cand.score or 0.0)
    blob = " ".join(
        [
            cand.option or "",
            cand.text or "",
            " ".join(cand.reasons or []),
        ]
    )
    years = _extract_years(blob)
    if not years:
        return score
    year = years[0]
    yp = _year_pillar_approx(year)
    y_stem, y_branch = yp[0], yp[1]

    # 大运贴合：事件年落在某步大运内，且大运干/支与流年干支相同或相合
    try:
        periods = dayun_list(bazi, gender, birth_date, birth_time, until_age=90)
    except Exception:
        periods = []
    age = year - birth_year if birth_year else None
    if age is not None and periods:
        for p in periods:
            try:
                a0, a1 = float(p.get("start_age") or 0), float(p.get("end_age") or 0)
            except (TypeError, ValueError):
                continue
            if a0 <= age <= a1 + 0.01:
                score += 0.15
                pillar = str(p.get("pillar") or "")
                if len(pillar) >= 2:
                    if pillar[0] == y_stem:
                        score += 0.25
                    if pillar[1] == y_branch:
                        score += 0.25
                break

    # 驿马：流年支为命局年支驿马
    compact = (bazi or "").replace(" ", "")
    year_zhi = compact[1] if len(compact) >= 2 else ""
    yima = _YIMA.get(year_zhi, "")
    if yima and y_branch == yima:
        score += 0.2

    # Confidence margin already encoded in Candidate; boost high conf
    if cand.confidence == "high":
        score += 0.1
    elif cand.confidence == "low":
        score -= 0.05

    return score


def structural_critic_pick(
    bazi: str,
    question: str,
    options: Sequence[str],
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    birth_year: int = 0,
    top_k: int = 2,
) -> Tuple[str, Dict]:
    """Pick a single option letter using shortlist + structural re-rank.

    Returns ``(letter, meta)`` where letter may be empty if not applicable.
    """
    opts = list(options)
    if not bazi or not birth_date or not is_year_asking_question(question, opts):
        return "", {"reason": "not_year_or_missing_birth"}

    shortlist = rank_year_candidates(
        bazi,
        question,
        opts,
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
        top_k=max(2, top_k),
        for_shortlist=True,
    )
    if not shortlist:
        # fallback: ungated rank for offline eval coverage
        shortlist = rank_year_candidates(
            bazi,
            question,
            opts,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
            top_k=max(2, top_k),
            for_shortlist=False,
        )
    if not shortlist:
        return "", {"reason": "empty_shortlist"}

    by_year = birth_year
    if not by_year and len(birth_date) >= 4:
        try:
            by_year = int(birth_date[:4])
        except ValueError:
            by_year = 0

    rescored: List[Tuple[float, Candidate]] = []
    for c in shortlist:
        s = structural_critic_score(
            c,
            bazi=bazi,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
            birth_year=by_year,
        )
        rescored.append((s, c))
    rescored.sort(key=lambda t: t[0], reverse=True)
    best_score, best = rescored[0]
    base = shortlist[0]
    base_letter = _letter_of(base.option) or base.option.strip().upper()[:1]
    base_critic = next(
        (s for s, c in rescored if _letter_of(c.option) == base_letter),
        float(base.score or 0.0),
    )
    # Only override top-1 when critic finds a clear upgrade (margin ≥ 0.2).
    # Prevents pure re-noise that drops below baseline top-1 hit rate.
    if best_score >= base_critic + 0.2:
        letter = _letter_of(best.option) or best.option.strip().upper()[:1]
        reason = "critic_override"
    else:
        letter = base_letter
        reason = "keep_top1"
        best_score = base_critic
    meta = {
        "reason": reason,
        "shortlist": [
            {
                "option": c.option,
                "base_score": c.score,
                "confidence": c.confidence,
                "critic_score": s,
                "letter": _letter_of(c.option),
            }
            for s, c in rescored
        ],
        "picked_score": best_score,
        "base_top1": shortlist[0].option,
    }
    return letter, meta


def evaluate_year_mcq(
    bazi: str,
    question: str,
    options: Sequence[str],
    gold: str,
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    birth_year: int = 0,
) -> Dict:
    """Score one year MCQ offline: top1 / top2 / critic hit."""
    gold_l = (gold or "").strip().upper()[:1]
    shortlist = rank_year_candidates(
        bazi,
        question,
        list(options),
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
        top_k=2,
        for_shortlist=False,
    )
    letters = [_letter_of(c.option) for c in shortlist]
    top1 = letters[0] if letters else ""
    top2_hit = gold_l in letters[:2] if letters else False
    critic_letter, meta = structural_critic_pick(
        bazi,
        question,
        options,
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
        birth_year=birth_year,
    )
    return {
        "gold": gold_l,
        "top1": top1,
        "top1_hit": top1 == gold_l and bool(top1),
        "top2_hit": top2_hit,
        "critic": critic_letter,
        "critic_hit": critic_letter == gold_l and bool(critic_letter),
        "shortlist_size": len(shortlist),
        "meta": meta,
    }
