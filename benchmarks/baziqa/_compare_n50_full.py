#!/usr/bin/env python3
"""Full comparison for contest8 LOO experiments."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


def load(p: str):
    path = Path(p)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def acc(rows):
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get("correct")) / len(rows)


def domain_of(q: str) -> str:
    keys = {
        "year": ("哪年", "何年", "那一年", "何时", "几时", "年份", "那年"),
        "career": ("职业", "工作", "事业", "从事", "行业"),
        "wealth": ("财运", "财富", "有钱", "贫富", "收入"),
        "health": ("病", "健康", "身体", "受伤", "疾病", "困扰"),
        "edu": ("学历", "读书", "学业"),
        "marriage": ("结婚", "离婚", "婚姻", "感情", "恋爱"),
        "kinship": ("父", "母", "子女", "孩子", "兄弟"),
    }
    for d, kws in keys.items():
        if any(k in q for k in kws):
            return d
    return "other"


sets = {
    "baseline_n30": load("benchmarks/baziqa/results/loo_contest8_deepseek_chat_n30.jsonl"),
    "shortlist_n50": load("benchmarks/baziqa/results/loo_contest8_deepseek_shortlist_n50.jsonl"),
    "rag_v2b_n30": load("benchmarks/baziqa/results/loo_contest8_rag_v2b_n30.jsonl"),
    "rag_v2b_n50": load("benchmarks/baziqa/results/loo_contest8_rag_v2b_n50.jsonl"),
}

print("=== overall ===")
for name, rows in sets.items():
    if rows:
        print(f"{name:16} {sum(r.get('correct') for r in rows):2}/{len(rows)} = {acc(rows):.1%}")

n50 = sets["rag_v2b_n50"]
sl50 = sets["shortlist_n50"]
print("\n=== n50 first30 / last20 ===")
if n50:
    print(f"rag first30 {sum(r.get('correct') for r in n50[:30])}/30 = {acc(n50[:30]):.1%}")
    print(f"rag last20  {sum(r.get('correct') for r in n50[30:])}/{len(n50[30:])} = {acc(n50[30:]):.1%}")
if sl50:
    print(f"sl  first30 {sum(r.get('correct') for r in sl50[:30])}/30 = {acc(sl50[:30]):.1%}")
    print(f"sl  last20  {sum(r.get('correct') for r in sl50[30:])}/{len(sl50[30:])} = {acc(sl50[30:]):.1%}")

print("\n=== paired n50 rag vs shortlist ===")
if n50 and sl50:
    om = {r["question_id"]: r for r in sl50}
    nm = {r["question_id"]: r for r in n50}
    both = set(om) & set(nm)
    win_n = sum(1 for q in both if nm[q].get("correct") and not om[q].get("correct"))
    win_o = sum(1 for q in both if om[q].get("correct") and not nm[q].get("correct"))
    print(f"rag wins {win_n}, shortlist wins {win_o}, ties {len(both)-win_n-win_o}, n={len(both)}")
    print("rag wins:")
    for q in sorted(both):
        if nm[q].get("correct") and not om[q].get("correct"):
            print(f"  + {q} {nm[q].get('question','')[:40]}")
    print("shortlist wins (rag lost):")
    for q in sorted(both):
        if om[q].get("correct") and not nm[q].get("correct"):
            print(f"  - {q} {om[q].get('question','')[:40]}")

print("\n=== by domain (n50 rag) ===")
if n50:
    by = {}
    for r in n50:
        d = domain_of(r.get("question", ""))
        by.setdefault(d, [0, 0])
        by[d][1] += 1
        if r.get("correct"):
            by[d][0] += 1
    for d, (ok, tot) in sorted(by.items(), key=lambda x: -x[1][1]):
        print(f"  {d:10} {ok}/{tot} = {ok/tot:.1%}")

print("\n=== shortlist fire (n50 rag) ===")
if n50:
    sl = [r for r in n50 if r.get("rule_shortlist")]
    print(f"fired {len(sl)} acc={acc(sl):.1%}")
    for r in sl:
        labs = [c["option"] for c in r["rule_shortlist"]]
        gold = (r.get("answer") or "")[:1]
        print(
            f"  {r['question_id']} gold={gold} pred={r.get('predicted')} "
            f"sl={labs} in={gold in labs} ok={r.get('correct')}"
        )

# errors without shortlist
print("\n=== wrong non-year sample (first 8) ===")
if n50:
    n = 0
    for r in n50:
        if r.get("correct") or r.get("rule_shortlist"):
            continue
        print(f"  {r['question_id']} gold={r.get('answer')} pred={r.get('predicted')} | {r.get('question','')[:50]}")
        n += 1
        if n >= 8:
            break
