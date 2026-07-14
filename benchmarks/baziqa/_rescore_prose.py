#!/usr/bin/env python3
"""Offline re-scorer: quantify how much of the prose 60% is comparator crudeness
vs real LLM drift, using a saved validate_real --output JSON (full liuqin_analysis).

Anchors:
  field_match  (~77% on n=30) = trusted e2e signal (LLM echoed injected verdict).
  det          (~74-88%)      = deterministic ceiling.

Tries several engine-prose strength-dir variants and reports each variant's
prose-match rate. If a principled variant lifts prose from 60% toward ~77%,
the gap was comparator noise (reading is fine). If none lifts it, the prose
genuinely drifts and field is the only clean e2e signal.

Usage:
  python benchmarks/baziqa/_rescore_prose.py /tmp/n30_full.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.baziqa.validate_real import (  # noqa: E402
    _detect_liuqin_subject, _engine_liuqin_section,
    _master_subject_section, _field_strength, _SUBJ_FIELD_KEYS,
)

# ---- candidate engine-prose strength dirs ---------------------------------

# Engine weak-verdict markers (the LLM's rewording of an injected 弱).
_ENG_WEAK = re.compile(
    r"假星|虚浮|无根|不现|缘(分)?(浅|薄)|助力(不大|有限|不显)|受损|被穿害|穿害|"
    r"合化|合坏|坏根|夺食|截脚|根气不固|减弱|偏弱|虚弱|泄气|受克|耗泄|争合|孤露"
)
# Bare 弱 as a verdict — but not inside "不算弱/不弱".
_ENG_WEAK_BARE = re.compile(r"(?<!不)弱")
# Engine strong-verdict markers.
_ENG_STRONG = re.compile(r"真星|强根|通根|得令|帝旺|长生|有力|稳固|根深|真而(旺|强)")
# Hedging that discounts a strong cue: "看似有力/旺/强".
_HEDGE = re.compile(r"看似.{0,6}(有力|旺|强|有根)")


def _strip_hedge(text: str) -> str:
    """Remove '看似...有力/旺/强' hedges so they don't read as strong."""
    return _HEDGE.sub("看似", text)


def v0_current(text: str) -> str:
    """The shipped _strength_dir (regex explicit → token count). Replicated."""
    from benchmarks.baziqa.validate_real import _strength_dir
    return _strength_dir(text)


def v1_weakpatterns(text: str) -> str:
    """Add engine-weak regex patterns + discount hedges; bare 弱 counts weak."""
    if not text:
        return "?"
    t = _strip_hedge(text)
    weak = bool(_ENG_WEAK.search(t)) or bool(_ENG_WEAK_BARE.search(t))
    strong = bool(_ENG_STRONG.search(t))
    if weak and not strong:
        return "弱"
    if strong and not weak:
        return "强"
    if weak and strong:  # both: prefer explicit 弱 verdict (engine says "看似强但弱")
        return "弱"
    return "?"


def v2_trailing(text: str) -> str:
    """v1 + trailing-verdict rule: the last 强/弱 near the section end wins."""
    base = v1_weakpatterns(text)
    if base != "?":
        return base
    if not text:
        return "?"
    tail = text[-12:]
    w = bool(re.search(r"(?<!不)弱", tail))
    s = bool(re.search(r"(?<!不)(强|旺)", tail))
    if w and not s:
        return "弱"
    if s and not w:
        return "强"
    return "?"


VARIANTS = [("v0_current", v0_current), ("v1_weakpatterns", v1_weakpatterns),
            ("v2_trailing", v2_trailing)]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/n30_full.json"
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    rows = []  # (subject, master_dir, field_dir, engine_section)
    for rec in records:
        res = rec.get("result", {})
        master = rec.get("master", "")
        subj = _detect_liuqin_subject(master)
        if not subj:
            continue
        lq = res.get("liuqin_analysis", "")
        sec = _engine_liuqin_section(lq, subj) if isinstance(lq, str) else ""
        m_dir = _strength_dir_master(master, subj)
        f_dir = _field_strength(res.get("liuqin_strength") or {}, subj)
        rows.append((subj, m_dir, f_dir, sec))

    n = len(rows)
    field_hits = sum(1 for _, m, f, _ in rows if m != "?" and f != "?" and m == f)

    print(f"records={n}  field_match={field_hits}/{n} = {field_hits/n:.0%}  (trusted anchor)\n")
    print(f"{'variant':<16} {'prose_match':<14} {'vs field':<10} {'undecided(?)':<12}")
    print("-" * 52)
    for name, fn in VARIANTS:
        hits = q = 0
        for _, m, _, sec in rows:
            e = fn(sec)
            if e == "?":
                q += 1
                continue
            if m != "?" and m == e:
                hits += 1
        denom = n - q
        rate = hits / denom if denom else 0.0
        # also rate vs full n (counting ? as miss, like the headline)
        rate_full = hits / n
        print(f"{name:<16} {hits}/{denom}={rate:.0%}{'':<2} {rate_full:.0%}(full)  ?={q}")

    # Dump the cases where v0 and v2 disagree, for manual sanity check.
    print("\n--- v0 vs v2 disagreements (engine section) ---")
    shown = 0
    for subj, m, f, sec in rows:
        a, b = v0_current(sec), v2_trailing(sec)
        if a != b and shown < 12:
            print(f"  master={m} field={f} | v0={a} v2={b} | {subj}")
            print(f"    {sec.strip()[:140]}")
            shown += 1


def _strength_dir_master(master: str, subj: str) -> str:
    from benchmarks.baziqa.validate_real import _strength_dir
    return _strength_dir(_master_subject_section(master, subj))


if __name__ == "__main__":
    main()
