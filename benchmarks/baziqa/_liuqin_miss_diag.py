#!/usr/bin/env python3
"""One-off diagnostic: dump root quality for 六亲-strength misses vs hits.

Hypothesis to confirm: the over-promotion misses (engine=强, master=弱) have
only SHALLOW 藏干 roots (not 本气通根), which the heuristic counts equal to a
deep root. If true, the principled fix is "require a 本气 root (or multiple
roots) for 强" — not overfitting to gold noise.

Prints, for every comparable case: relation, verdict hit/miss, has_stem,
root positions with their TYPE (本气 vs 藏干), destroyed/intact, 得令.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.bazi_ai import bazi_structural as bs  # noqa: E402

CASES = Path("bazi_knowledge/杨炎八字绝技_cases.jsonl")
_LQ_POSITIONS = ("年支", "月支", "日支", "时支")

# mirror validate_liuqin_det subject + master parsing (kept inline to stay standalone)
_MARKERS = {
    "father": ["父亲断象", "父亲断", "父星断", "父灾", "· 父亲", "父星：", "父星"],
    "spouse": ["丈夫断象", "夫星断象", "夫星断", "夫灾", "妻子断象", "妻星断",
               "配偶断象", "· 丈夫", "· 配偶", "断夫", "断妻", "夫星", "妻星", "配偶星"],
    "mother": ["母亲断象", "母亲断", "母星断", "· 母亲", "母星：", "母星"],
    "child": ["子女断象", "子女断", "克子", "克子女", "· 子女", "子女星", "子女"],
    "sibling": ["兄弟断象", "姐妹断象", "兄弟断", "兄弟情况", "· 兄弟", "· 姐妹"],
}
_LQ_KEY = {"father": "father", "spouse": "spouse", "mother": "mother",
           "child": "son", "sibling": "brother"}
_LQ_ZH = {"father": "父亲", "spouse": "配偶", "mother": "母亲", "child": "子女", "sibling": "兄弟"}


def _subject(master):
    best, bi = "", len(master) + 1
    for subj, ms in _MARKERS.items():
        for m in ms:
            idx = master.find(m)
            if idx != -1 and idx < bi:
                best, bi = subj, idx
    return best


def _master_strength(text):
    import re
    STRONG = re.compile(r"真而(旺|强)|真星.{0,8}(旺|强|有力|稳固)|是为.{0,4}真星")
    WEAK = re.compile(r"假(星|而|而弱)|虚浮(无根)?|无根|受.{0,3}克(制)?|耗泄|根气不固|缘(薄|浅)|截脚")
    ST = ["真星", "强根", "通根", "得令", "帝旺", "长生", "有力", "稳固", "根深", "旺"]
    WK = ["假星", "无根", "虚浮", "受克", "绝地", "弱", "缘薄", "不稳", "截脚", "孤露", "争合", "耗泄"]
    if STRONG.search(text) and not WEAK.search(text):
        return "强"
    if WEAK.search(text) and not STRONG.search(text):
        return "弱"
    s = sum(1 for t in ST if t in text)
    w = sum(1 for t in WK if t in text)
    return "强" if s > w else ("弱" if w > s else "?")


def main():
    recs = [json.loads(l) for l in CASES.open(encoding="utf-8") if l.strip()]
    for r in recs:
        bazi = r.get("bazi", "")
        gender = "female" if r.get("gender") == "女" else "male"
        master = r.get("analysis_corrected", "") or r.get("analysis_raw", "") or ""
        if not bazi or not master:
            continue
        subj = _subject(master)
        if not subj:
            continue
        prof = bs.liuqin_profile(bazi, gender=gender) or {}
        rel = prof.get(_LQ_KEY.get(subj, ""), {})
        if not rel.get("exists"):
            continue
        mstr = _master_strength(master)
        det = rel.get("strength", "?")
        if det == "?" or mstr == "?":
            continue
        ok = det == mstr
        locs = rel.get("locations", [])
        roots = [l for l in locs if l["type"] in ("地支本气", "地支藏干") and l["position"] in _LQ_POSITIONS]
        benqi = [l for l in roots if l["type"] == "地支本气"]
        canggan = [l for l in roots if l["type"] == "地支藏干"]
        stems = [l for l in locs if l["type"] == "天干"]
        flag = "✓" if ok else "✗ MISS"
        print(f"\n{flag} [{_LQ_ZH[subj]}] {gender} {bazi}  master={mstr} engine={det}")
        print(f"    透干: {len(stems)}处 {[l['position']+l['char'] for l in stems]}")
        print(f"    本气根: {len(benqi)}处 {[l['position']+l['char'] for l in benqi]}")
        print(f"    藏干根: {len(canggan)}处 {[l['position']+l['char'] for l in canggan]}")
        print(f"    support: {rel.get('support_text','')}")


if __name__ == "__main__":
    main()
