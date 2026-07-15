#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def acc(rows):
    return sum(1 for r in rows if r.get("correct")) / len(rows) if rows else 0


paths = {
    "baseline": "benchmarks/baziqa/results/loo_contest8_deepseek_chat_n30.jsonl",
    "shortlist": "benchmarks/baziqa/results/loo_contest8_deepseek_shortlist_n50.jsonl",
    "rag_v2": "benchmarks/baziqa/results/loo_contest8_rag_v2_n30.jsonl",
}
rows = {}
for k, p in paths.items():
    path = Path(p)
    if not path.exists():
        print(f"missing {p}")
        continue
    r = load(path)
    if k == "shortlist":
        r = r[:30]
    rows[k] = r
    print(f"{k:12} {sum(x.get('correct') for x in r)}/{len(r)} = {acc(r):.1%}")

if "baseline" in rows and "rag_v2" in rows:
    om = {r["question_id"]: r for r in rows["baseline"]}
    nm = {r["question_id"]: r for r in rows["rag_v2"]}
    both = set(om) & set(nm)
    win_n = sum(1 for q in both if nm[q].get("correct") and not om[q].get("correct"))
    win_o = sum(1 for q in both if om[q].get("correct") and not nm[q].get("correct"))
    print(f"rag_v2 vs baseline: +{win_n} / -{win_o} / ties {len(both)-win_n-win_o}")

if "shortlist" in rows and "rag_v2" in rows:
    om = {r["question_id"]: r for r in rows["shortlist"]}
    nm = {r["question_id"]: r for r in rows["rag_v2"]}
    both = set(om) & set(nm)
    win_n = sum(1 for q in both if nm[q].get("correct") and not om[q].get("correct"))
    win_o = sum(1 for q in both if om[q].get("correct") and not nm[q].get("correct"))
    print(f"rag_v2 vs shortlist: +{win_n} / -{win_o} / ties {len(both)-win_n-win_o}")

# domain-ish accuracy
rag = rows.get("rag_v2", [])
base = rows.get("baseline", [])


def domain_slice(rs, keys):
    return [r for r in rs if any(k in r.get("question", "") for k in keys)]


for name, keys in [
    ("career", ("职业", "工作", "事业")),
    ("year", ("哪年", "何年", "那一年", "何时")),
    ("edu", ("学历", "读书")),
]:
    a, b = domain_slice(base, keys), domain_slice(rag, keys)
    if a or b:
        print(
            f"  {name}: baseline {sum(x.get('correct') for x in a)}/{len(a)} "
            f"rag {sum(x.get('correct') for x in b)}/{len(b)}"
        )
