#!/usr/bin/env python3
"""Offline measure: rule-engine top-1 / top-2 ceiling on contest8 year questions."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import load_baziqa, person_to_bazi  # noqa: E402
from tools.bazi_ai.rule_reasoner import (  # noqa: E402
    RuleReasoner,
    apply_rule_reasoner,
    rank_year_candidates,
)


def _gender(person: dict) -> str:
    g = person.get("profile", {}).get("gender", "male")
    if g in ("女", "female", "f", "F"):
        return "female"
    return "male"


def main() -> None:
    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    top1 = top2 = n = 0
    by_conf = {"high": [0, 0], "medium": [0, 0], "low": [0, 0]}
    by_kind: dict = {}
    gold_in_shortlist_non_high = 0
    non_high = 0
    hard_override_ok = hard_override_n = 0

    for person in contest:
        bazi = person_to_bazi(person)
        if not bazi:
            continue
        birth = person.get("profile", {}).get("birth", {})
        g = _gender(person)
        bd = f"{birth['year']:04d}-{birth['month']:02d}-{birth['day']:02d}"
        bt = f"{birth.get('hour', 0):02d}:{birth.get('minute', 0):02d}"
        for q in person.get("questions", []):
            qtext = q.get("question", "")
            opts = q.get("options", [])
            ans = (q.get("answer") or "").strip().upper()[:1]
            if not ans or not any(re.search(r"19\d{2}|20\d{2}", o) for o in opts):
                continue
            ranked = rank_year_candidates(
                bazi, qtext, opts, gender=g, birth_date=bd, birth_time=bt, top_k=2
            )
            if not ranked:
                continue
            n += 1
            reasoner = RuleReasoner(bazi, g, bd, bt)
            kind = reasoner.classify_year_event(qtext) or "?"
            by_kind.setdefault(kind, [0, 0, 0])  # top1, top2, n
            labels = [c.option for c in ranked]
            conf = ranked[0].confidence
            if ans == labels[0]:
                top1 += 1
                by_conf[conf][0] += 1
                by_kind[kind][0] += 1
            by_conf[conf][1] += 1
            by_kind[kind][2] += 1
            if ans in labels[:2]:
                top2 += 1
                by_kind[kind][1] += 1
            if conf != "high":
                non_high += 1
                if ans in labels[:2]:
                    gold_in_shortlist_non_high += 1

            hard = apply_rule_reasoner(
                bazi,
                qtext,
                opts,
                gender=g,
                birth_date=bd,
                birth_time=bt,
                min_confidence="high",
            )
            if hard is not None:
                hard_override_n += 1
                if hard == ans:
                    hard_override_ok += 1

    print(f"year rule-dispatch n={n}")
    if n:
        print(f"top1={top1 / n:.1%} ({top1}/{n})")
        print(f"top2={top2 / n:.1%} ({top2}/{n})")
        for c in ("high", "medium", "low"):
            ok, tot = by_conf[c]
            rate = f"{ok / tot:.1%}" if tot else "n/a"
            print(f"  conf={c}: top1 {rate} ({ok}/{tot})")
        if non_high:
            print(
                f"non-high shortlist hit={gold_in_shortlist_non_high / non_high:.1%} "
                f"({gold_in_shortlist_non_high}/{non_high})"
            )
        print("by kind (top1 / top2 / n):")
        for kind, (t1, t2, tot) in sorted(by_kind.items()):
            print(f"  {kind}: top1={t1/tot:.1%} top2={t2/tot:.1%} n={tot}")
        if hard_override_n:
            print(
                f"hard-override(high, classic only)={hard_override_ok / hard_override_n:.1%} "
                f"({hard_override_ok}/{hard_override_n})"
            )
        else:
            print("hard-override(high, classic only)=0 triggers")


if __name__ == "__main__":
    main()
