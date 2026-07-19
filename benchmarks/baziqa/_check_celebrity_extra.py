#!/usr/bin/env python3
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.bazi_validator import normalize_bazi
from tools.bazi_ai.calendar import pillars_for_datetime

extra = json.loads(
    Path("benchmarks/baziqa/data/celebrity_extra.json").read_text(encoding="utf-8")
)
print("total", len(extra))

bad = []
for r in extra:
    y, m, d = map(int, r["birth_date"].split("-"))
    hh, mm = map(int, r["birth_time"].split(":"))
    p = pillars_for_datetime(datetime(y, m, d, hh, mm))
    raw = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    got = normalize_bazi(raw) or raw
    if got != r["bazi"]:
        bad.append((r["name"], r["bazi"], got))
print("bazi self-consistency fails", len(bad))
if bad[:5]:
    print(bad[:5])

random.seed(42)
print("--- 5 samples ---")
for r in random.sample(extra, 5):
    print(
        r["name"],
        r["gender"],
        r["birth_date"],
        r["birth_time"],
        r["bazi"],
        r["source"][:60],
    )

c50 = json.loads(
    Path("benchmarks/baziqa/data/celebrity50_zh.json").read_text(encoding="utf-8")
)
c50_names = {p["name"].lower() for p in c50}
overlap = [r["name"] for r in extra if r["name"].lower() in c50_names]
print("name overlap celebrity50", overlap)

yy_path = Path("benchmarks/baziqa/data/yangyan_bazi_only.jsonl")
yy = [json.loads(l) for l in yy_path.read_text(encoding="utf-8").splitlines() if l.strip()]
print("yangyan lines", len(yy))
print("yangyan sample", yy[0])
print("license", Counter(r["license"] for r in extra))
print(
    "src fam",
    Counter("qizheng" if "qizheng" in r["source"] else "wikipedia" for r in extra),
)

# json.load ok
assert isinstance(extra, list) and len(extra) >= 30
assert len(bad) == 0
print("ACCEPTANCE: list ok, n>=30, self-consistency 100%")
