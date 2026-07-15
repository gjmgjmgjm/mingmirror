#!/usr/bin/env python3
"""List contest8 year questions and which ones the rule reasoner covers."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import load_baziqa, person_to_bazi  # noqa: E402
from tools.bazi_ai.rule_reasoner import rank_year_candidates  # noqa: E402


def main() -> None:
    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    total_year = 0
    covered = 0
    for person in contest:
        bazi = person_to_bazi(person) or ""
        birth = person.get("profile", {}).get("birth", {})
        g = person.get("profile", {}).get("gender", "male")
        gender = "female" if g in ("女", "female", "f", "F") else "male"
        bd = f"{birth['year']:04d}-{birth['month']:02d}-{birth['day']:02d}" if birth.get("year") else ""
        bt = f"{birth.get('hour', 0):02d}:{birth.get('minute', 0):02d}"
        for q in person.get("questions", []):
            opts = q.get("options", [])
            if not any(re.search(r"19\d{2}|20\d{2}", o) for o in opts):
                continue
            total_year += 1
            qtext = q.get("question", "")
            ans = (q.get("answer") or "").strip().upper()[:1]
            ranked = rank_year_candidates(
                bazi, qtext, opts, gender=gender, birth_date=bd, birth_time=bt, top_k=2
            )
            status = "COVERED" if ranked else "MISS"
            if ranked:
                covered += 1
                labs = [c.option for c in ranked]
                hit = "HIT" if ans in labs else "MISS-top2"
                print(f"{status} {hit} {q.get('question_id')} gold={ans} top={labs} | {qtext[:60]}")
            else:
                print(f"{status} ---- {q.get('question_id')} gold={ans} | {qtext[:80]}")
    print(f"\nyear questions={total_year}, covered={covered}, miss={total_year - covered}")


if __name__ == "__main__":
    main()
