#!/usr/bin/env python3
"""Deterministic 健康 ruler: health_profile 弱脏腑 vs 杨炎 master 健康文本.

结构层 thesis 延伸:排盘/格局/用神/六亲都有 det 层,唯独健康纯靠 LLM.
本尺子测 health_profile(五行偏枯→脏腑弱项, 零 LLM)是否与大师健康断一致,
决定是否值得注入 engine. 零 API.

⚠️ gold 粗:杨炎案例是六亲断象,命主健康只是文本附带,关键词 overlap 是粗粒度
近似,数字仅供参考(不像排盘/用神有干净 gold)。

Usage::
    python benchmarks/baziqa/validate_health_det.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.bazi_structural import health_profile  # noqa: E402

CASES = Path("bazi_knowledge/杨炎八字绝技_cases.jsonl")
# 脏腑/健康关键词 (与 validate_real._HEALTH 对齐)
_HEALTH = ["妇科", "子宫", "肝", "胆", "脾", "胃", "肺", "肾", "心", "血压",
           "呼吸", "神经", "骨", "血", "皮肤", "目", "眼", "头", "肠", "泌尿",
           "血管", "脾胃", "腰椎", "颈椎"]


def main() -> None:
    recs = [json.loads(l) for l in CASES.open(encoding="utf-8") if l.strip()]
    n = hit = 0
    rows = []
    for r in recs:
        bazi = r.get("bazi", "")
        master = r.get("analysis_corrected", "") or r.get("analysis_raw", "") or ""
        if not bazi or not master:
            continue
        prof = health_profile(bazi)
        if not prof:
            continue
        eng_organs = set(prof["weak_organs"])
        master_organs = {h for h in _HEALTH if h in master}
        if not eng_organs or not master_organs:
            continue
        n += 1
        ov = eng_organs & master_organs
        ok = bool(ov)
        hit += int(ok)
        rows.append((bazi, prof["weakest_element"], prof["strongest_element"],
                     sorted(eng_organs), sorted(master_organs), sorted(ov), ok))

    print(f"健康 det 脏腑 vs 杨炎文本 (n={n}, 零API, gold粗)\n")
    for bazi, weak, strong, eng, mast, ov, ok in rows:
        print(f"  {'✓' if ok else '✗'} {bazi}  最弱={weak} 最旺={strong} "
              f"engine弱脏腑={eng} master提到={mast}")
    if n:
        print(f"\n健康 det 脏腑 overlap: {hit}/{n} = {hit/n:.0%}")
        print("解读：≥70%→确定性健康推断有效,值得注入 engine;<50%→五行脏腑映射太粗,放弃注入。")


if __name__ == "__main__":
    main()
