#!/usr/bin/env python3
"""Deterministic 六亲-strength ruler — isolates the engine layer from the LLM.

The other window's validate_real.py measures END-TO-END 六亲 (engine facts → LLM
liuqin_analysis → comparator). That mixes two questions: (a) is the deterministic
strength right? (b) does the LLM adopt it? This ruler answers (a) ONLY, by
comparing the engine's DETERMINISTIC liuqin strength (liuqin_profile.strength,
which now carries the root-destruction fix) directly against the 杨炎 master gold
— no LLM in the loop. Zero API cost.

If this number is high but end-to-end is low → the gap is LLM adoption (fix the
prompt). If this number itself is low → the deterministic heuristic is wrong
(fix bazi_structural).

Usage::
    python benchmarks/baziqa/validate_liuqin_det.py --limit 30
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai import bazi_structural  # noqa: E402

CASES = Path("bazi_knowledge/杨炎八字绝技_cases.jsonl")

# Subject detection (section markers, earliest wins) — aligned with validate_real.
_MARKERS = {
    "father": ["父亲断象", "父亲断", "父星断", "父灾", "· 父亲", "父星：", "父星"],
    "spouse": ["丈夫断象", "夫星断象", "夫星断", "夫灾", "妻子断象", "妻星断",
               "配偶断象", "· 丈夫", "· 配偶", "断夫", "断妻", "夫星", "妻星", "配偶星"],
    "mother": ["母亲断象", "母亲断", "母星断", "· 母亲", "母星：", "母星"],
    "child": ["子女断象", "子女断", "克子", "克子女", "· 子女", "子女星", "子女"],
    "sibling": ["兄弟断象", "姐妹断象", "兄弟断", "兄弟情况", "· 兄弟", "· 姐妹"],
}
_LQ_KEY = {"father": "father", "spouse": "spouse", "mother": "mother",
           "child": "son", "sibling": "brother"}  # liuqin_profile keys (single rel per case)
_LQ_ZH = {"father": "父亲", "spouse": "配偶", "mother": "母亲", "child": "子女", "sibling": "兄弟"}

# Master verdict-first strength (真星/假星/旺/衰 explicit before token balance).
_STRONG = re.compile(r"真而(旺|强)|真星.{0,8}(旺|强|有力|稳固)|是为.{0,4}真星")
_WEAK = re.compile(r"假(星|而|而弱)|虚浮(无根)?|无根|受.{0,3}克(制)?|耗泄|根气不固|缘(薄|浅)|截脚")
_STRONG_TOKS = ["真星", "强根", "通根", "得令", "帝旺", "长生", "有力", "稳固", "根深", "旺"]
_WEAK_TOKS = ["假星", "无根", "虚浮", "受克", "绝地", "弱", "缘薄", "不稳", "截脚", "孤露", "争合", "耗泄"]


def _subject(master: str) -> str:
    best, bi = "", len(master) + 1
    for subj, ms in _MARKERS.items():
        for m in ms:
            idx = master.find(m)
            if idx != -1 and idx < bi:
                best, bi = subj, idx
    return best


def _master_strength(text: str) -> str:
    if not text:
        return "?"
    if _STRONG.search(text) and not _WEAK.search(text):
        return "强"
    if _WEAK.search(text) and not _STRONG.search(text):
        return "弱"
    s = sum(1 for t in _STRONG_TOKS if t in text)
    w = sum(1 for t in _WEAK_TOKS if t in text)
    return "强" if s > w else ("弱" if w > s else "?")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()
    recs = [json.loads(l) for l in CASES.open(encoding="utf-8") if l.strip()][: args.limit]

    n = hit = 0
    by_subj = {}
    rows = []
    for r in recs:
        bazi = r.get("bazi", "")
        gender = "female" if r.get("gender") == "女" else "male"
        master = r.get("analysis_corrected", "") or r.get("analysis_raw", "") or ""
        if not bazi or not master:
            continue
        subj = _subject(master)
        if not subj:
            continue
        prof = bazi_structural.liuqin_profile(bazi, gender=gender) or {}
        rel = prof.get(_LQ_KEY.get(subj, ""), {})
        det = rel.get("strength", "?")
        mstr = _master_strength(master)
        if det == "?" or mstr == "?":
            continue  # skip hedgy/undetectable
        n += 1
        ok = det == mstr
        hit += int(ok)
        by_subj.setdefault(_LQ_ZH[subj], [0, 0]); by_subj[_LQ_ZH[subj]][1] += 1
        if ok:
            by_subj[_LQ_ZH[subj]][0] += 1
        rows.append((r.get("gender", ""), subj, bazi, mstr, det, ok, rel.get("support_text", "")))

    print(f"确定性六亲强弱 vs 杨炎大师gold (n={n}, 绕过LLM, 零API)\n")
    for g, subj, bazi, mstr, det, ok, sup in rows:
        print(f"  {'✓' if ok else '✗'} [{_LQ_ZH[subj]}] {g} {bazi}  master={mstr} engine={det}")
        if not ok:
            print(f"      engine依据: {sup}")
    print(f"\n确定性六亲强弱准确率: {hit}/{n} = {hit/n:.0%}" if n else "no comparable cases")
    if by_subj:
        print("按六亲:")
        for s, (h, t) in sorted(by_subj.items()):
            print(f"  {s}: {h}/{t} = {h/t:.0%}")
    print("\n解读：高→引擎确定性层对，端到端差距=LLM采纳；低→确定性启发式本身要改。")


if __name__ == "__main__":
    main()
