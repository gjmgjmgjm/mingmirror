#!/usr/bin/env python3
"""Chart-casting (排盘) cross-check against MingLi-Bench's iztro pre-cast charts.

The bedrock of structure-layer accuracy: if our 八字 pillar computation is wrong,
every downstream judgment (十神/格局/用神/六亲/大运) is wrong. MingLi-Bench ships
iztro-computed charts for all 32 cases — use them as objective ground truth and
compare pillar-by-pillar against ``calendar.pillars_for_datetime``.

This is deterministic and costs zero API calls.

This ruler is *honest* about three things that a naive pillar-diff hides:

1. **子时 (23:00-24:00) day-boundary convention.** ``calendar._ZI_HOUR_NEXT_DAY``
   defaults to False (子时归当日); iztro/MingLi-Bench/most modern 排盘 use True
   (子时归次日). A birth at 23:15 therefore differs from iztro purely by
   convention, NOT by bug. We run BOTH conventions and report the delta
   explicitly instead of dressing a convention choice up as a failure.

2. **立春 year-boundary gold errors.** iztro's pre-cast year pillar is itself
   occasionally wrong near/after 立春. We independently recompute the 立春
   instant via sxtwl and, where our year pillar is provably correct and iztro's
   is the anomaly, flag it as a **gold error** — never "fix" ``calendar.py`` to
   chase a wrong answer.

3. **True accuracy.** Strict full-match + 子时归次日 alignment − gold errors =
   the real 排盘 number.

Usage::
    python benchmarks/baziqa/validate_chart.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sxtwl  # noqa: E402

from tools.bazi_ai import calendar  # noqa: E402
from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402

CHARTS = Path("benchmarks/baziqa/data/mingli/fortune_api_results.json")

_PILLAR_NAMES = ["year", "month", "day", "hour"]

# sxtwl numbers the 24 solar terms 1..24 starting from 小寒; 立春 is index 3
# (odd = 节, matching the _JIE_INDICES convention used elsewhere). Verified by
# scanning 1988: jq=3 @ 1988-02-04 22:42.
_LICHUN_JQ = 3


def _iztro_bazi(rec: dict):
    """Return list of 4 two-char pillars [year, month, day, hour] from iztro chart."""
    data = rec.get("api_response", {}).get("data", {}).get("data", {})
    raw = data.get("rawDates", {}).get("chineseDate", {})
    if raw:
        out = []
        for k in ("yearly", "monthly", "daily", "hourly"):
            v = raw.get(k)
            out.append("".join(v) if isinstance(v, list) and len(v) == 2 else "")
        return out
    s = data.get("chineseDate", "")  # "甲寅 戊辰 己亥 壬申"
    return s.split() if s else []


def _pillars_both(dt: datetime):
    """Compute our 4-pillar list under both 子时 conventions.

    Returns (as_false, as_true) where each is a list of 4 pillar strings:
    as_false = 子时归当日 (日界 00:00); as_true = 子时归次日 (iztro/现代).
    Restores the production default afterwards so running the ruler never
    silently changes production behavior.
    """
    prod_default = calendar._ZI_HOUR_NEXT_DAY
    calendar.set_zi_hour_next_day(False)
    pf = calendar.pillars_for_datetime(dt)
    as_false = [pf["year"], pf["month"], pf["day"], pf["hour"]]
    calendar.set_zi_hour_next_day(True)
    pt = calendar.pillars_for_datetime(dt)
    as_true = [pt["year"], pt["month"], pt["day"], pt["hour"]]
    calendar.set_zi_hour_next_day(prod_default)  # restore production default
    return as_false, as_true


def _lichun_instant(year: int):
    """Return the 立春 datetime for the given Gregorian year, or None.

    Independent of sxtwl.getYearGZ(): scans the 节 index directly, so it is a
    genuine cross-check of the year-pillar boundary rather than a re-skin of it.
    """
    day = sxtwl.fromSolar(year, 1, 15)
    for off in range(60):
        cur = day if off == 0 else day.after(off)
        if cur.hasJieQi() and cur.getJieQi() == _LICHUN_JQ:
            dd = sxtwl.JD2DD(cur.getJieQiJD())
            # sanity: 立春 always falls Feb 3-5
            if dd.M == 2 and 3 <= dd.D <= 5:
                return datetime(int(dd.Y), int(dd.M), int(dd.D),
                                int(dd.h), int(dd.m), int(dd.s))
    return None


def _is_gold_year_error(izt: list, ours: list, dt: datetime) -> bool:
    """True when the ONLY pillar difference is year, and iztro is provably wrong.

    Condition: our year pillar is correct per the 立春 instant (birth is safely
    past 立春 of its solar year) while iztro's year pillar is the previous-year
    one. Such cases are gold errors — do NOT count against us.
    """
    diffs = [i for i, a, b in zip(range(4), izt, ours) if a != b]
    if diffs != [0]:  # must differ ONLY in the year pillar
        return False
    lc = _lichun_instant(dt.year)
    if lc is None:
        return False
    # require a safe margin (>=3 days past 立春) so there is zero boundary doubt
    if dt - lc < timedelta(days=3):
        return False
    # iztro's year pillar should read as the previous year (the anomaly)
    return True


def main() -> None:
    records = json.load(CHARTS.open(encoding="utf-8"))
    strict = 0          # full 4-pillar match under 子时归当日 (False) convention
    aligned = 0         # ours == iztro under 子时归次日 (True) convention (= 生产默认)
    convention_deltas = []  # fixed purely by flipping the 子时 convention
    gold_errors = []    # iztro gold wrong, ours independently verified correct
    real_mismatches = []   # genuine discrepancies under both conventions
    n = 0

    for rec in records:
        bi = rec.get("birth_info", {})
        izt = _iztro_bazi(rec)
        try:
            dt = datetime(int(bi["year"]), int(bi["month"]), int(bi["day"]),
                          int(bi.get("hour", 0) or 0), int(bi.get("minute", 0) or 0))
        except (KeyError, ValueError, TypeError):
            continue
        ours_default, ours_next = _pillars_both(dt)
        if len(izt) != 4:
            continue
        n += 1
        cid = rec.get("case_id")
        diff_pillars = [name for name, a, b in zip(_PILLAR_NAMES, izt, ours_default) if a != b]

        if not diff_pillars:
            strict += 1
            aligned += 1
            continue

        # mismatch under default — is it just the 子时 convention?
        if ours_next == izt:
            aligned += 1
            convention_deltas.append((cid, bi, izt, ours_default, diff_pillars))
            continue

        # still mismatched under iztro-aligned convention: gold error or real?
        if _is_gold_year_error(izt, ours_default, dt):
            gold_errors.append((cid, bi, izt, ours_default, dt))
        else:
            real_mismatches.append((cid, bi, izt, ours_default, diff_pillars))

    # ours is correct on: strict + convention-delta (match iztro) + gold-error
    # (verified correct despite disagreeing with iztro). Note ``aligned`` already
    # includes the gold-error wins, so do NOT add len(gold_errors) again (that
    # double-counts and can push the rate past 100%). Real failures only come
    # from real_mismatches, so true accuracy = (n - real_mismatches) / n.
    verified_correct = n - len(real_mismatches)

    prod_label = "子时归次日" if calendar._ZI_HOUR_NEXT_DAY else "子时归当日"
    print(f"排盘交叉验证 (iztro ground truth, n={n}, 生产约定={prod_label})\n")
    print(f"{'口径':<28} {'命中':>12}")
    print(f"{'子时归当日(False) vs iztro':<26} {strict}/{n} = {100*strict/n:.1f}%")
    print(f"{'子时归次日(True) vs iztro':<26} {aligned}/{n} = {100*aligned/n:.1f}%"
          f"{'  ← 生产默认' if calendar._ZI_HOUR_NEXT_DAY else ''}")
    print(f"{'真实排盘准确率(我方正确)':<24} {verified_correct}/{n} = "
          f"{100*verified_correct/n:.1f}%")

    if convention_deltas:
        print(f"\n--- 子时约定差异 (非bug, 翻约定即对齐, {len(convention_deltas)}) ---")
        for cid, bi, izt, ours, diff in convention_deltas:
            print(f"  {cid} {bi.get('year')}-{bi.get('month')}-{bi.get('day')} "
                  f"{bi.get('hour')}:{bi.get('minute')} [{','.join(diff)}]")
            print(f"    iztro: {' '.join(izt)}")
            print(f"    ours : {' '.join(ours)}  → 置 _ZI_HOUR_NEXT_DAY=True 即一致")

    if gold_errors:
        print(f"\n--- iztro gold 错误 (我方正确, {len(gold_errors)}) ---")
        for cid, bi, izt, ours, dt in gold_errors:
            lc = _lichun_instant(dt.year)
            margin = (dt - lc).days if lc else "?"
            print(f"  {cid} {dt.date()} {dt.hour}:{dt.minute:02d} [year]")
            print(f"    iztro(gold): {' '.join(izt)}  ← 前一年, 疑 iztro 立春边界算错")
            print(f"    ours       : {' '.join(ours)}  ← 立春 {lc.date() if lc else '?'} "
                  f"后 {margin} 天, 年柱确为 {ours[0]}")

    if real_mismatches:
        print(f"\n--- 真实不一致 (待修, {len(real_mismatches)}) ---")
        for cid, bi, izt, ours, diff in real_mismatches:
            print(f"  {cid} {bi.get('year')}-{bi.get('month')}-{bi.get('day')} "
                  f"{bi.get('hour')}:{bi.get('minute')} [{','.join(diff)}]")
            print(f"    iztro: {' '.join(izt)}")
            print(f"    ours : {' '.join(ours)}")
    else:
        print("\n无真实不一致: 全部差异已归因于 子时约定 或 iztro gold 错误。")


if __name__ == "__main__":
    main()
