#!/usr/bin/env python3
"""Offline: domain shortlist top-1/top-2 ceiling on contest8 non-year MCQs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import load_baziqa, person_to_bazi  # noqa: E402
from tools.bazi_ai.rule_reasoner import rank_domain_candidates  # noqa: E402


def main() -> None:
    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    top1 = top2 = n = 0
    by_dom: dict = {}
    for person in contest:
        bazi = person_to_bazi(person)
        if not bazi:
            continue
        g = person.get("profile", {}).get("gender", "male")
        gender = "female" if g in ("女", "female", "f", "F") else "male"
        for q in person.get("questions", []):
            opts = q.get("options", [])
            ans = (q.get("answer") or "").strip().upper()[:1]
            if not ans:
                continue
            # skip pure year options
            if sum(1 for o in opts if re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", o)) >= 2:
                continue
            ranked = rank_domain_candidates(
                bazi, q.get("question", ""), opts, gender=gender, top_k=2
            )
            if not ranked:
                continue
            n += 1
            labs = [c.option for c in ranked]
            # crude domain tag from first reason
            dom = (ranked[0].reasons[0] if ranked[0].reasons else "?")[:6]
            by_dom.setdefault(dom, [0, 0, 0])
            by_dom[dom][2] += 1
            if ans == labs[0]:
                top1 += 1
                by_dom[dom][0] += 1
            if ans in labs[:2]:
                top2 += 1
                by_dom[dom][1] += 1
            print(
                f"{'HIT' if ans in labs[:2] else 'MISS'} {q.get('question_id')} "
                f"gold={ans} top={labs} conf={ranked[0].confidence} "
                f"q={q.get('question','')[:40]}"
            )
    print(f"\ndomain shortlist n={n}")
    if n:
        print(f"top1={top1/n:.1%} ({top1}/{n})")
        print(f"top2={top2/n:.1%} ({top2}/{n})")


if __name__ == "__main__":
    main()
