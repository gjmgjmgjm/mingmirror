#!/usr/bin/env python3
"""Leave-one-out weight calibration for the year-question rule reasoner.

Compares several weighting schemes on the 25 contest8 LOO year-questions:

- (A) current engine weights (baseline; should reproduce ~35% top-1)
- (B) raw feature count (all weights = 1)
- (C) count excluding anti-predictive ``stem_star`` + corrected 天干五合
- (D) per-signal empirical GOLD fire-rate (LOO-smoothed)
- (E) L2 logistic regression (LOO)

Reports top-1 / top-2 accuracy for each and prints the learned weights for the
best scheme, ready to paste into ``tools/bazi_ai/rule_reasoner.py``.

All evaluation is leave-one-out at the *question* level (hold out all options of
one question, fit on the rest), so numbers are not train/test-contaminated.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import (  # noqa: E402
    _extract_years,
    load_baziqa,
    person_to_bazi,
)
from tools.bazi_ai.rule_reasoner import RuleReasoner  # noqa: E402
from benchmarks.baziqa.rule_diagnose import (  # noqa: E402
    extract_features,
    _birth,
    _qtype,
)

# Current engine weights (mirrors _score_year_for_star + _score_dayun_for_star).
CURRENT_WEIGHTS = {
    "stem_star": 2.0,
    "branch_liuhe_palace": 1.2,
    "branch_sanhe_palace": 1.3,
    "branch_sanhui_palace": 1.0,
    "branch_chong_palace": -1.0,   # penalty_for_clash=True path (marriage/children)
    "hidden_star": 0.5,
    "stem_wuhe_daymaster": 0.3,
    "dayun_stem_star": 0.8,
    "dayun_hidden_star": 0.5,
    "dayun_liuhe_palace": 0.5,
    "dayun_sanhe_palace": 0.4,
    "dayun_chong_palace": -0.3,
    "parent_guansha_ke": 0.5,
    # new signals absent from current engine → weight 0 in baseline:
    "tian_kang_di_chong": 0.0,
    "sui_yun_bing_lin": 0.0,
    "fu_yin_day_branch": 0.0,
    "fan_yin_day_branch": 0.0,
}


def build_dataset() -> List[Dict]:
    """Return list of {features: [dict per option], gold_idx, n}."""
    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    data = []
    for p in contest:
        bazi = person_to_bazi(p)
        bd, bt = _birth(p)
        gender = p.get("profile", {}).get("gender", "male")
        for q in p.get("questions", []):
            opts = q.get("options", [])
            if not any(_extract_years(o) for o in opts) or not bazi or not bd:
                continue
            gl = q.get("answer", "")
            gold_idx = (ord(gl.upper()) - 65) if (gl and len(gl) == 1 and gl.isalpha()) else None
            if gold_idx is None or gold_idx >= len(opts):
                continue
            try:
                reasoner = RuleReasoner(bazi, gender, bd, bt)
            except Exception:
                continue
            stars, palace, kind = _qtype(reasoner, q.get("question", ""))
            feats = []
            for o in opts:
                yrs = _extract_years(o)
                if not yrs:
                    feats.append(None)
                    continue
                feats.append(extract_features(reasoner, kind, stars, palace, yrs[0]))
            data.append({"feats": feats, "gold": gold_idx, "q": q.get("question", "")})
    return data


def _vocab(dataset: List[Dict]) -> List[str]:
    vocab = set(CURRENT_WEIGHTS.keys())
    for d in dataset:
        for fr in d["feats"]:
            if fr:
                vocab.update(fr.keys())
    return sorted(vocab)


def _score(feats: Dict, weights: Dict[str, float]) -> float:
    return sum(weights.get(k, 0.0) * v for k, v in (feats or {}).items())


def _topk_accuracy(dataset: List[Dict], weights: Dict[str, float]) -> Tuple[float, float, int]:
    top1 = top2 = n = 0
    for d in dataset:
        scored = [(i, _score(fr, weights)) for i, fr in enumerate(d["feats"]) if fr is not None]
        if not scored:
            continue
        n += 1
        scored.sort(key=lambda x: -x[1])
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            top1 += 1
        if d["gold"] in order[:2]:
            top2 += 1
    return (100.0 * top1 / n if n else 0.0,
            100.0 * top2 / n if n else 0.0, n)


def scheme_current(dataset) -> Dict[str, float]:
    return dict(CURRENT_WEIGHTS)


def scheme_raw(dataset) -> Dict[str, float]:
    return {k: 1.0 for k in _vocab(dataset)}


def scheme_no_stemstar(dataset) -> Dict[str, float]:
    w = scheme_raw(dataset)
    w["stem_star"] = 0.0
    return w


def scheme_firerate_loo(dataset) -> Dict[str, float]:
    """Per-signal weight = LOO gold-fire-rate − pick-fire-rate on the rest.

    For each held-out question, weights come from the *other* questions only.
    We return the scheme fitted on ALL data (for inspection), but accuracy is
    computed with a true LOO inside ``loo_accuracy``.
    """
    return _firerate_weights(dataset, exclude=None)


def _firerate_weights(dataset, exclude: int) -> Dict[str, float]:
    gold_fire = defaultdict(int)
    other_fire = defaultdict(int)
    n_gold = n_other = 0
    for di, d in enumerate(dataset):
        if di == exclude:
            continue
        for i, fr in enumerate(d["feats"]):
            if not fr:
                continue
            if i == d["gold"]:
                n_gold += 1
                for s, v in fr.items():
                    if v:
                        gold_fire[s] += 1
            else:
                n_other += 1
                for s, v in fr.items():
                    if v:
                        other_fire[s] += 1
    weights = {}
    sigs = set(gold_fire) | set(other_fire)
    for s in sigs:
        gr = gold_fire[s] / n_gold if n_gold else 0.0
        orr = other_fire[s] / n_other if n_other else 0.0
        weights[s] = gr - orr  # positive ⇒ fires more on gold
    return weights


def loo_accuracy(dataset, weighter) -> Tuple[float, float, int]:
    """True LOO: recompute weights excluding each question, then rank it."""
    top1 = top2 = n = 0
    for di, d in enumerate(dataset):
        weights = weighter(dataset, di) if _takes_exclude(weighter) else weighter(dataset)
        scored = [(i, _score(fr, weights)) for i, fr in enumerate(d["feats"]) if fr is not None]
        if not scored:
            continue
        n += 1
        scored.sort(key=lambda x: -x[1])
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            top1 += 1
        if d["gold"] in order[:2]:
            top2 += 1
    return (100.0 * top1 / n if n else 0.0,
            100.0 * top2 / n if n else 0.0, n)


def _takes_exclude(weighter) -> bool:
    import inspect
    return "exclude" in inspect.signature(weighter).parameters


def scheme_logreg_loo(dataset) -> Dict[str, float]:
    """Logistic regression fitted on ALL data (inspected); LOO accuracy separate."""
    from sklearn.linear_model import LogisticRegression
    vocab = _vocab(dataset)
    idx = {s: i for i, s in enumerate(vocab)}
    X, y = [], []
    for d in dataset:
        for i, fr in enumerate(d["feats"]):
            if not fr:
                continue
            vec = np.zeros(len(vocab))
            for s, v in fr.items():
                vec[idx[s]] = v
            X.append(vec)
            y.append(1 if i == d["gold"] else 0)
    X = np.array(X)
    y = np.array(y)
    clf = LogisticRegression(
        max_iter=2000, C=0.5, class_weight="balanced", solver="lbfgs"
    ).fit(X, y)
    return {vocab[i]: float(clf.coef_[0][i]) for i in range(len(vocab))}


def loo_logreg(dataset) -> Tuple[float, float, int]:
    from sklearn.linear_model import LogisticRegression
    vocab = _vocab(dataset)
    idx = {s: i for i, s in enumerate(vocab)}
    top1 = top2 = n = 0
    for held in range(len(dataset)):
        train_X, train_y = [], []
        for di, d in enumerate(dataset):
            if di == held:
                continue
            for i, fr in enumerate(d["feats"]):
                if not fr:
                    continue
                vec = np.zeros(len(vocab))
                for s, v in fr.items():
                    vec[idx[s]] = v
                train_X.append(vec)
                train_y.append(1 if i == d["gold"] else 0)
        clf = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced").fit(
            np.array(train_X), np.array(train_y)
        )
        d = dataset[held]
        scored = []
        for i, fr in enumerate(d["feats"]):
            if not fr:
                continue
            vec = np.zeros(len(vocab))
            for s, v in fr.items():
                vec[idx[s]] = v
            scored.append((i, clf.decision_function([vec])[0]))
        n += 1
        scored.sort(key=lambda x: -x[1])
        order = [i for i, _ in scored]
        if d["gold"] == order[0]:
            top1 += 1
        if d["gold"] in order[:2]:
            top2 += 1
    return (100.0 * top1 / n if n else 0.0, 100.0 * top2 / n if n else 0.0, n)


def main() -> None:
    dataset = build_dataset()
    print(f"Dataset: {len(dataset)} year-questions", file=sys.stderr)

    schemes = [
        ("A current engine", scheme_current, False),
        ("B raw count", scheme_raw, False),
        ("C no_stemstar", scheme_no_stemstar, False),
        ("D fire-rate (LOO)", _firerate_weights, True),
    ]
    print(f"\n{'scheme':24s} {'top1':>7s} {'top2':>7s} {'n':>4s}")
    best_name, best_acc, best_w = None, -1, None
    for name, weighter, loo in schemes:
        if loo:
            t1, t2, n = loo_accuracy(dataset, weighter)
        else:
            w = weighter(dataset)
            t1, t2, n = _topk_accuracy(dataset, w)
        print(f"{name:24s} {t1:6.1f}% {t2:6.1f}% {n:4d}")
        if t1 > best_acc:
            best_acc, best_name, best_w = t1, name, (weighter(dataset, len(dataset)) if loo else weighter(dataset))

    # Logistic regression (own LOO path).
    t1, t2, n = loo_logreg(dataset)
    print(f"{'E logreg (LOO)':24s} {t1:6.1f}% {t2:6.1f}% {n:4d}")
    if t1 > best_acc:
        best_acc, best_name, best_w = t1, "E logreg", scheme_logreg_loo(dataset)

    print(f"\nBest scheme: {best_name}  top-1 = {best_acc:.1f}%")
    print("\nLearned weights (sorted; paste into rule_reasoner):")
    for s, w in sorted(best_w.items(), key=lambda x: -x[1]):
        print(f"   {s:26s} {w:+.3f}")


if __name__ == "__main__":
    main()
