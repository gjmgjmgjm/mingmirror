#!/usr/bin/env python3
"""Per-signal diagnostic for the year-question rule reasoner.

For each contest8 LOO year-question, decompose scoring into individual signals
applied to *every* option (not just the winner), then report how often each
signal fires on the GOLD option vs the engine's PICK vs the runner-up.

Purpose: decide whether the engine fails because (a) the right signals exist
but have wrong weights, or (b) the gold option carries a signal the engine
doesn't model at all.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import (  # noqa: E402
    _extract_years,
    load_baziqa,
    person_to_bazi,
)
from tools.bazi_ai.rule_reasoner import (  # noqa: E402
    RuleReasoner,
    _active_dayun_for_year,
    _is_chong,
    _is_liu_he,
    _san_he_element_for_pair,
    _san_hui_element_for_pair,
    _shishen,
    _year_pillar,
    _ZHI_CANG_GAN,
)
from tools.bazi_ai.bazi_validator import extract_pillars  # noqa: E402

# Correct 天干五合 pairs (the engine's version checks stems against the
# *branch* table and therefore never fires — this is the corrected set).
_TIAN_GAN_WU_HE = {
    ("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸"),
}

# Extra 应期 signals not modelled by the current engine.
_TIAN_KANG_DI_CHONG = "tian_kang_di_chong"   # 天克地冲: year vs day pillar
_SUI_YUN_BING_LIN = "sui_yun_bing_lin"       # 岁运并临: year pillar == dayun pillar
_FU_YIN_DAY = "fu_yin_day_branch"            # 伏吟: year branch == day branch
_FAN_YIN_DAY = "fan_yin_day_branch"          # 反吟: year branch clashes day branch


def _birth(person: Dict) -> Tuple[str, str]:
    b = person.get("profile", {}).get("birth", {})
    y, mo, d = b.get("year"), b.get("month"), b.get("day")
    if not all(isinstance(v, int) for v in (y, mo, d)):
        return "", ""
    return f"{y:04d}-{mo:02d}-{d:02d}", f"{b.get('hour', 0):02d}:{b.get('minute', 0):02d}"


def _qtype(reasoner: RuleReasoner, question: str) -> Tuple[List[str], str, str]:
    """Return (target_stars, palace_zhi, kind) for this question."""
    q = question
    if any(k in q for k in ["结婚", "婚姻", "第二婚", "那一年结婚", "哪年结婚"]):
        return reasoner._marriage_stars(), reasoner.spouse_palace, "marriage"
    if any(k in q for k in ["子女", "孩子", "儿子", "女儿", "得子", "得女", "那年出生", "得到子女", "何一年得到"]):
        return reasoner._children_stars(), reasoner.children_palace, "children"
    if any(k in q for k in ["父", "母", "仙逝", "去世", "逝世"]):
        father, mother = reasoner._parent_stars()
        is_f = "父" in q
        is_m = "母" in q
        stars = father if is_f and not is_m else (mother if is_m and not is_f else father + mother)
        return stars, reasoner.parents_palace, "parent"
    # non-canonical event: no star/palace mapping; treat as event on day branch
    return [], reasoner.pillars[2][1], "event"


def extract_features(
    reasoner: RuleReasoner, qtype_kind: str, stars: List[str],
    palace_zhi: str, year: int,
) -> Dict[str, int]:
    """Binary feature vector for one option-year (mirrors + extends engine signals)."""
    f: Dict[str, int] = defaultdict(int)
    pillars = reasoner.pillars
    day_master = reasoner.day_master
    day_branch = pillars[2][1]
    yp = _year_pillar(year)
    yg, yz = yp[0], yp[1]
    yss = _shishen(day_master, yg)

    if stars and yss in stars:
        f["stem_star"] += 1
    if palace_zhi:
        if _is_liu_he(yz, palace_zhi):
            f["branch_liuhe_palace"] += 1
        if _san_he_element_for_pair(yz, palace_zhi):
            f["branch_sanhe_palace"] += 1
        if _san_hui_element_for_pair(yz, palace_zhi):
            f["branch_sanhui_palace"] += 1
        if _is_chong(yz, palace_zhi):
            f["branch_chong_palace"] += 1
    for gan in _ZHI_CANG_GAN.get(yz, ()):
        if stars and _shishen(day_master, gan) in stars:
            f["hidden_star"] += 1
    # CORRECTED 天干五合 (stem five-combination with day master)
    pair = tuple(sorted((day_master, yg)))
    if pair in _TIAN_GAN_WU_HE:
        f["stem_wuhe_daymaster"] += 1

    # dayun signals
    ad = _active_dayun_for_year(reasoner.dayun, year, reasoner.birth_date)
    if ad and len(ad.get("pillar", "")) == 2:
        dg, dz = ad["pillar"][0], ad["pillar"][1]
        if stars and _shishen(day_master, dg) in stars:
            f["dayun_stem_star"] += 1
        for gan in _ZHI_CANG_GAN.get(dz, ()):
            if stars and _shishen(day_master, gan) in stars:
                f["dayun_hidden_star"] += 1
        if palace_zhi:
            if _is_liu_he(dz, palace_zhi):
                f["dayun_liuhe_palace"] += 1
            if _san_he_element_for_pair(dz, palace_zhi):
                f["dayun_sanhe_palace"] += 1
            if _is_chong(dz, palace_zhi):
                f["dayun_chong_palace"] += 1

    # NEW 应期 signals
    # 天克地冲 vs 日柱: year stem clashes day stem (different element, restrains)
    # + year branch clashes day branch
    dp_gan, dp_zhi = pillars[2][0], day_branch
    gan_clash = (_element_index(yg) // 2 != _element_index(dp_gan) // 2) and _restrains(yg, dp_gan)
    if gan_clash and _is_chong(yz, dp_zhi):
        f[_TIAN_KANG_DI_CHONG] += 1
    # 岁运并临: year pillar == active dayun pillar
    if ad and ad.get("pillar") == yp:
        f[_SUI_YUN_BING_LIN] += 1
    # 伏吟/反吟 on day branch
    if yz == day_branch:
        f[_FU_YIN_DAY] += 1
    if _is_chong(yz, day_branch):
        f[_FAN_YIN_DAY] += 1

    # parent-death extra: 官杀克身 on year stem
    if qtype_kind == "parent" and yss in ("七杀", "正官"):
        f["parent_guansha_ke"] += 1

    return dict(f)


_ELM = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
        "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}


def _element_index(gan: str) -> int:
    return ["木", "火", "土", "金", "水"].index(_ELM[gan])


def _restrains(a: str, b: str) -> bool:
    """True if stem a's element restrains (克) stem b's element."""
    return _SHENG.get(_ELM[a]) is not None and _restrains_elm(_ELM[a], _ELM[b])


def _restrains_elm(a: str, b: str) -> bool:
    ke = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    return ke.get(a) == b


def main() -> None:
    data = Path("benchmarks/baziqa/data")
    contest, _ = load_baziqa(data)

    # Build (person, q) pairs that are year-questions.
    pairs = []
    for p in contest:
        bazi = person_to_bazi(p)
        bd, bt = _birth(p)
        gender = p.get("profile", {}).get("gender", "male")
        for q in p.get("questions", []):
            opts = q.get("options", [])
            if any(_extract_years(o) for o in opts) and bazi and bd:
                pairs.append((bazi, bd, bt, gender, q))

    print(f"Year-questions found: {len(pairs)}", file=sys.stderr)

    signal_gold = defaultdict(int)   # signal -> #questions where it fires on gold
    signal_pick = defaultdict(int)   # signal -> #questions where it fires on engine pick
    signal_gold_not_pick = defaultdict(int)  # fires on gold but NOT on pick (missing-feature evidence)
    questions_where_pick_has_gold_only = 0

    rank_counts = defaultdict(int)   # rank of gold among scored options
    n_pickable = 0

    for bazi, bd, bt, gender, q in pairs:
        opts = q["options"]
        gold_idx = None
        # gold letter -> idx
        gl = q.get("answer", "")
        if gl and len(gl) == 1 and gl.isalpha():
            gold_idx = ord(gl.upper()) - 65
        if gold_idx is None or gold_idx >= len(opts):
            continue
        try:
            reasoner = RuleReasoner(bazi, gender, bd, bt)
        except Exception:
            continue
        stars, palace, kind = _qtype(reasoner, q.get("question", ""))
        feat_rows = []
        scores = []
        for o in opts:
            yrs = _extract_years(o)
            if not yrs:
                feat_rows.append(None)
                scores.append(-1e9)
                continue
            fr = extract_features(reasoner, kind, stars, palace, yrs[0])
            feat_rows.append(fr)
            # current engine score (recomputed via reason() is per-qtype; approximate
            # by summing the engine's own reason on full option list)
            scores.append(sum(fr.values()))  # unweighted count, for ranking reference
        # engine pick (via real reason())
        cand = reasoner.reason(q.get("question", ""), opts)
        pick_letter = cand.option if cand else None
        pick_idx = (ord(pick_letter) - 65) if pick_letter else None

        gold_feat = feat_rows[gold_idx] or {}
        pick_feat = feat_rows[pick_idx] or {} if pick_idx is not None and pick_idx < len(feat_rows) and feat_rows[pick_idx] else {}

        for sig, v in gold_feat.items():
            if v:
                signal_gold[sig] += 1
        for sig, v in pick_feat.items():
            if v:
                signal_pick[sig] += 1
        gold_only = {s for s, v in gold_feat.items() if v and not pick_feat.get(s)}
        for s in gold_only:
            signal_gold_not_pick[s] += 1
        if gold_only:
            questions_where_pick_has_gold_only += 1

        # rank of gold by unweighted feature count
        if all(fr is not None for fr in feat_rows):
            n_pickable += 1
            gold_score = sum(gold_feat.values())
            rank = 1 + sum(1 for fr in feat_rows if sum((fr or {}).values()) > gold_score)
            rank_counts[rank] += 1

    print("\n=== Signal fire-rate: GOLD option vs ENGINE PICK ===")
    all_sigs = sorted(set(signal_gold) | set(signal_pick), key=lambda s: -signal_gold.get(s, 0))
    print(f"{'signal':26s} {'gold':>5s} {'pick':>5s} {'gold_not_pick':>14s}")
    for s in all_sigs:
        print(f"{s:26s} {signal_gold[s]:>5d} {signal_pick[s]:>5d} {signal_gold_not_pick[s]:>14d}")

    print(f"\nQuestions where gold carries a signal the pick LACKS: "
          f"{questions_where_pick_has_gold_only}/{len(pairs)}")

    print(f"\n=== Rank of GOLD option by raw feature count (unweighted) ===")
    print(f"(out of {n_pickable} pickable questions; rank 1 = gold has most signals)")
    for r in sorted(rank_counts):
        print(f"  rank {r}: {rank_counts[r]}")
    top1 = rank_counts.get(1, 0)
    print(f"  → raw-count top-1 accuracy: {top1}/{n_pickable} = "
          f"{100*top1/n_pickable:.1f}%" if n_pickable else "  n/a")


if __name__ == "__main__":
    main()
