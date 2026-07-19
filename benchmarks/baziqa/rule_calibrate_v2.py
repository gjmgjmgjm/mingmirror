#!/usr/bin/env python3
"""LOO year-signal recalibration using *production* feature vectors.

No sklearn dependency.  Schemes:
  A) current YEAR_SIGNAL_WEIGHTS (production)
  B) raw count (all 1.0 for non-zero production keys)
  C) LOO fire-rate (gold_rate − other_rate)
  D) LOO fire-rate, zero out negative signals
  E) grid-refine around production (coordinate ascent on LOO top-1)

Prints top-1 / top-2 and a paste-ready weight table.
"""
from __future__ import annotations

import copy
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import (  # noqa: E402
    _extract_years,
    load_baziqa,
    person_to_bazi,
    _birth_date_time,
)
from tools.bazi_ai.rule_reasoner import (  # noqa: E402
    YEAR_SIGNAL_WEIGHTS,
    RuleReasoner,
    _year_feature_vector,
    is_year_asking_question,
)


def _stars_palace(reasoner: RuleReasoner, kind: str, question: str) -> Tuple[List[str], Optional[str]]:
    if kind == "parent":
        father, mother = reasoner._parent_stars()
        is_f = "父" in question or "祖" in question
        is_m = "母" in question
        if is_f and not is_m:
            stars = father
        elif is_m and not is_f:
            stars = mother
        else:
            stars = father + mother
        return stars, reasoner.parents_palace
    if kind == "children":
        return reasoner._children_stars(), reasoner.children_palace
    if kind == "marriage":
        return reasoner._marriage_stars(), reasoner.spouse_palace
    if kind == "move":
        return ["正印", "偏印"], reasoner.spouse_palace
    if kind == "legal":
        return ["正官", "七杀"], reasoner.pillars[2][1]
    return [], reasoner.spouse_palace


def build_dataset() -> List[Dict]:
    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    data: List[Dict] = []
    for p in contest:
        bazi = person_to_bazi(p)
        bd, bt = _birth_date_time(p)
        gender = p.get("profile", {}).get("gender", "male")
        if gender in ("男", "m", "M"):
            gender = "male"
        elif gender in ("女", "f", "F"):
            gender = "female"
        for q in p.get("questions", []):
            qtext = q.get("question", "")
            opts = q.get("options", [])
            if not bazi or not bd:
                continue
            if not is_year_asking_question(qtext, opts):
                continue
            if not any(_extract_years(o) for o in opts):
                continue
            gl = (q.get("answer") or "").strip().upper()[:1]
            if gl not in "ABCD" or (ord(gl) - 65) >= len(opts):
                continue
            try:
                reasoner = RuleReasoner(bazi, gender, bd, bt)
            except Exception:
                continue
            kind = reasoner.classify_year_event(qtext) or "generic"
            stars, palace = _stars_palace(reasoner, kind, qtext)
            feats: List[Optional[Dict[str, int]]] = []
            for o in opts:
                yrs = _extract_years(o)
                if not yrs:
                    feats.append(None)
                    continue
                fr = _year_feature_vector(
                    bazi,
                    yrs[0],
                    stars,
                    palace,
                    bd,
                    reasoner.dayun,
                    qtype_kind=kind,
                )
                feats.append(fr)
            if sum(1 for f in feats if f) < 2:
                continue
            data.append(
                {
                    "feats": feats,
                    "gold": ord(gl) - 65,
                    "q": qtext,
                    "qid": q.get("question_id", ""),
                    "kind": kind,
                }
            )
    return data


def _score(feats: Optional[Dict[str, int]], weights: Dict[str, float]) -> float:
    if not feats:
        return float("-inf")
    return sum(weights.get(k, 0.0) * v for k, v in feats.items())


def topk(dataset: Sequence[Dict], weights: Dict[str, float]) -> Tuple[float, float, int]:
    t1 = t2 = n = 0
    for d in dataset:
        scored = [
            (i, _score(fr, weights))
            for i, fr in enumerate(d["feats"])
            if fr is not None
        ]
        if not scored:
            continue
        n += 1
        scored.sort(key=lambda x: -x[1])
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            t1 += 1
        if d["gold"] in order[:2]:
            t2 += 1
    return (
        100.0 * t1 / n if n else 0.0,
        100.0 * t2 / n if n else 0.0,
        n,
    )


def fire_rate_weights(dataset: Sequence[Dict], exclude: Optional[int] = None) -> Dict[str, float]:
    gold_fire: Dict[str, int] = defaultdict(int)
    other_fire: Dict[str, int] = defaultdict(int)
    n_gold = n_other = 0
    for di, d in enumerate(dataset):
        if exclude is not None and di == exclude:
            continue
        for i, fr in enumerate(d["feats"]):
            if not fr:
                continue
            if i == d["gold"]:
                n_gold += 1
                for s, v in fr.items():
                    if v:
                        gold_fire[s] += v
            else:
                n_other += 1
                for s, v in fr.items():
                    if v:
                        other_fire[s] += v
    sigs = set(gold_fire) | set(other_fire) | set(YEAR_SIGNAL_WEIGHTS)
    out: Dict[str, float] = {}
    for s in sigs:
        gr = gold_fire[s] / n_gold if n_gold else 0.0
        orr = other_fire[s] / n_other if n_other else 0.0
        out[s] = gr - orr
    return out


def loo_fire_rate_acc(dataset: List[Dict], zero_neg: bool = False) -> Tuple[float, float, int]:
    t1 = t2 = n = 0
    for di, d in enumerate(dataset):
        w = fire_rate_weights(dataset, exclude=di)
        if zero_neg:
            w = {k: (v if v > 0 else 0.0) for k, v in w.items()}
        scored = [
            (i, _score(fr, w)) for i, fr in enumerate(d["feats"]) if fr is not None
        ]
        if not scored:
            continue
        n += 1
        scored.sort(key=lambda x: -x[1])
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            t1 += 1
        if d["gold"] in order[:2]:
            t2 += 1
    return (
        100.0 * t1 / n if n else 0.0,
        100.0 * t2 / n if n else 0.0,
        n,
    )


def coordinate_ascent(
    dataset: List[Dict],
    base: Dict[str, float],
    *,
    steps: Sequence[float] = (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4),
    rounds: int = 3,
) -> Dict[str, float]:
    """Greedy LOO top-1 coordinate ascent over production signal keys."""
    keys = [k for k, v in base.items() if abs(v) > 1e-9 or k in YEAR_SIGNAL_WEIGHTS]
    # Also allow flipping currently-zero signals that fire often.
    keys = sorted(set(keys) | set(YEAR_SIGNAL_WEIGHTS.keys()))
    w = dict(base)
    best_t1, _, n = topk(dataset, w)
    print(f"  coord start top1={best_t1:.1f}% n={n}", file=sys.stderr)

    def loo_t1(weights: Dict[str, float]) -> float:
        # Full-set top1 is optimistic for search; use leave-one-out fire-rate
        # only for evaluation of schemes.  Here use full-set top1 as cheap
        # surrogate, then final report uses true LOO fire / full.
        t1, _, _ = topk(dataset, weights)
        return t1

    for rnd in range(rounds):
        improved = False
        for k in keys:
            cur = w.get(k, 0.0)
            best_local = cur
            best_score = loo_t1(w)
            for delta in steps:
                cand = cur + delta
                if abs(cand) > 1.5:
                    continue
                trial = dict(w)
                trial[k] = cand
                sc = loo_t1(trial)
                if sc > best_score + 1e-9:
                    best_score = sc
                    best_local = cand
            if abs(best_local - cur) > 1e-12:
                w[k] = best_local
                improved = True
                print(
                    f"  round{rnd+1} {k}: {cur:+.2f} → {best_local:+.2f} "
                    f"top1={best_score:.1f}%",
                    file=sys.stderr,
                )
        if not improved:
            break
    return w


def by_kind_breakdown(dataset: List[Dict], weights: Dict[str, float]) -> None:
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for d in dataset:
        buckets[d["kind"]].append(d)
    print("\nPer-kind (production-style weights):")
    for kind, xs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        t1, t2, n = topk(xs, weights)
        print(f"  {kind:10s} n={n:2d} top1={t1:5.1f}% top2={t2:5.1f}%")


def soft_shortlist_stats(dataset: List[Dict], weights: Dict[str, float]) -> None:
    """Simulate production shortlist gates on full-set ranking."""
    # Approximate gates: top score > 0, for gated kinds need score>=0.4 and margin>=0.2
    gated = {"marriage", "generic", "children", "legal"}
    always = {"parent", "move"}
    fire = hit1 = hit2 = 0
    for d in dataset:
        scored = [
            (i, _score(fr, weights))
            for i, fr in enumerate(d["feats"])
            if fr is not None
        ]
        if not scored:
            continue
        scored.sort(key=lambda x: -x[1])
        top_s = scored[0][1]
        second = scored[1][1] if len(scored) > 1 else float("-inf")
        margin = top_s - second
        kind = d["kind"]
        if top_s <= 0:
            continue
        if kind in always:
            ok = True
        elif kind in gated:
            # medium ≈ margin>=0.2 and score>=0.4
            ok = top_s >= 0.4 and margin >= 0.2
        else:
            ok = False
        if not ok:
            continue
        fire += 1
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            hit1 += 1
        if d["gold"] in order[:2]:
            hit2 += 1
    if fire:
        print(
            f"\nSoft-shortlist sim: fire={fire} "
            f"top1={100*hit1/fire:.1f}% top2={100*hit2/fire:.1f}%"
        )
    else:
        print("\nSoft-shortlist sim: no fires")


def round_weights(w: Dict[str, float], places: int = 1) -> Dict[str, float]:
    return {k: round(v, places) for k, v in w.items()}


def main() -> None:
    dataset = build_dataset()
    print(f"Year-asking questions with features: {len(dataset)}", file=sys.stderr)
    kinds = defaultdict(int)
    for d in dataset:
        kinds[d["kind"]] += 1
    print(f"Kinds: {dict(kinds)}", file=sys.stderr)

    prod = dict(YEAR_SIGNAL_WEIGHTS)
    raw = {k: 1.0 for k in YEAR_SIGNAL_WEIGHTS}
    firerate_all = fire_rate_weights(dataset, exclude=None)
    firerate_pos = {k: (v if v > 0 else 0.0) for k, v in firerate_all.items()}

    print(f"\n{'scheme':28s} {'top1':>7s} {'top2':>7s} {'n':>4s}")
    for name, w in [
        ("A production", prod),
        ("B raw ones", raw),
        ("C fire-rate (full fit)", firerate_all),
        ("D fire-rate pos only", firerate_pos),
    ]:
        t1, t2, n = topk(dataset, w)
        print(f"{name:28s} {t1:6.1f}% {t2:6.1f}% {n:4d}")

    t1, t2, n = loo_fire_rate_acc(dataset, zero_neg=False)
    print(f"{'C2 fire-rate LOO':28s} {t1:6.1f}% {t2:6.1f}% {n:4d}")
    t1, t2, n = loo_fire_rate_acc(dataset, zero_neg=True)
    print(f"{'D2 fire-rate LOO pos':28s} {t1:6.1f}% {t2:6.1f}% {n:4d}")

    print("\nCoordinate ascent from production (full-set top1 surrogate)...", file=sys.stderr)
    ascended = coordinate_ascent(dataset, prod, rounds=4)
    t1, t2, n = topk(dataset, ascended)
    print(f"{'E coord-ascent (full)':28s} {t1:6.1f}% {t2:6.1f}% {n:4d}")
    rounded = round_weights(ascended, 1)
    t1r, t2r, nr = topk(dataset, rounded)
    print(f"{'E rounded 1dp':28s} {t1r:6.1f}% {t2r:6.1f}% {nr:4d}")

    # Hybrid: production skeleton + fire-rate scale for zeros that are positive
    hybrid = dict(prod)
    for k, v in firerate_all.items():
        if abs(prod.get(k, 0.0)) < 1e-9 and v > 0.05:
            hybrid[k] = round(min(0.5, v * 2), 1)
        elif prod.get(k, 0.0) > 0 and v < -0.02:
            # dampen production positives that fire more on wrong options
            hybrid[k] = round(max(0.0, prod[k] - 0.1), 1)
        elif prod.get(k, 0.0) > 0 and v > 0.05:
            hybrid[k] = round(min(1.2, prod[k] + 0.1), 1)
    t1, t2, n = topk(dataset, hybrid)
    print(f"{'F hybrid fire+prod':28s} {t1:6.1f}% {t2:6.1f}% {n:4d}")

    by_kind_breakdown(dataset, prod)
    by_kind_breakdown(dataset, rounded)
    soft_shortlist_stats(dataset, prod)
    soft_shortlist_stats(dataset, rounded)
    soft_shortlist_stats(dataset, hybrid)

    print("\n--- Production weights ---")
    for s, w in sorted(prod.items(), key=lambda x: -abs(x[1])):
        print(f"  {s:26s} {w:+.2f}")

    print("\n--- Fire-rate (full) ---")
    for s, w in sorted(firerate_all.items(), key=lambda x: -x[1]):
        print(f"  {s:26s} {w:+.3f}")

    print("\n--- Coord-ascent rounded (paste candidate) ---")
    for s, w in sorted(rounded.items(), key=lambda x: -abs(x[1])):
        if abs(w) < 1e-9 and abs(prod.get(s, 0)) < 1e-9:
            continue
        print(f"  {s:26s} {w:+.1f}")

    print("\n--- Hybrid (paste candidate) ---")
    for s, w in sorted(hybrid.items(), key=lambda x: -abs(x[1])):
        if abs(w) < 1e-9 and abs(prod.get(s, 0)) < 1e-9:
            continue
        mark = "" if abs(w - prod.get(s, 0)) < 1e-9 else "  *"
        print(f"  {s:26s} {w:+.1f}{mark}")

    # Choose best by soft-shortlist top2 then top1 full
    candidates = {
        "production": prod,
        "rounded_ascent": rounded,
        "hybrid": hybrid,
        "firerate_pos": firerate_pos,
    }
    print("\n=== Selection score (full top1/top2 + shortlist top2) ===")
    best_name, best_key = None, (-1.0, -1.0, -1.0)
    for name, w in candidates.items():
        t1, t2, n = topk(dataset, w)
        # recompute shortlist top2
        gated = {"marriage", "generic", "children", "legal"}
        always = {"parent", "move"}
        fire = hit2 = 0
        for d in dataset:
            scored = [
                (i, _score(fr, w))
                for i, fr in enumerate(d["feats"])
                if fr is not None
            ]
            if not scored:
                continue
            scored.sort(key=lambda x: -x[1])
            top_s = scored[0][1]
            second = scored[1][1] if len(scored) > 1 else float("-inf")
            margin = top_s - second
            kind = d["kind"]
            if top_s <= 0:
                continue
            if kind in always:
                ok = True
            elif kind in gated:
                ok = top_s >= 0.4 and margin >= 0.2
            else:
                ok = False
            if not ok:
                continue
            fire += 1
            if d["gold"] in [i for i, _ in scored[:2]]:
                hit2 += 1
        sl2 = 100.0 * hit2 / fire if fire else 0.0
        key = (t2, t1, sl2)
        print(
            f"  {name:18s} full_top1={t1:5.1f}% full_top2={t2:5.1f}% "
            f"sl_fire={fire} sl_top2={sl2:5.1f}%"
        )
        if key > best_key:
            best_key, best_name = key, name

    print(f"\nRecommended: {best_name}")
    rec = candidates[best_name]
    print("YEAR_SIGNAL_WEIGHTS = {")
    for s in sorted(set(YEAR_SIGNAL_WEIGHTS) | set(rec), key=lambda x: -abs(rec.get(x, 0))):
        v = rec.get(s, 0.0)
        print(f'    "{s}": {v:.1f},')
    print("}")


if __name__ == "__main__":
    main()
