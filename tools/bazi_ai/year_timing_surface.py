#!/usr/bin/env python3
"""Product surface for year / 应期 timing — honesty-first API.

Maps symbolic year shortlist quality into **display modes** the product must
respect:

- ``hard_shortlist``: show top-1/2 as structural 应期 candidates (not a prophecy)
- ``soft_hint``: show candidates with explicit uncertainty
- ``trend_only``: refuse a single year; only trend language
- ``unavailable``: no birth date / not a year-event question

Never claims open-ended year accuracy; Contest8 MCQ ceiling with MiniMax is
~31–48% depending on slice. Structural det (chart/yongshen/liuqin) is separate.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from tools.bazi_ai.rule_reasoner import (
    Candidate,
    RuleReasoner,
    is_year_asking_question,
    rank_year_candidates,
)

_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


def _year_pillar_approx(year: int) -> str:
    idx = (int(year) - 1984) % 60
    return _STEMS[idx % 10] + _BRANCHES[idx % 12]


def _extract_years(text: str) -> List[int]:
    return [int(y) for y in re.findall(r"(?:19|20)\d{2}", text or "")]


def _letter_of(option: str) -> str:
    m = re.match(r"\s*([A-Da-d])", option or "")
    return m.group(1).upper() if m else (option or "").strip().upper()[:1]


@dataclass
class YearTimingCandidate:
    year: int
    gan_zhi: str
    score: float
    confidence: str
    reasons: List[str] = field(default_factory=list)
    option_letter: str = ""
    option_text: str = ""


@dataclass
class YearTimingSurface:
    """Product-facing year timing decision."""

    event_kind: Optional[str]
    display_mode: str  # hard_shortlist | soft_hint | trend_only | unavailable
    trust: str  # symbolic | mixed | none
    assert_single_year: bool
    candidates: List[YearTimingCandidate] = field(default_factory=list)
    product_title: str = ""
    product_copy: str = ""
    disclaimer: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# UI / API copy (Chinese).
_DISCLAIMER = (
    "应期为结构符号排序，非确定性预言；开放式「哪年必发生」不作准确率承诺。"
    "结构层（排盘/用神/六亲）与事件层分开披露。"
)

_COPY = {
    "hard_shortlist": (
        "结构应期 shortlist（优先对照）",
        "下列年份在十神/宫位/大运符号上信号较强，产品可**并列展示**候选年，"
        "禁止写成「必在某年」。用户追问时引导对照大运流年叙述。",
    ),
    "soft_hint": (
        "结构应期参考（不确定）",
        "有弱–中等符号信号，仅作参考候选；勿在 UI 上高亮为唯一答案。",
    ),
    "trend_only": (
        "仅趋势，不报具体年份",
        "本题无可靠年份 shortlist，或问题本身是状态/分类题。"
        "请输出运势趋势（如「婚宫不稳、中年宜慎重」），不要点名公历年。",
    ),
    "unavailable": (
        "应期不可用",
        "缺少八字或出生日期，或问题不是年份应期类。",
    ),
}


def _classify_kind(bazi: str, question: str, gender: str, birth_date: str, birth_time: str) -> Optional[str]:
    if not bazi or not birth_date:
        return None
    try:
        r = RuleReasoner(bazi, gender, birth_date, birth_time)
        return r.classify_year_event(question)
    except Exception:
        return None


def _to_candidates(ranked: Sequence[Candidate]) -> List[YearTimingCandidate]:
    out: List[YearTimingCandidate] = []
    for c in ranked:
        blob = f"{c.option or ''} {c.text or ''}"
        years = _extract_years(blob)
        year = years[0] if years else 0
        letter = _letter_of(c.option) or _letter_of(c.text)
        out.append(
            YearTimingCandidate(
                year=year,
                gan_zhi=_year_pillar_approx(year) if year else "",
                score=float(c.score or 0.0),
                confidence=c.confidence or "low",
                reasons=list(c.reasons or []),
                option_letter=letter,
                option_text=(c.text or c.option or "")[:80],
            )
        )
    return out


def resolve_year_timing(
    bazi: str,
    question: str,
    options: Optional[Sequence[str]] = None,
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    top_k: int = 2,
) -> YearTimingSurface:
    """Resolve how the product should present year-timing for *question*.

    *options*: MCQ option strings when available.  If omitted or empty, open-ended
    year asks are treated as ``trend_only`` (no fabricated year list).
    """
    opts = list(options or [])
    kind = _classify_kind(bazi, question, gender, birth_date, birth_time)

    if not bazi or not birth_date:
        title, copy = _COPY["unavailable"]
        return YearTimingSurface(
            event_kind=kind,
            display_mode="unavailable",
            trust="none",
            assert_single_year=False,
            product_title=title,
            product_copy=copy,
            disclaimer=_DISCLAIMER,
            meta={"reason": "missing_bazi_or_birth"},
        )

    # Status MCQs that only mention 婚姻/感情 — not "which year"
    if opts and not is_year_asking_question(question, opts):
        title, copy = _COPY["trend_only"]
        return YearTimingSurface(
            event_kind=kind,
            display_mode="trend_only",
            trust="none",
            assert_single_year=False,
            product_title=title,
            product_copy=copy + "（状态/分类题，非年份应期。）",
            disclaimer=_DISCLAIMER,
            meta={"reason": "not_year_asking"},
        )

    if not opts:
        # No MCQ options: only surface open-ended *year-asking* questions as
        # trend_only. Generic reads (事业/财运) must not spam the UI panel.
        if not is_year_asking_question(question, None):
            title, copy = _COPY["unavailable"]
            return YearTimingSurface(
                event_kind=kind,
                display_mode="unavailable",
                trust="none",
                assert_single_year=False,
                product_title=title,
                product_copy=copy,
                disclaimer=_DISCLAIMER,
                meta={"reason": "not_year_open_ended", "kind": kind},
            )
        title, copy = _COPY["trend_only"]
        return YearTimingSurface(
            event_kind=kind,
            display_mode="trend_only",
            trust="symbolic" if kind else "none",
            assert_single_year=False,
            product_title=title,
            product_copy=copy + "（开放式年份问题：结构层只给趋势。）",
            disclaimer=_DISCLAIMER,
            meta={"reason": "open_ended_no_options", "kind": kind},
        )

    ranked = rank_year_candidates(
        bazi,
        question,
        opts,
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
        top_k=max(2, top_k),
        for_shortlist=True,
    )
    cands = _to_candidates(ranked)
    if not cands:
        title, copy = _COPY["trend_only"]
        return YearTimingSurface(
            event_kind=kind,
            display_mode="trend_only",
            trust="none",
            assert_single_year=False,
            product_title=title,
            product_copy=copy,
            disclaimer=_DISCLAIMER,
            meta={"reason": "empty_shortlist", "kind": kind},
        )

    top = cands[0]
    margin = top.score - cands[1].score if len(cands) > 1 else top.score
    # hard_shortlist: high structural signal — show top-2 as candidates
    if top.confidence == "high" and top.score >= 0.5:
        mode = "hard_shortlist"
        assert_one = False  # still never assert a single year in product
        trust = "symbolic"
    elif top.confidence in ("high", "medium") and top.score >= 0.2:
        mode = "soft_hint"
        assert_one = False
        trust = "mixed"
    else:
        mode = "trend_only"
        assert_one = False
        trust = "none"
        cands = []  # do not leak noisy letters into UI

    title, copy = _COPY[mode]
    shown = cands if mode != "trend_only" else []

    # Optional pure-rule re-rank (大运/驿马). Soft signal only — never assert_single_year.
    critic_meta: Dict[str, Any] = {}
    if shown:
        try:
            from tools.bazi_ai.year_critic import structural_critic_pick

            letter, cmeta = structural_critic_pick(
                bazi,
                question,
                opts,
                gender=gender,
                birth_date=birth_date,
                birth_time=birth_time,
                top_k=max(2, top_k),
            )
            critic_meta = {
                "letter": letter,
                "reason": cmeta.get("reason"),
                "picked_score": cmeta.get("picked_score"),
                "base_top1": cmeta.get("base_top1"),
                # Product: critic may reorder preference but UI still shows multi-candidate.
                "assert_single_year": False,
            }
            if letter:
                for c in shown:
                    if (c.option_letter or "").upper() == letter.upper():
                        if "结构 critic 偏好" not in c.reasons:
                            c.reasons = list(c.reasons or []) + ["结构 critic 偏好（并列参考）"]
                        break
        except Exception:
            critic_meta = {"reason": "critic_unavailable"}

    return YearTimingSurface(
        event_kind=kind,
        display_mode=mode,
        trust=trust,
        assert_single_year=assert_one,
        candidates=shown,
        product_title=title,
        product_copy=copy,
        disclaimer=_DISCLAIMER,
        meta={
            "top_score": top.score,
            "margin": margin,
            "top_confidence": top.confidence,
            "kind": kind,
            "structural_critic": critic_meta,
        },
    )


def format_product_block(surface: YearTimingSurface) -> str:
    """Markdown block for reports / chat UI."""
    lines = [
        f"### {surface.product_title}",
        surface.product_copy,
    ]
    if surface.candidates:
        lines.append("")
        lines.append("| 候选 | 干支 | 分 | 置信 | 信号 |")
        lines.append("|------|------|----|------|------|")
        for c in surface.candidates:
            lab = c.option_letter or (str(c.year) if c.year else "?")
            sig = "；".join(c.reasons[:3]) if c.reasons else "—"
            lines.append(
                f"| {lab} {c.year or ''} | {c.gan_zhi or '—'} | "
                f"{c.score:.2f} | {c.confidence} | {sig} |"
            )
    bridge = (surface.meta or {}).get("liuqin_bridge") or {}
    samples = bridge.get("samples") or []
    if samples:
        lines.append("")
        lines.append("**六亲流年象征取样（联动）**：")
        for s in samples[:6]:
            lines.append(
                f"- {s.get('member_label', '')} {s.get('year')}年"
                f" {s.get('pillar', '')}：{s.get('note', '')}"
            )
    lines.append("")
    lines.append(f"> {surface.disclaimer}")
    return "\n".join(lines)


# event_kind / question → 六亲 member keys for liunian sample bridge
_KIND_MEMBERS = {
    "parent": ("father", "mother"),
    "marriage": ("spouse",),
    "children": ("son", "daughter"),
}

_MEMBER_LABEL = {
    "father": "父亲",
    "mother": "母亲",
    "spouse": "配偶",
    "son": "儿子",
    "daughter": "女儿",
    "brother": "兄弟",
    "sister": "姐妹",
}


def member_keys_for_year_question(
    event_kind: Optional[str], question: str = ""
) -> List[str]:
    """Map year-event kind + question text → liuqin dossier member keys."""
    q = question or ""
    kind = event_kind or ""
    if kind == "parent" or any(t in q for t in ("父", "母", "父母")):
        if "父" in q and "母" not in q and "父母" not in q:
            return ["father"]
        if "母" in q and "父" not in q:
            return ["mother"]
        if kind == "parent" or "父母" in q:
            return ["father", "mother"]
    if kind == "marriage" or any(
        t in q for t in ("结婚", "婚姻", "配偶", "妻子", "丈夫", "二婚", "再婚")
    ):
        return ["spouse"]
    if kind == "children" or any(
        t in q for t in ("子女", "得子", "得女", "生子", "生女", "孩子")
    ):
        return ["son", "daughter"]
    # Explicit 六亲 keywords without event kind
    if "兄弟" in q or "兄" in q:
        return ["brother"]
    if "姐妹" in q or "妹" in q:
        return ["sister"]
    return list(_KIND_MEMBERS.get(kind, ()))


def enrich_year_timing_with_liuqin(
    surface: Dict[str, Any],
    dossier: Optional[Dict[str, Any]],
    *,
    question: str = "",
) -> Dict[str, Any]:
    """Cross-link year_timing_surface with liuqin dossier 流年 samples.

    - Attach ``meta.liuqin_bridge`` (member samples + overlap years)
    - Annotate shortlist candidates whose year hits a symbolic sample
    - For open-ended 六亲 year asks (trend_only), surface samples under bridge
      without promoting them to hard shortlist prophecy

    Mutates and returns *surface* dict (API/JSON shape).
    """
    if not isinstance(surface, dict):
        return surface
    if not isinstance(dossier, dict) or not dossier.get("members"):
        return surface

    meta = dict(surface.get("meta") or {})
    kind = surface.get("event_kind") or meta.get("kind")
    keys = member_keys_for_year_question(kind, question)
    members = dossier.get("members") or {}

    samples: List[Dict[str, Any]] = []
    if keys:
        for k in keys:
            m = members.get(k) or {}
            for s in (m.get("timing") or {}).get("liunian_samples") or []:
                if not isinstance(s, dict):
                    continue
                samples.append(
                    {
                        "member_key": k,
                        "member_label": m.get("label") or _MEMBER_LABEL.get(k, k),
                        "year": s.get("year"),
                        "pillar": s.get("pillar"),
                        "age": s.get("age"),
                        "note": s.get("note"),
                        "kind": "liuqin_symbolic",
                    }
                )
    else:
        # No focused member: still expose a compact multi-member sample set
        # when question mentions 六亲 broadly.
        if any(t in (question or "") for t in ("六亲", "家人", "亲属")):
            for k, m in members.items():
                for s in ((m or {}).get("timing") or {}).get("liunian_samples") or []:
                    if not isinstance(s, dict):
                        continue
                    samples.append(
                        {
                            "member_key": k,
                            "member_label": (m or {}).get("label")
                            or _MEMBER_LABEL.get(k, k),
                            "year": s.get("year"),
                            "pillar": s.get("pillar"),
                            "age": s.get("age"),
                            "note": s.get("note"),
                            "kind": "liuqin_symbolic",
                        }
                    )

    # de-dupe by (member, year), keep chronological
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for s in sorted(samples, key=lambda x: (x.get("year") or 0, x.get("member_key") or "")):
        key = (s.get("member_key"), s.get("year"))
        if key in seen or not s.get("year"):
            continue
        seen.add(key)
        uniq.append(s)
    samples = uniq[:12]

    sample_years = {int(s["year"]) for s in samples if s.get("year")}
    overlap: List[int] = []
    cands = list(surface.get("candidates") or [])
    if cands and sample_years:
        new_cands = []
        for c in cands:
            if not isinstance(c, dict):
                new_cands.append(c)
                continue
            y = c.get("year")
            try:
                yi = int(y) if y else 0
            except (TypeError, ValueError):
                yi = 0
            reasons = list(c.get("reasons") or [])
            if yi and yi in sample_years:
                overlap.append(yi)
                tag = "与六亲流年象征取样重合"
                if tag not in reasons:
                    reasons = reasons + [tag]
                c = {**c, "reasons": reasons, "liuqin_overlap": True}
            new_cands.append(c)
        surface["candidates"] = new_cands

    bridge = {
        "member_keys": keys,
        "samples": samples,
        "overlap_years": sorted(set(overlap)),
        "honesty": "六亲流年为结构象征取样，与应期 shortlist 联动展示；不作必在某年断言。",
    }
    meta["liuqin_bridge"] = bridge
    surface["meta"] = meta

    # Open-ended 六亲 year questions: keep trend_only but ensure product_copy
    # mentions linked samples exist for UI chips.
    if (
        samples
        and surface.get("display_mode") == "trend_only"
        and keys
        and is_year_asking_question(question, None)
    ):
        extra = (
            f" 已联动六亲细断流年象征取样（{len(samples)} 条），"
            "仅作对照，勿当作唯一答案。"
        )
        copy = surface.get("product_copy") or ""
        if "六亲细断流年" not in copy:
            surface["product_copy"] = (copy + extra).strip()

    return surface
