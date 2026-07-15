#!/usr/bin/env python3
"""过去验证 (past-validation) harness — the product-truth accuracy ruler.

This is the ruler that measures what the product actually faces: given a REAL
person's birth, does the engine's reading match their KNOWN past? Unlike MCQ or
self-consistency, this validates the full reading (财富/婚姻/职业/健康/六亲/事件)
against ground truth the person provides. It is the pre-launch answer to
"how accurate is this for real people" — recruit N volunteers, have them fill
known_facts, run this.

Volunteer record schema (see volunteer_template.json):
    {
      "birth": {"year","month","day","hour","minute"},
      "gender": "男"|"女",
      "known_facts": {                 # all fields OPTIONAL — score what's present
        "wealth": "中产",              # 贫/温饱/小康/中产/小富/中富/大富/巨富
        "marriage_year": 2006,
        "career": ["公职","管理"],     # keyword hints
        "health": ["心脏"],
        "liuqin": {"配偶":"强"},       # 强/弱 per family member
        "events": [{"year":2018,"event":"父亲去世"}]
      }
    }

Scoring reuses the extractors from validate_real/validate_mingli. Each present
fact is scored; absent facts are skipped (not counted against). This runs the
FULL analyze_bazi reading (costs 1 API call per person).

Usage::
    DEEPSEEK_API_KEY=... python benchmarks/baziqa/validate_past.py \
        benchmarks/baziqa/volunteer_template.json --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.engine import analyze_bazi  # noqa: E402

_WEALTH_BUCKET = {
    "贫": "穷", "温饱": "穷", "小康": "中", "中产": "中",
    "小富": "富", "中富": "富", "大富": "富", "巨富": "富",
}


def _wealth_bucket(level: str) -> str:
    for k, v in _WEALTH_BUCKET.items():
        if k in (level or ""):
            return v
    return "?"


def _years(text: str) -> set:
    return set(re.findall(r"(?:19|20)\d{2}", text or ""))


def _kw_hit(text: str, keys: List[str]) -> List[str]:
    return sorted({k for k in keys if k in (text or "")})


def _liuqin_section(liuqin, subject: str) -> str:
    if not isinstance(liuqin, str):
        return ""
    label = {"配偶": "【配偶】", "父亲": "【父亲】", "母亲": "【母亲】", "子女": "【子女】"}.get(subject, "")
    if not label or label not in liuqin:
        return liuqin[:200]
    start = liuqin.index(label) + len(label)
    nxt = liuqin.find("【", start)
    return liuqin[start:nxt if nxt != -1 else len(liuqin)]


def _strength(text: str) -> str:
    s = sum(1 for t in ["真星", "强根", "通根", "得令", "有力", "稳固", "旺"] if t in text)
    w = sum(1 for t in ["假星", "无根", "虚浮", "受克", "绝地", "弱", "缘薄", "不稳"] if t in text)
    return "强" if s > w else ("弱" if w > s else "?")


async def _score_one_birth(rec: dict, key, base, model) -> dict:
    from tools.bazi_ai import calendar
    from tools.bazi_ai.bazi_validator import normalize_bazi
    bi = rec["birth"]
    dt = datetime(int(bi["year"]), int(bi["month"]), int(bi["day"]),
                  int(bi.get("hour", 0)), int(bi.get("minute", 0)))
    p = calendar.pillars_for_datetime(dt)
    bazi = normalize_bazi(f"{p['year']} {p['month']} {p['day']} {p['hour']}") or \
        f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    gender = rec.get("gender", "男")
    gender = "male" if gender in ("男", "male") else "female"
    res = await analyze_bazi(bazi, gender=gender, api_key=key, base_url=base, model=model)
    return res


def _score(res: dict, facts: dict) -> dict:
    """Return per-dimension {dim: (hit_bool, detail)} for present facts."""
    out = {}
    da = (res.get("domain_analysis") or {})
    if "wealth" in facts:
        eng = _wealth_bucket(res.get("wealth_level", ""))
        gold = _wealth_bucket(facts["wealth"])
        out["财富"] = (eng != "?" and gold != "?" and eng == gold, f"engine={eng} gold={gold}")
    if "marriage_year" in facts:
        eng_years = _years(da.get("marriage", "") + " " + (res.get("marriage_evidence") or ""))
        out["婚姻年"] = (str(facts["marriage_year"]) in eng_years,
                       f"gold={facts['marriage_year']} engine年={sorted(eng_years)}")
    if "career" in facts:
        eng_kw = _kw_hit(da.get("career", ""), facts["career"])
        out["职业"] = (bool(eng_kw), f"交集={eng_kw}")
    if "health" in facts:
        eng_kw = _kw_hit(da.get("health", ""), facts["health"])
        out["健康"] = (bool(eng_kw), f"交集={eng_kw}")
    if "liuqin" in facts:
        lq = res.get("liuqin_analysis", "")
        for subj, gold_str in facts["liuqin"].items():
            eng_str = _strength(_liuqin_section(lq, subj))
            out[f"六亲:{subj}"] = (eng_str != "?" and eng_str == gold_str,
                                   f"gold={gold_str} engine={eng_str}")
    if "events" in facts:
        # event match: engine milestones/events contain the gold year + a keyword
        eng_text = json.dumps(res.get("milestones", []), ensure_ascii=False) + \
            " ".join(res.get("events", []))
        for ev in facts["events"]:
            yr = str(ev.get("year", ""))
            ev_kw = [k for k in re.findall(r"[一-龥]{2,}", ev.get("event", "")) if len(k) >= 2][:3]
            hit = (not yr or yr in eng_text) and (not ev_kw or any(k in eng_text for k in ev_kw))
            out[f"事件:{ev.get('event','')[:12]}"] = (hit, ev.get("event", "")[:30])
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", nargs="?", default="benchmarks/baziqa/volunteer_template.json")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()
    key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("no API key", file=sys.stderr); return
    recs = [json.loads(l) for l in Path(args.data).open(encoding="utf-8") if l.strip()][: args.limit]
    print(f"过去验证 on {len(recs)} 人 (模型 {args.model})\n", file=sys.stderr)
    totals = {}  # dim -> [hit, n]
    for i, rec in enumerate(recs, 1):
        res = await _score_one_birth(rec, key, args.base_url, args.model)
        scores = _score(res, rec.get("known_facts", {}))
        hits = [d for d, (h, _) in scores.items() if h]
        print(f"===== [{i}] {rec.get('source','')} =====")
        for d, (h, detail) in scores.items():
            bucket = d.split(":")[0]  # 事件:... → 事件 ; 六亲:配偶 → 六亲
            totals.setdefault(bucket, [0, 0]); totals[bucket][1] += 1
            if h:
                totals[bucket][0] += 1
            print(f"  {'✓' if h else '✗'} {d}: {detail}")
        if not scores:
            print("  (无 known_facts，跳过)")
        print()
    if totals:
        print("=" * 50)
        print("过去验证命中率（按维度，仅统计已提供的事实）:")
        for d, (h, n) in sorted(totals.items()):
            print(f"  {d}: {h}/{n} = {h/n:.0%}")


if __name__ == "__main__":
    asyncio.run(main())
