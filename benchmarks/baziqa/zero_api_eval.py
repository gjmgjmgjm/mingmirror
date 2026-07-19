#!/usr/bin/env python3
"""Zero-API evaluation harness for Contest8 / MingLi / local charts.

No DEEPSEEK_API_KEY required. Reports:

1. Dataset inventory
2. Chart integrity (celebrity_extra precomputed bazi vs pillars_for_datetime)
3. Year-MCQ pure-rule shortlist top-1 / top-2 / structural-critic hit rates
4. Birthday-shuffle control: structural features must change when birth shifts

Usage::

    python benchmarks/baziqa/zero_api_eval.py
    python benchmarks/baziqa/zero_api_eval.py --sources contest8,mingli
    python benchmarks/baziqa/zero_api_eval.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.baziqa.dataset_loader import (  # noqa: E402
    EvalItem,
    iter_all_mcq,
    load_celebrity_extra_charts,
    load_summary,
)
from tools.bazi_ai.bazi_structural import liuqin_profile, structural_profile  # noqa: E402
from tools.bazi_ai.calendar import pillars_for_datetime  # noqa: E402
from tools.bazi_ai.rule_reasoner import is_year_asking_question  # noqa: E402
from tools.bazi_ai.year_critic import evaluate_year_mcq  # noqa: E402


def compute_bazi(item: EvalItem) -> str:
    if item.bazi:
        return item.bazi
    try:
        y, m, d = map(int, item.birth_date.split("-"))
        hh, mm = 12, 0
        if item.birth_time and ":" in item.birth_time:
            parts = item.birth_time.split(":")
            hh, mm = int(parts[0]), int(parts[1])
        dt = datetime(y, m, d, hh, mm)
        p = pillars_for_datetime(dt)
        return " ".join(p[k] for k in ("year", "month", "day", "hour"))
    except Exception:
        return ""


def eval_chart_integrity(limit: int = 200) -> Dict[str, Any]:
    charts = load_celebrity_extra_charts()[:limit]
    n = hit = 0
    misses: List[Dict[str, str]] = []
    for rec in charts:
        gold = str(rec.get("bazi") or "").strip()
        bd = str(rec.get("birth_date") or "").strip()
        bt = str(rec.get("birth_time") or "00:00").strip() or "00:00"
        if not gold or not bd:
            continue
        try:
            y, m, d = map(int, bd.split("-")[:3])
            hh, mm = 0, 0
            if ":" in bt:
                hh, mm = map(int, bt.split(":")[:2])
            got = pillars_for_datetime(datetime(y, m, d, hh, mm))
            got_s = " ".join(got[k] for k in ("year", "month", "day", "hour"))
        except Exception as exc:
            misses.append({"name": rec.get("name", ""), "error": str(exc)})
            continue
        n += 1
        # Allow hour pillar mismatch when birth_time is midnight placeholder
        gold_parts = gold.split()
        got_parts = got_s.split()
        if len(gold_parts) >= 3 and len(got_parts) >= 3:
            # Compare year/month/day strictly; hour soft if time is 00:00
            same_ymd = gold_parts[:3] == got_parts[:3]
            if bt in ("00:00", "0:00") and same_ymd:
                hit += 1
            elif gold_parts == got_parts:
                hit += 1
            else:
                misses.append(
                    {
                        "name": str(rec.get("name") or ""),
                        "gold": gold,
                        "got": got_s,
                        "birth": f"{bd} {bt}",
                    }
                )
        elif gold_parts == got_parts:
            hit += 1
        else:
            misses.append({"name": str(rec.get("name") or ""), "gold": gold, "got": got_s})
    return {
        "n": n,
        "hit": hit,
        "acc": (hit / n) if n else 0.0,
        "miss_samples": misses[:8],
    }


def eval_year_mcq(
    items: Sequence[EvalItem],
    *,
    limit: int = 0,
) -> Dict[str, Any]:
    year_items = [
        it
        for it in items
        if is_year_asking_question(it.question, it.options)
    ]
    if limit > 0:
        year_items = year_items[:limit]

    by_src: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"n": 0, "top1": 0, "top2": 0, "critic": 0, "scorable": 0}
    )
    total = {"n": 0, "top1": 0, "top2": 0, "critic": 0, "scorable": 0}
    samples: List[Dict[str, Any]] = []

    for it in year_items:
        bazi = compute_bazi(it)
        total["n"] += 1
        by_src[it.source]["n"] += 1
        if not bazi:
            continue
        res = evaluate_year_mcq(
            bazi,
            it.question,
            it.options,
            it.answer,
            gender=it.gender,
            birth_date=it.birth_date,
            birth_time=it.birth_time,
            birth_year=it.birth_year,
        )
        if res["shortlist_size"] <= 0 and not res["critic"]:
            continue
        total["scorable"] += 1
        by_src[it.source]["scorable"] += 1
        if res["top1_hit"]:
            total["top1"] += 1
            by_src[it.source]["top1"] += 1
        if res["top2_hit"]:
            total["top2"] += 1
            by_src[it.source]["top2"] += 1
        if res["critic_hit"]:
            total["critic"] += 1
            by_src[it.source]["critic"] += 1
        if len(samples) < 12:
            samples.append(
                {
                    "id": it.item_id,
                    "source": it.source,
                    "gold": res["gold"],
                    "top1": res["top1"],
                    "critic": res["critic"],
                    "top2_hit": res["top2_hit"],
                    "q": it.question[:60],
                }
            )

    def _rate(num: int, den: int) -> float:
        return (num / den) if den else 0.0

    per_source = {}
    for src, st in by_src.items():
        den = st["scorable"] or st["n"]
        per_source[src] = {
            **st,
            "top1_acc": _rate(st["top1"], st["scorable"]),
            "top2_acc": _rate(st["top2"], st["scorable"]),
            "critic_acc": _rate(st["critic"], st["scorable"]),
        }

    return {
        "year_questions": total["n"],
        "scorable": total["scorable"],
        "top1_hit": total["top1"],
        "top2_hit": total["top2"],
        "critic_hit": total["critic"],
        "top1_acc": _rate(total["top1"], total["scorable"]),
        "top2_acc": _rate(total["top2"], total["scorable"]),
        "critic_acc": _rate(total["critic"], total["scorable"]),
        "per_source": per_source,
        "samples": samples,
    }


def eval_shuffle_control(items: Sequence[EvalItem], *, n: int = 40) -> Dict[str, Any]:
    """Structural features should change when birth is shifted by ~180 days."""
    checked = changed = 0
    for it in items[: max(n * 3, n)]:
        if checked >= n:
            break
        bazi = compute_bazi(it)
        if not bazi:
            continue
        try:
            y, m, d = map(int, it.birth_date.split("-"))
            hh, mm = 12, 0
            if ":" in it.birth_time:
                hh, mm = map(int, it.birth_time.split(":")[:2])
            dt0 = datetime(y, m, d, hh, mm)
            dt1 = dt0 + timedelta(days=180)
            p0 = pillars_for_datetime(dt0)
            p1 = pillars_for_datetime(dt1)
            s0 = structural_profile(" ".join(p0[k] for k in ("year", "month", "day", "hour")))
            s1 = structural_profile(" ".join(p1[k] for k in ("year", "month", "day", "hour")))
            if not s0 or not s1:
                continue
            checked += 1
            # Day master or month branch or useful gods should differ for +180d
            if (
                s0.get("day_master") != s1.get("day_master")
                or s0.get("month_branch") != s1.get("month_branch")
                or s0.get("useful_gods") != s1.get("useful_gods")
            ):
                changed += 1
            else:
                # still compare liuqin fingerprints
                l0 = liuqin_profile(
                    " ".join(p0[k] for k in ("year", "month", "day", "hour")),
                    gender=it.gender,
                )
                l1 = liuqin_profile(
                    " ".join(p1[k] for k in ("year", "month", "day", "hour")),
                    gender=it.gender,
                )
                fp0 = tuple(
                    (l0 or {}).get(k, {}).get("strength")
                    for k in ("father", "mother", "spouse")
                )
                fp1 = tuple(
                    (l1 or {}).get(k, {}).get("strength")
                    for k in ("father", "mother", "spouse")
                )
                if fp0 != fp1:
                    changed += 1
        except Exception:
            continue
    return {
        "n": checked,
        "changed": changed,
        "change_rate": (changed / checked) if checked else 0.0,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sources",
        type=str,
        default="contest8,mingli,celebrity50",
        help="comma list: contest8,mingli,celebrity50",
    )
    ap.add_argument("--year-limit", type=int, default=0, help="cap year MCQ eval (0=all)")
    ap.add_argument("--json", type=str, default="", help="write full report JSON")
    args = ap.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    inventory = load_summary()
    items = list(iter_all_mcq(sources=sources))

    print("=" * 64)
    print("Zero-API 命理评测（无需 DEEPSEEK_API_KEY）")
    print("=" * 64)
    print("\n[库存]")
    for k, v in inventory.items():
        print(f"  {k}: {v}")
    print(f"  loaded_mcq (filtered sources={sources}): {len(items)}")

    integrity = eval_chart_integrity()
    print("\n[排盘一致性] celebrity_extra 预计算八字 vs pillars_for_datetime")
    print(
        f"  {integrity['hit']}/{integrity['n']} = {integrity['acc']:.1%}"
        f"  (时辰 00:00 仅比对年月日柱)"
    )
    if integrity["miss_samples"]:
        print("  miss 样例:")
        for m in integrity["miss_samples"][:3]:
            print(f"    {m}")

    year_rep = eval_year_mcq(items, limit=args.year_limit)
    print("\n[年份 MCQ · 纯规则 shortlist + 结构 critic]")
    print(f"  年份题: {year_rep['year_questions']}  可打分(有 shortlist): {year_rep['scorable']}")
    if year_rep["scorable"]:
        print(
            f"  top-1: {year_rep['top1_hit']}/{year_rep['scorable']} = {year_rep['top1_acc']:.1%}"
        )
        print(
            f"  top-2: {year_rep['top2_hit']}/{year_rep['scorable']} = {year_rep['top2_acc']:.1%}"
        )
        print(
            f"  critic: {year_rep['critic_hit']}/{year_rep['scorable']} = {year_rep['critic_acc']:.1%}"
        )
        for src, st in year_rep["per_source"].items():
            if st["scorable"]:
                print(
                    f"    · {src}: top1={st['top1_acc']:.0%} top2={st['top2_acc']:.0%} "
                    f"critic={st['critic_acc']:.0%} (n={st['scorable']})"
                )
    else:
        print("  （无可用 shortlist 的年份题）")

    shuffle = eval_shuffle_control(items, n=40)
    print("\n[生日 shuffle 对照] +180 天结构特征应变化")
    print(
        f"  changed {shuffle['changed']}/{shuffle['n']} = {shuffle['change_rate']:.1%}"
    )

    print("\n说明:")
    print("  · 年份 top-2 是 shortlist 上限；critic 为纯规则重排，不调用 LLM。")
    print("  · 非年份题不在此 harness 计分（需 LLM 或专项规则）。")
    print("  · 结构层 gold 尺子仍用: python benchmarks/baziqa/accuracy_report.py")
    print("=" * 64)

    report = {
        "inventory": inventory,
        "loaded_mcq": len(items),
        "chart_integrity": integrity,
        "year_mcq": year_rep,
        "shuffle": shuffle,
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
