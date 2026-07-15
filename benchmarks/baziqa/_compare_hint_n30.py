#!/usr/bin/env python3
import json
from pathlib import Path


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


old = load("benchmarks/baziqa/results/loo_contest8_deepseek_chat_n30.jsonl")
prev = load("benchmarks/baziqa/results/loo_contest8_deepseek_shortlist_n50.jsonl")[:30]
new = load("benchmarks/baziqa/results/loo_contest8_deepseek_hint_n30.jsonl")

def acc(rows):
    return sum(1 for r in rows if r.get("correct")) / len(rows) if rows else 0

print(f"baseline n30:     {sum(r.get('correct') for r in old)}/{len(old)} = {acc(old):.1%}")
print(f"shortlist n30:    {sum(r.get('correct') for r in prev)}/{len(prev)} = {acc(prev):.1%}")
print(f"hint+sl n30:      {sum(r.get('correct') for r in new)}/{len(new)} = {acc(new):.1%}")

om = {r["question_id"]: r for r in old}
nm = {r["question_id"]: r for r in new}
both = set(om) & set(nm)
win_n = sum(1 for q in both if nm[q].get("correct") and not om[q].get("correct"))
win_o = sum(1 for q in both if om[q].get("correct") and not nm[q].get("correct"))
print(f"vs baseline: new wins {win_n}, old wins {win_o}, ties {len(both)-win_n-win_o}")

pm = {r["question_id"]: r for r in prev}
both2 = set(pm) & set(nm)
win_n2 = sum(1 for q in both2 if nm[q].get("correct") and not pm[q].get("correct"))
win_p = sum(1 for q in both2 if pm[q].get("correct") and not nm[q].get("correct"))
print(f"vs shortlist: new wins {win_n2}, prev wins {win_p}, ties {len(both2)-win_n2-win_p}")

# year shortlist fire rate
sl = [r for r in new if r.get("rule_shortlist")]
print(f"year shortlist fired: {len(sl)} acc={acc(sl):.1%}")
# domain hints: no rule_shortlist but raw might mention 结构
hintish = [r for r in new if not r.get("rule_shortlist") and any(
    k in r.get("question","") for k in ("职业","学历","健康","财运","工作","读书","疾病")
)]
print(f"domain-ish qs without year sl: {sum(r.get('correct') for r in hintish)}/{len(hintish)}")
