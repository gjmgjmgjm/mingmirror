#!/usr/bin/env python3
"""Open-ended event validation on MingLi-Bench (the real-case ruler).

MingLi-Bench (MIT, github.com/DestinyLinker/MingLi-Bench) = 32 real 命主 with
FULL birth time (年月日时分) + verified life events (competition answers), 12
categories, pre-cast charts. This script uses those cases as ground truth:

For each question we hide the 4 options and ask the model an OPEN question
("命主<year>发生何事？"), then check whether the model's free-text prediction
matches the real event (the gold option text). This is the ruler MCQ cannot be:
it rewards actually predicting the event, not letter-picking.

Scoring is intentionally simple (keyword overlap) — the point is a repeatable
real-case signal, not false precision.

Usage::
    python benchmarks/baziqa/validate_mingli.py --limit 8 \
        --api-key $DEEPSEEK_API_KEY
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime  # noqa: E402
from tools.bazi_ai import calendar  # noqa: E402
from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402

DATA = Path("benchmarks/baziqa/data/mingli/data.json")

# stopwords not useful for event matching
_STOP = set("的 了 是 在 和 与 或 也 都 就 还 又 这 那 你 他 她 我 个 们 年 月 日 时 岁 "
            "发生 何事 可能 会 有 没 一个 一种 一些 什么 以下 选项 下列".split())


def _bazi(bi: Dict) -> str:
    try:
        dt = datetime(int(bi["year"]), int(bi["month"]), int(bi["day"]),
                      int(bi.get("hour", 0) or 0), int(bi.get("minute", 0) or 0))
    except (KeyError, ValueError, TypeError):
        return ""
    p = calendar.pillars_for_datetime(dt)
    bazi = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    return normalize_bazi(bazi) or bazi


def _keywords(text: str) -> set:
    """Crude zh keyword set: 2-4 char runs excluding stopwords/single chars."""
    if not text:
        return set()
    cleaned = re.sub(r"[A-DＡ-Ｄ.\s、，。；：！？()（）「」“”'\"<=/]+", "", text)
    kws = set()
    for m in re.findall(r"[一-龥]{2,4}", cleaned):
        if m not in _STOP:
            kws.add(m)
    return kws


def _build_prompt(bazi: str, bi: Dict, q: Dict) -> str:
    gender = "男命" if bi.get("gender") in ("男", "male") else "女命"
    return f"""你是资深命理师。只依据八字命局推算，不许编造。

八字：{bazi}
性别：{gender}
出生：{bi.get('year')}-{bi.get('month')}-{bi.get('day')} {bi.get('hour',0)}:{bi.get('minute',0):02d}

问题（开放式，不给选项）：{q['question']}

请先简要推理（结合原局 + 大运 + 流年，50字以内），再用一句话直接说出最可能发生的【一件】具体事件（要有场景，如"因X破财""认识配偶结婚""交通意外"）。
输出格式：
推理：<推理>
事件：<一句话事件>
"""


async def _call(client, key, base, model, prompt) -> str:
    url = f"{base.rstrip('/')}/chat/completions"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.2, "max_tokens": 600}
    last = None
    for attempt in range(3):
        async with client.post(url, headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"}, json=payload) as resp:
            text = await resp.text()
            if resp.status == 200:
                import json as _json
                data = _json.loads(text)
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
            last = f"HTTP {resp.status}: {text[:200]}"
        if resp.status in (429, 500, 502, 503):
            await asyncio.sleep(2 * (attempt + 1))
            continue
        break
    raise RuntimeError(last or "no response")


def _extract_event(text: str) -> str:
    m = re.search(r"事件[：:]\s*(.+)", text)
    return (m.group(1).strip() if m else text.strip())[:160]


def _score_match(gold_text: str, pred: str, raw: str):
    """Return (matched: bool, how: str). Year questions compare years; else keywords."""
    gold_years = re.findall(r"(?:19|20)\d{2}", gold_text)
    if gold_years:
        pred_years = set(re.findall(r"(?:19|20)\d{2}", pred + " " + raw))
        hit_years = [y for y in gold_years if y in pred_years]
        if hit_years:
            return True, f"年份命中 {hit_years}"
        return False, f"年份未命中 (gold={gold_years}, pred={sorted(pred_years)})"
    gold_kw = _keywords(gold_text)
    pred_kw = _keywords(pred) | _keywords(raw)
    overlap = gold_kw & pred_kw
    return bool(overlap), f"关键词 {sorted(overlap) or '—'}"


CELEB = Path("benchmarks/baziqa/data/celebrity50_zh.json")


def _load_celebrity50(limit: int):
    """Load celebrity50 real persons (full birth time + verified life events) as
    MingLi-shape records: 1 question per person → up to *limit* open-ended calls."""
    persons = json.load(CELEB.open(encoding="utf-8"))
    out = []
    for p in persons:
        bi0 = p["profile"]["birth"]
        bi = {"year": bi0["year"], "month": bi0["month"], "day": bi0["day"],
              "hour": bi0.get("hour", 0) or 0, "minute": bi0.get("minute", 0) or 0,
              "gender": "男" if p["profile"].get("gender") == "male" else "女"}
        q = p["questions"][0]
        opts = []
        for o in q["options"]:
            m = re.match(r"([A-E])\.\s*(.+)", o)
            opts.append({"letter": m.group(1), "text": m.group(2)}
                        if m else {"letter": "", "text": o})
        out.append({"case_id": p.get("name", p.get("person_id", "")),
                    "birth_info": bi, "question": q["question"],
                    "options": opts, "answer": q["answer"], "category": "celebrity"})
        if len(out) >= limit:
            break
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--dataset", choices=["mingli", "celebrity50"], default="mingli")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()

    if args.dataset == "celebrity50":
        questions = _load_celebrity50(args.limit)
        ds_label = "celebrity50 (real persons, verified events)"
    else:
        questions = json.load(DATA.open(encoding="utf-8"))["questions"][: args.limit]
        ds_label = "MingLi"
    key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("ERROR: no API key (pass --api-key or set DEEPSEEK_API_KEY)", file=sys.stderr); return
    print(f"Open-ended validation on {len(questions)} {ds_label} questions ({args.model})\n",
          file=sys.stderr)

    timeout = aiohttp.ClientTimeout(total=90)
    conn = aiohttp.TCPConnector(limit=2)
    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        hit = 0
        per_cat = {}
        for i, q in enumerate(questions, 1):
            bi = q["birth_info"]
            bazi = _bazi(bi)
            gold_opt = next((o for o in q["options"] if o["letter"] == q["answer"]), None)
            gold_text = gold_opt["text"] if gold_opt else ""
            gold_kw = _keywords(gold_text)
            try:
                raw = await _call(session, key, args.base_url, args.model,
                                  _build_prompt(bazi, bi, q))
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}] {q['case_id']} ERROR {exc}", file=sys.stderr); continue
            pred = _extract_event(raw)
            matched, how = _score_match(gold_text, pred, raw)
            if matched:
                hit += 1
            cat = q.get("category", "?")
            per_cat.setdefault(cat, [0, 0]); per_cat[cat][1] += 1
            if matched:
                per_cat[cat][0] += 1
            mark = "✓" if matched else "✗"
            print(f"===== [{i}] {q['case_id']} ({cat}) {mark} =====")
            print(f"  Q: {q['question'][:50]}")
            print(f"  真实事件(gold {q['answer']}): {gold_text[:80]}")
            print(f"  引擎预测: {pred[:80]}")
            print(f"  匹配: {how}")
            print()

    n = len(questions)
    print(f"\n{'='*50}\n开放事件命中率 (n={n}): {hit}/{n} = {hit/n:.0%}")
    print("分类别命中:")
    for c, (h, t) in sorted(per_cat.items(), key=lambda x: -x[1][1]):
        print(f"  {c}: {h}/{t}")


if __name__ == "__main__":
    asyncio.run(main())
