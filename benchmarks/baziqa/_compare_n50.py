#!/usr/bin/env python3
import json
import re
from pathlib import Path


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


old = load("benchmarks/baziqa/results/loo_contest8_deepseek_chat_n30.jsonl")
new = load("benchmarks/baziqa/results/loo_contest8_deepseek_shortlist_n50.jsonl")

print(f"old n30 {sum(r.get('correct') for r in old)}/{len(old)} = {sum(r.get('correct') for r in old)/len(old):.1%}")
print(f"new n50 {sum(r.get('correct') for r in new)}/{len(new)} = {sum(r.get('correct') for r in new)/len(new):.1%}")
new30 = new[:30]
print(f"new first30 {sum(r.get('correct') for r in new30)}/{len(new30)} = {sum(r.get('correct') for r in new30)/len(new30):.1%}")

om = {r["question_id"]: r for r in old}
nm = {r["question_id"]: r for r in new}
both = set(om) & set(nm)
print(f"paired qids {len(both)}")
old_ok = sum(1 for q in both if om[q].get("correct"))
new_ok = sum(1 for q in both if nm[q].get("correct"))
print(f"paired old {old_ok} new {new_ok}")
win_new = sum(1 for q in both if nm[q].get("correct") and not om[q].get("correct"))
win_old = sum(1 for q in both if om[q].get("correct") and not nm[q].get("correct"))
print(f"new wins {win_new} old wins {win_old} ties {len(both)-win_new-win_old}")

sl = [r for r in new if r.get("rule_shortlist")]
print(f"\nshortlist fired {len(sl)} acc {sum(r.get('correct') for r in sl)/len(sl) if sl else 0:.1%}")
for r in sl:
    labs = [c["option"] for c in r["rule_shortlist"]]
    gold = (r.get("answer") or "")[:1]
    print(
        f"  {r['question_id']} gold={gold} pred={r.get('predicted')} "
        f"sl={labs} in={gold in labs} ok={r.get('correct')}"
    )

# year-asking questions overall
year_kw = ("哪年", "那一年", "何年", "哪一年", "何时", "几时", "什么时候", "年份", "那年")
year_qs = [r for r in new if any(k in r.get("question", "") for k in year_kw)]
print(f"\nyear-asking in n50: {sum(r.get('correct') for r in year_qs)}/{len(year_qs)}")
