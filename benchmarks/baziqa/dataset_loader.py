#!/usr/bin/env python3
"""Unified loaders for Contest8 / Celebrity50 / MingLi (zero network).

Normalizes heterogeneous JSON into a common ``EvalItem`` shape so offline
harnesses can score year-shortlist, chart integrity, and shuffle controls
without calling any LLM API.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

DATA_DIR = Path(__file__).resolve().parent / "data"

_OPTION_LETTER_RE = re.compile(r"^\s*([A-Da-d])[\.．、:：\s]")


@dataclass
class EvalItem:
    """One multiple-choice evaluation sample."""

    source: str  # contest8 | mingli | celebrity50
    item_id: str
    person_id: str
    question: str
    options: List[str]  # "A. text" form
    answer: str  # single letter A-D
    gender: str  # male | female
    birth_date: str  # YYYY-MM-DD
    birth_time: str  # HH:MM
    birth_year: int = 0
    birth_place: str = ""
    bazi: str = ""  # optional precomputed
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def option_letters(self) -> List[str]:
        return [_option_letter(o) for o in self.options]


def _option_letter(text: str) -> str:
    m = _OPTION_LETTER_RE.match(text or "")
    if m:
        return m.group(1).upper()
    # bare letter
    t = (text or "").strip().upper()
    if t and t[0] in "ABCD":
        return t[0]
    return ""


def _normalize_gender(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"女", "female", "f", "woman"}:
        return "female"
    return "male"


def _fmt_date(y: int, m: int, d: int) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _fmt_time(h: int, mi: int = 0) -> str:
    return f"{int(h):02d}:{int(mi):02d}"


def _normalize_options(options: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for i, opt in enumerate(options):
        if isinstance(opt, dict):
            letter = str(opt.get("letter") or chr(ord("A") + i)).upper()[:1]
            text = str(opt.get("text") or opt.get("content") or "").strip()
            out.append(f"{letter}. {text}" if text else letter)
        else:
            s = str(opt).strip()
            if _OPTION_LETTER_RE.match(s):
                out.append(s)
            else:
                letter = chr(ord("A") + i)
                out.append(f"{letter}. {s}")
    return out


def _normalize_answer(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    if s[0] in "ABCD":
        return s[0]
    m = re.search(r"[ABCD]", s)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# Contest8
# ---------------------------------------------------------------------------


def load_contest8(
    years: Optional[Sequence[int]] = None,
    data_dir: Path = DATA_DIR,
) -> List[EvalItem]:
    """Load Contest8 people/questions. ``years`` defaults to 2021–2025."""
    years = list(years or (2021, 2022, 2023, 2024, 2025))
    items: List[EvalItem] = []
    for y in years:
        path = data_dir / f"contest8_{y}.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            continue
        for rec in raw:
            if not isinstance(rec, dict) or "person_id" not in rec:
                continue
            profile = rec.get("profile") or {}
            birth = profile.get("birth") or {}
            try:
                by, bm, bd = int(birth["year"]), int(birth["month"]), int(birth["day"])
                bh = int(birth.get("hour") or 12)
                bmi = int(birth.get("minute") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            gender = _normalize_gender(profile.get("gender"))
            person_id = str(rec.get("person_id") or "")
            for q in rec.get("questions") or []:
                if not isinstance(q, dict):
                    continue
                ans = _normalize_answer(q.get("answer"))
                opts = _normalize_options(q.get("options") or [])
                if not ans or len(opts) < 2:
                    continue
                items.append(
                    EvalItem(
                        source="contest8",
                        item_id=str(q.get("question_id") or f"{person_id}-Q"),
                        person_id=person_id,
                        question=str(q.get("question") or "").strip(),
                        options=opts,
                        answer=ans,
                        gender=gender,
                        birth_date=_fmt_date(by, bm, bd),
                        birth_time=_fmt_time(bh, bmi),
                        birth_year=by,
                        birth_place=str(birth.get("place") or ""),
                        meta={"contest_year": y},
                    )
                )
    return items


# ---------------------------------------------------------------------------
# MingLi-Bench style (local mingli/data.json)
# ---------------------------------------------------------------------------


def load_mingli(data_dir: Path = DATA_DIR) -> List[EvalItem]:
    path = data_dir / "mingli" / "data.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions = raw.get("questions") if isinstance(raw, dict) else raw
    if not isinstance(questions, list):
        return []
    items: List[EvalItem] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if q.get("has_answer") is False:
            continue
        bi = q.get("birth_info") or {}
        try:
            by, bm, bd = int(bi["year"]), int(bi["month"]), int(bi["day"])
            bh = int(bi.get("hour") or 12)
            bmi = int(bi.get("minute") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        ans = _normalize_answer(q.get("answer"))
        opts = _normalize_options(q.get("options") or [])
        if not ans or len(opts) < 2:
            continue
        items.append(
            EvalItem(
                source="mingli",
                item_id=str(q.get("id") or q.get("question_number") or ""),
                person_id=str(q.get("case_id") or ""),
                question=str(q.get("question") or "").strip(),
                options=opts,
                answer=ans,
                gender=_normalize_gender(bi.get("gender")),
                birth_date=_fmt_date(by, bm, bd),
                birth_time=_fmt_time(bh, bmi),
                birth_year=by,
                birth_place=str(bi.get("location") or bi.get("country") or ""),
                meta={"category": q.get("category")},
            )
        )
    return items


# ---------------------------------------------------------------------------
# Celebrity50 (QA may be under questions; birth under profile)
# ---------------------------------------------------------------------------


def load_celebrity50(data_dir: Path = DATA_DIR) -> List[EvalItem]:
    path = data_dir / "celebrity50_zh.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    items: List[EvalItem] = []
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        profile = rec.get("profile") or {}
        birth = profile.get("birth") or {}
        try:
            by, bm, bd = int(birth["year"]), int(birth["month"]), int(birth["day"])
            bh = int(birth.get("hour") if birth.get("hour") is not None else 12)
            bmi = int(birth.get("minute") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        gender = _normalize_gender(profile.get("gender"))
        person_id = str(rec.get("person_id") or rec.get("name") or "")
        questions = rec.get("questions") or []
        # celebrity50 sometimes stores narrative only; skip empty MCQ
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            ans = _normalize_answer(q.get("answer") or q.get("correct") or q.get("gold"))
            opts = q.get("options")
            if not opts:
                continue
            opts_n = _normalize_options(opts)
            if not ans or len(opts_n) < 2:
                continue
            items.append(
                EvalItem(
                    source="celebrity50",
                    item_id=str(q.get("question_id") or f"{person_id}-Q{i+1}"),
                    person_id=person_id,
                    question=str(q.get("question") or q.get("text") or "").strip(),
                    options=opts_n,
                    answer=ans,
                    gender=gender,
                    birth_date=_fmt_date(by, bm, bd),
                    birth_time=_fmt_time(bh, bmi),
                    birth_year=by,
                    birth_place=str(birth.get("place") or ""),
                    meta={"name": rec.get("name")},
                )
            )
    return items


def load_celebrity_extra_charts(data_dir: Path = DATA_DIR) -> List[Dict[str, Any]]:
    """Precomputed bazi charts (no MCQ) for structural integrity tests."""
    path = data_dir / "celebrity_extra.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in raw if isinstance(r, dict) and r.get("bazi")] if isinstance(raw, list) else []


def iter_all_mcq(
    sources: Optional[Sequence[str]] = None,
    data_dir: Path = DATA_DIR,
) -> Iterator[EvalItem]:
    src = set(sources or ("contest8", "mingli", "celebrity50"))
    if "contest8" in src:
        yield from load_contest8(data_dir=data_dir)
    if "mingli" in src:
        yield from load_mingli(data_dir=data_dir)
    if "celebrity50" in src:
        yield from load_celebrity50(data_dir=data_dir)


def load_summary(data_dir: Path = DATA_DIR) -> Dict[str, int]:
    return {
        "contest8": len(load_contest8(data_dir=data_dir)),
        "mingli": len(load_mingli(data_dir=data_dir)),
        "celebrity50_mcq": len(load_celebrity50(data_dir=data_dir)),
        "celebrity_extra_charts": len(load_celebrity_extra_charts(data_dir=data_dir)),
    }
