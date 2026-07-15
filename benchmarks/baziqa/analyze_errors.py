#!/usr/bin/env python3
"""Phase 0 error analysis for BaziQA results.

Loads one or more result JSONL files, classifies each question by domain and by
question shape (year-based vs categorical), and reports:

- overall / per-domain accuracy
- error-type split (infra error, extraction failure, genuine wrong answer)
- predicted-letter distribution (bias check)
- year-question gold-vs-predicted distance
- symbolic rule_reasoner agreement (when birth info is available in the dataset)

The point is to surface *where* we are wrong and *why*, so Phase 1 (rule engine)
and Phase 2 (case library) can be prioritised rather than guessing.

Usage::

    python benchmarks/baziqa/analyze_errors.py \\
        benchmarks/baziqa/results/loo_contest8_agnes_flash.jsonl \\
        benchmarks/baziqa/results/cross_celebrity50_agnes_flash.jsonl \\
        [--data benchmarks/baziqa/data]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow imports from repo root when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import (  # noqa: E402
    _detect_domain,
    _DOMAIN_LABELS,
    _extract_years,
    load_baziqa,
    person_to_bazi,
)
from tools.bazi_ai.rule_reasoner import apply_rule_reasoner  # noqa: E402


def _load_rows(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _birth_date_time(person: Dict) -> Tuple[str, str]:
    birth = person.get("profile", {}).get("birth", {})
    y, mo, d = birth.get("year"), birth.get("month"), birth.get("day")
    h, mi = birth.get("hour", 0), birth.get("minute", 0)
    if not all(isinstance(v, int) for v in (y, mo, d)):
        return "", ""
    return f"{y:04d}-{mo:02d}-{d:02d}", f"{h:02d}:{mi:02d}"


def _build_qid_meta(contest, celebrity) -> Dict[str, Dict]:
    """Map question_id -> {gender, birth_date, birth_time, options, bazi}."""
    meta: Dict[str, Dict] = {}
    for person in list(contest) + list(celebrity):
        bazi = person_to_bazi(person)
        birth_date, birth_time = _birth_date_time(person)
        gender = person.get("profile", {}).get("gender", "male")
        for q in person.get("questions", []):
            qid = q.get("question_id")
            if qid:
                meta[qid] = {
                    "gender": gender,
                    "birth_date": birth_date,
                    "birth_time": birth_time,
                    "options": q.get("options", []),
                    "bazi": bazi,
                    "question": q.get("question", ""),
                }
    return meta


def _classify_error(row: Dict) -> str:
    """Bucket each incorrect row by the most likely failure mode."""
    if row.get("error") or not row.get("predicted"):
        err = str(row.get("error", ""))
        if "429" in err or "Rate" in err or "Too Many" in err:
            return "infra_429"
        if "timeout" in err.lower() or "Timeout" in err:
            return "infra_timeout"
        if not row.get("raw"):
            return "infra_other"
        return "extract_fail"  # model replied but no letter parsed
    return "genuine_wrong"


def analyze(path: Path, meta: Dict[str, Dict]) -> Dict:
    rows = _load_rows(path)
    n = len(rows)
    if not n:
        return {"path": str(path), "n": 0}

    attempted = [r for r in rows if r.get("predicted")]
    correct = sum(1 for r in rows if r.get("correct"))

    by_domain_correct = defaultdict(int)
    by_domain_total = defaultdict(int)
    year_correct = {"yes": [0, 0], "no": [0, 0]}  # [correct, total]
    err_types = Counter()
    pred_letters = Counter()
    year_distances = []  # abs(gold_year - pred_year)

    rule_fired = 0
    rule_fired_correct = 0
    rule_agrees_llm = 0
    rule_disagrees_and_rule_right = 0
    rule_disagrees_and_llm_right = 0

    for r in rows:
        qid = r.get("question_id", "")
        qtext = r.get("question", "")
        domain = _detect_domain(qtext)
        by_domain_total[domain] += 1
        if r.get("correct"):
            by_domain_correct[domain] += 1

        is_year = bool(_extract_years(qtext)) or bool(
            _extract_years(" ".join(meta.get(qid, {}).get("options", [])))
        )
        key = "yes" if is_year else "no"
        year_correct[key][1] += 1
        if r.get("correct"):
            year_correct[key][0] += 1

        if not r.get("correct"):
            err_types[_classify_error(r)] += 1

        if r.get("predicted"):
            pred_letters[r["predicted"]] += 1

        # year distance
        if is_year and r.get("predicted") and meta.get(qid):
            opts = meta[qid]["options"]
            gold = r.get("answer")
            pred = r.get("predicted")
            idx_gold = ord(gold) - ord("A") if gold and len(gold) == 1 else -1
            idx_pred = ord(pred) - ord("A") if pred and len(pred) == 1 else -1
            if 0 <= idx_gold < len(opts) and 0 <= idx_pred < len(opts):
                gy = _extract_years(opts[idx_gold])
                py = _extract_years(opts[idx_pred])
                if gy and py:
                    year_distances.append(abs(gy[0] - py[0]))

        # rule reasoner agreement (needs birth info) — measured at production
        # threshold (high) so the numbers reflect actual override behaviour.
        m = meta.get(qid)
        if m and m.get("birth_date") and m.get("options") and is_year:
            try:
                rule_ans = apply_rule_reasoner(
                    m["bazi"],
                    qtext,
                    m["options"],
                    gender=m["gender"],
                    birth_date=m["birth_date"],
                    birth_time=m["birth_time"],
                    min_confidence="high",
                )
            except Exception:
                rule_ans = None
            if rule_ans:
                rule_fired += 1
                if rule_ans == r.get("answer"):
                    rule_fired_correct += 1
                if rule_ans == r.get("predicted"):
                    rule_agrees_llm += 1
                else:
                    if rule_ans == r.get("answer"):
                        rule_disagrees_and_rule_right += 1
                    elif r.get("predicted") == r.get("answer"):
                        rule_disagrees_and_llm_right += 1

    domain_acc = {
        _DOMAIN_LABELS.get(d, d): {
            "acc": round(100.0 * by_domain_correct[d] / by_domain_total[d], 1)
            if by_domain_total[d]
            else 0.0,
            "n": by_domain_total[d],
            "correct": by_domain_correct[d],
        }
        for d in sorted(by_domain_total, key=lambda x: -by_domain_total[x])
    }

    return {
        "path": path.name,
        "n": n,
        "attempted": len(attempted),
        "correct": correct,
        "accuracy": round(100.0 * correct / n, 1),
        "attempted_accuracy": round(100.0 * correct / len(attempted), 1)
        if attempted
        else 0.0,
        "domain_accuracy": domain_acc,
        "year_question_accuracy": {
            "year": {
                "acc": round(100.0 * year_correct["yes"][0] / year_correct["yes"][1], 1)
                if year_correct["yes"][1]
                else 0.0,
                "n": year_correct["yes"][1],
            },
            "non_year": {
                "acc": round(100.0 * year_correct["no"][0] / year_correct["no"][1], 1)
                if year_correct["no"][1]
                else 0.0,
                "n": year_correct["no"][1],
            },
        },
        "error_types": dict(err_types),
        "pred_letter_dist": dict(pred_letters),
        "year_distance": {
            "mean": round(sum(year_distances) / len(year_distances), 1)
            if year_distances
            else None,
            "within_1yr": sum(1 for d in year_distances if d <= 1),
            "within_3yr": sum(1 for d in year_distances if d <= 3),
            "n": len(year_distances),
        },
        "rule_reasoner": {
            "fired": rule_fired,
            "correct_when_fired": rule_fired_correct,
            "acc_when_fired": round(100.0 * rule_fired_correct / rule_fired, 1)
            if rule_fired
            else 0.0,
            "agrees_with_llm": rule_agrees_llm,
            "disagree_rule_right": rule_disagrees_and_rule_right,
            "disagree_llm_right": rule_disagrees_and_llm_right,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", nargs="+", type=Path, help="Result JSONL files")
    ap.add_argument("--data", default="benchmarks/baziqa/data", type=Path)
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of text")
    args = ap.parse_args()

    meta: Dict[str, Dict] = {}
    if args.data.exists():
        contest, celebrity = load_baziqa(args.data)
        meta = _build_qid_meta(contest, celebrity)
        print(f"Loaded dataset meta for {len(meta)} questions", file=sys.stderr)

    summaries = []
    for path in args.results:
        if not path.exists():
            print(f"SKIP missing: {path}", file=sys.stderr)
            continue
        summaries.append(analyze(path, meta))

    if args.json:
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
        return

    for s in summaries:
        print(f"\n{'='*72}\n{s['path']}  (n={s['n']}, attempted={s['attempted']})")
        print(f"  accuracy = {s['accuracy']}%   attempted_acc = {s['attempted_accuracy']}%")
        print(f"  --- per-domain ---")
        for d, v in s["domain_accuracy"].items():
            print(f"    {d:8s} {v['acc']:5.1f}%  (n={v['n']}, correct={v['correct']})")
        y = s["year_question_accuracy"]
        print(f"  --- question shape ---")
        print(
            f"    year-based   {y['year']['acc']:5.1f}%  (n={y['year']['n']})"
        )
        print(
            f"    non-year     {y['non_year']['acc']:5.1f}%  (n={y['non_year']['n']})"
        )
        print(f"  --- error types (wrong only) ---")
        for k, v in sorted(s["error_types"].items(), key=lambda x: -x[1]):
            print(f"    {k:16s} {v}")
        wd = s["year_distance"]
        if wd["mean"] is not None:
            print(
                f"  --- year distance (n={wd['n']}) mean={wd['mean']}yr  "
                f"<=1yr={wd['within_1yr']}  <=3yr={wd['within_3yr']}"
            )
        rr = s["rule_reasoner"]
        if rr["fired"]:
            print(f"  --- rule_reasoner ---")
            print(
                f"    fired={rr['fired']}  acc_when_fired={rr['acc_when_fired']}%  "
                f"agrees_llm={rr['agrees_with_llm']}"
            )
            print(
                f"    disagree: rule_right={rr['disagree_rule_right']}  "
                f"llm_right={rr['disagree_llm_right']}"
            )


if __name__ == "__main__":
    main()
