#!/usr/bin/env python3
"""用神 调候一致性 — 大 n 聚合尺子。

``validate_yongshen.py`` 只跑 MingLi 32 命主。本尺子把用神 gold
(``tiaohou_yongshen`` —— 纯函数,任意生辰可算)扩展到全部可用真实生辰数据集:
celebrity50 + contest8(2021–2025) + MingLi,按八字去重,拿到用神调候一致性的
**大 n 稳定估计**。

gold 性质不变:穷通宝鉴调候(日干喜用 ∪ 季节寒暖),确定性、可 cite。
n 只受限于"有完整生辰的真实命主"数量,不再受限于人工标注 —— 这是用神维度
相对六亲的优势(六亲 gold 是杨炎断象标注,扩 n 受限)。

Usage::
    python benchmarks/baziqa/validate_yongshen_full.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai import bazi_structural, calendar  # noqa: E402
from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402
from tools.bazi_ai.tiao_hou import tiaohou_yongshen  # noqa: E402

DATA = Path("benchmarks/baziqa/data")
_ELM = set("木火土金水")


def _bazi(year, month, day, hour, minute) -> str:
    dt = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0))
    p = calendar.pillars_for_datetime(dt)
    raw = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    return normalize_bazi(raw) or raw


def _elm_set(s: str) -> set:
    return {x for x in (s or "").replace("，", ",").split(",") if x in _ELM}


def _collect():
    """Yield (source, id, birth_dict) over all datasets."""
    recs = []
    # celebrity50
    cel = DATA / "celebrity50_zh.json"
    if cel.exists():
        for p in json.load(cel.open(encoding="utf-8")):
            b = (p.get("profile") or {}).get("birth") or {}
            if b.get("year"):
                recs.append(("celebrity50", p.get("person_id", ""), b))
    # contest8 2021–2025 (skip the meta header dict)
    for f in sorted(DATA.glob("contest8_*.json")):
        try:
            arr = json.load(f.open(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for p in arr:
            if not isinstance(p, dict) or "person_id" not in p:
                continue
            b = (p.get("profile") or {}).get("birth") or {}
            if b.get("year"):
                recs.append(("contest8", p.get("person_id", ""), b))
    # mingli (dedup by case_id)
    ml = DATA / "mingli" / "data.json"
    if ml.exists():
        qs = json.load(ml.open(encoding="utf-8")).get("questions", [])
        seen = set()
        for q in qs:
            cid = q.get("case_id", "")
            if cid in seen:
                continue
            seen.add(cid)
            bi = q.get("birth_info") or {}
            if bi.get("year"):
                recs.append(("mingli", cid, bi))
    return recs


def main() -> None:
    recs = _collect()
    by_src: dict = {}
    seen_bazi: dict = {}
    n = overlap = engine_in_gold = gold_covered = dups = 0
    misses = []
    for src, cid, b in recs:
        try:
            bazi = _bazi(b["year"], b["month"], b["day"], b.get("hour", 0), b.get("minute", 0))
        except (KeyError, ValueError):
            continue
        if bazi in seen_bazi:
            dups += 1
            continue
        seen_bazi[bazi] = (src, cid)
        prof = bazi_structural.structural_profile(bazi) or {}
        dm = prof.get("day_master", "")
        mb = prof.get("month_branch", "")
        eng = _elm_set(prof.get("useful_gods", ""))
        gold = tiaohou_yongshen(dm, mb)
        if not eng or not gold:
            continue
        n += 1
        ov = eng & gold
        s = by_src.setdefault(src, [0, 0])
        s[1] += 1
        if ov:
            overlap += 1
            s[0] += 1
        if eng.issubset(gold):
            engine_in_gold += 1
        if gold.issubset(eng):
            gold_covered += 1
        if not ov:
            misses.append((src, cid, bazi, dm, mb, sorted(eng), sorted(gold)))

    print("用神 调候一致性 · 大n聚合 (gold=穷通宝鉴纯函数, 按八字去重)")
    print(f"  数据集: celebrity50 + contest8(2021-2025) + mingli")
    print(f"  生辰总数 {len(recs)}, 八字去重后 {len(seen_bazi)}, 重复 {dups}, 可比较 {n}\n")
    if not n:
        print("  no comparable cases")
        return
    print(f"  {'指标':<28} {'命中':>12}")
    print(f"  {'与调候gold有交集(任一)':<24} {overlap}/{n} = {overlap/n:.1%}")
    print(f"  {'engine用神全在gold内':<24} {engine_in_gold}/{n} = {engine_in_gold/n:.1%}")
    print(f"  {'engine用神覆盖gold全部':<24} {gold_covered}/{n} = {gold_covered/n:.1%}")
    print(f"\n  分数据集(交集命中):")
    for src, (h, t) in sorted(by_src.items()):
        print(f"    {src:<14} {h}/{t} = {h/t:.1%}")
    if misses:
        print(f"\n  不一致 {len(misses)} 例(前 12):")
        for src, cid, bazi, dm, mb, eng, gold in misses[:12]:
            lack = sorted(set(gold) - set(eng))
            print(f"    [{src}] {cid} {bazi} {dm}/{mb} eng={eng} gold={gold} 缺{lack}")


if __name__ == "__main__":
    main()
