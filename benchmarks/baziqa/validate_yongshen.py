#!/usr/bin/env python3
"""用神 real-accuracy ruler: engine 用神 vs 穷通宝鉴 (classical authority) gold.

Until now 用神 was only measured as *consistency with our own rule engine* (100%).
That is circular. This ruler compares the engine's 用神 against an INDEPENDENT,
authoritative gold — the 穷通宝鉴 调候用神 (tiao_hou.py) — over all 32 MingLi
real 命主. Deterministic both sides → zero API cost.

Outputs the 调候一致率 (does the engine's 用神 overlap the classical 调候用神),
which is a real accuracy signal against a citable source — not just self-consistency.

Usage::
    python benchmarks/baziqa/validate_yongshen.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai import bazi_structural, calendar  # noqa: E402
from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402
from tools.bazi_ai.tiao_hou import tiaohou_yongshen, tiaohou_yongshen_stems  # noqa: E402

DATA = Path("benchmarks/baziqa/data/mingli/data.json")
_ELM = set("木火土金水")


def _bazi(bi: dict) -> str:
    dt = datetime(int(bi["year"]), int(bi["month"]), int(bi["day"]),
                  int(bi.get("hour", 0) or 0), int(bi.get("minute", 0) or 0))
    p = calendar.pillars_for_datetime(dt)
    raw = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    return normalize_bazi(raw) or raw


def _elm_set(s: str) -> set:
    return {x for x in (s or "").replace("，", ",").split(",") if x in _ELM}


def main() -> None:
    qs = json.load(DATA.open(encoding="utf-8"))["questions"]
    seen = set()
    cases = []
    for q in qs:
        cid = q["case_id"]
        if cid in seen:
            continue
        seen.add(cid)
        cases.append(q)

    overlap = 0        # engine 用神 ∩ gold 非空
    engine_in_gold = 0  # engine 全部用神都在 gold 内（完全符合调候）
    gold_covered = 0    # engine 用神覆盖了 gold 全部（充分）
    n = 0
    rows = []
    for q in cases:
        bi = q["birth_info"]
        bazi = _bazi(bi)
        prof = bazi_structural.structural_profile(bazi) or {}
        dm = prof.get("day_master", "")
        mb = prof.get("month_branch", "")
        eng = _elm_set(prof.get("useful_gods", ""))
        gold = tiaohou_yongshen(dm, mb)
        if not eng or not gold:
            continue
        n += 1
        ov = eng & gold
        if ov:
            overlap += 1
        if eng.issubset(gold):
            engine_in_gold += 1
        if gold.issubset(eng):
            gold_covered += 1
        rows.append((q["case_id"], bazi, dm, mb, eng, gold, ov))

    print(f"用神 调候一致性 (engine vs 穷通宝鉴 gold, n={n})\n")
    print(f"  {'指标':<28} {'命中':>10}")
    print(f"  {'与调候gold有交集(任一)':<24} {overlap}/{n} = {overlap/n:.0%}")
    print(f"  {'engine用神全在gold内':<24} {engine_in_gold}/{n} = {engine_in_gold/n:.0%}")
    print(f"  {'engine用神覆盖gold全部':<24} {gold_covered}/{n} = {gold_covered/n:.0%}")
    print(f"\n  gold来源：穷通宝鉴调候（{'' }季节寒暖 + 日干喜用配对），见 tiao_hou.py")

    print(f"\n--- 逐例 (前16) ---")
    for cid, bazi, dm, mb, eng, gold, ov in rows[:16]:
        gold_stems = "、".join(sorted(tiaohou_yongshen_stems(dm, mb)))
        mark = "✓" if ov else "✗"
        miss = sorted(gold - eng)
        extra = sorted(eng - gold)
        print(f"  {cid} {bazi} {dm}/{mb}  engine用神={sorted(eng)} "
              f"gold={sorted(gold)}({gold_stems}) {mark}")
        if not ov:
            print(f"      → engine 缺调候用 {miss}，多了 {extra}")


if __name__ == "__main__":
    main()
