#!/usr/bin/env python3
"""Real-case validation harness (the ruler that replaces BaziQA MCQ).

Runs the production ``analyze_bazi`` on 杨炎 real cases (which carry a master's
narrative reading as ground truth), then compares STRUCTURAL claims between the
engine output and the master text:

- 财富方向 (富 / 中 / 穷)  — coarse bucket match
- 职业 keyphrase hit       — does the engine's career text mention a 职业象
                             the master also raised?
- 健康 keyphrase hit       — same for health/脏腑
- 六亲 side-by-side        — dumped for manual review (too nuanced to auto-score)

This is intentionally COARSE: master texts are noisy OCR narratives, so we lean
on side-by-side dump + a couple of cheap auto-metrics rather than pretending to
a precise accuracy number. The point is a repeatable ruler, not a false-precision
score.

Usage::

    python benchmarks/baziqa/validate_real.py --limit 6 \
        --api-key $DEEPSEEK_API_KEY --model deepseek-chat
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.engine import analyze_bazi  # noqa: E402

CASES = Path("bazi_knowledge/杨炎八字绝技_cases.jsonl")
EXTRA_KNOWLEDGE = [
    Path("bazi_knowledge/杨炎八字绝技_rulebook_compact.md"),
    Path("bazi_knowledge/杨炎八字绝技_mnemonics.md"),
    Path("bazi_knowledge/杨炎_knowledge_final.md"),
]
EXTRA_CASES = [Path("bazi_knowledge/杨炎八字绝技_cases.jsonl")]

# --- keyword dictionaries for coarse auto-metrics ---------------------------
_WEALTH_RICH = ["千万", "亿", "暴富", "巨富", "大富", "有钱", "富裕", "富翁", "百万"]
_WEALTH_MID = ["小康", "温饱", "稳定", "中产", "工薪", "工资"]
_WEALTH_POOR = ["穷", "贫", "破财", "没钱", "困难", "负债", "清贫", "温饱困难"]

_CAREER = ["公职", "公务员", "国企", "管理", "法律", "律师", "审计", "金融", "银行",
           "生意", "商", "老板", "创业", "技术", "设计", "创意", "教", "老师", "文",
           "医", "军", "警", "武", "自由职业", "稳定", "上班", "工程", "销售"]
_HEALTH = ["妇科", "子宫", "肝", "胆", "脾", "胃", "肺", "肾", "心", "血压",
           "呼吸", "神经", "骨", "血", "皮肤", "目", "眼", "头"]


def _bucket(text: str) -> str:
    if any(k in text for k in _WEALTH_RICH):
        return "富"
    if any(k in text for k in _WEALTH_POOR):
        return "穷"
    if any(k in text for k in _WEALTH_MID):
        return "中"
    return "?"


def _engine_wealth_bucket(level: str) -> str:
    if any(k in level for k in ["大富", "巨富", "中富", "小富"]):
        return "富"
    if any(k in level for k in ["中产", "小康"]):
        return "中"
    if any(k in level for k in ["温饱", "贫"]):
        return "穷"
    return "?"


def _hits(text: str, keys: List[str]) -> List[str]:
    return sorted({k for k in keys if k in text})


# --- 六亲断象 comparator (apples-to-apples for 杨炎 kinship cases) ----------
_LIUQIN_SUBJECT_PATTERNS = [
    ("father", ["父星", "父亲", "父断", "偏财为父"]),
    ("spouse", ["夫星", "丈夫", "妻星", "妻子", "配偶星", "正官为夫", "正财为妻"]),
    ("mother", ["母星", "母亲", "母断", "正印为母"]),
    ("child", ["子女星", "子女", "子星", "官杀为子女", "食伤为子女"]),
    ("sibling", ["兄弟", "姐妹", "比劫", "手足"]),
]
_LIUQIN_SECTION_LABEL = {
    "father": "【父亲】", "mother": "【母亲】",
    "spouse": "【配偶】", "child": "【子女】", "sibling": "【兄弟姐妹】",
}
# Master-side section headers (杨炎 readings start each relative's verdict with
# these). Used for section-aware extraction so body-strength talk (身弱杀旺 etc.)
# doesn't contaminate the kinship verdict.
_MASTER_SECTION_MARKERS = {
    "father": ["父亲断象", "父亲断", "父星断", "父灾", "· 父亲", "父星："],
    "mother": ["母亲断象", "母亲断", "母星断", "· 母亲", "母星："],
    "spouse": ["丈夫断象", "夫星断象", "夫星断", "夫灾", "妻子断象", "妻星断",
               "配偶断象", "· 丈夫", "· 配偶", "断夫", "断妻"],
    "child": ["子女断象", "子女断", "克子", "克子女", "· 子女"],
    "sibling": ["兄弟断象", "姐妹断象", "兄弟断", "兄弟情况", "· 兄弟", "· 姐妹"],
}
_STRONG_TOKS = ["真星", "强根", "通根", "得令", "帝旺", "长生", "有力", "稳固",
                "根深", "健康", "健朗", "助", "旺", "地位稳固", "依靠"]
_WEAK_TOKS = ["假星", "无根", "虚浮", "受克", "绝地", "死地", "缘薄", "缘浅",
              "不稳", "截脚", "克", "损", "漂", "弱", "孤露", "争合",
              "耗泄", "根气不固", "寒", "残", "孤"]


def _detect_liuqin_subject(master: str) -> str:
    """Which family member is the master's reading about (杨炎 cases are 单亲断象).

    Prefer an explicit section marker (earliest occurrence wins — the reading's
    primary focus usually comes first); fall back to keyword scatter.
    """
    best, best_idx = "", len(master) + 1
    for subj in ("father", "spouse", "mother", "child", "sibling"):
        for m in _MASTER_SECTION_MARKERS.get(subj, []):
            idx = master.find(m)
            if idx != -1 and idx < best_idx:
                best, best_idx = subj, idx
    if best:
        return best
    for subj, pats in _LIUQIN_SUBJECT_PATTERNS:
        if any(p in master for p in pats):
            return subj
    return ""


def _master_subject_section(master: str, subject: str) -> str:
    """Slice the master text down to the detected relative's verdict section.

    Body-strength discussion (身弱/杀旺/水旺) otherwise leaks into the verdict
    token count and flips the strength the wrong way. Falls back to the whole
    text when no section header is found (legacy behavior).
    """
    if not subject:
        return master
    markers = _MASTER_SECTION_MARKERS.get(subject, [])
    start = None
    for m in markers:
        idx = master.find(m)
        if idx != -1 and (start is None or idx < start):
            start = idx
    if start is None:
        return master
    end = len(master)
    for other, ms in _MASTER_SECTION_MARKERS.items():
        if other == subject:
            continue
        for m in ms:
            idx = master.find(m, start + 1)
            if idx != -1 and idx < end:
                end = idx
    return master[start:end]


def _strength_dir(text: str) -> str:
    """Verdict-first strength for a kinship section.

    杨炎 verdicts state 真星/假星 + 旺/衰 explicitly. A raw token count mis-reads
    cases like 根气不固+耗泄 (a 金/根 token gets counted strong though the master's
    verdict is weak), or hedges to "?" when 得生 and 克 balance. We trust explicit
    verdict markers first and only fall back to token balance.
    """
    if not text:
        return "?"
    strong_explicit = bool(
        re.search(r"真而(旺|强)|真星.{0,8}(旺|强|有力|稳固)|是为.{0,4}真星", text)
    )
    weak_explicit = bool(
        re.search(r"假(星|而|而弱)|虚浮(无根)?|无根|受.{0,3}克(制)?|耗泄|"
                  r"根气不固|缘(薄|浅)|截脚", text)
    )
    if strong_explicit and not weak_explicit:
        return "强"
    if weak_explicit and not strong_explicit:
        return "弱"
    s = sum(1 for t in _STRONG_TOKS if t in text)
    w = sum(1 for t in _WEAK_TOKS if t in text)
    if s > w:
        return "强"
    if w > s:
        return "弱"
    return "?"


def _engine_liuqin_section(liuqin_text: str, subject: str) -> str:
    """Pull the engine's 【<subject>】... section out of the liuqin narrative."""
    if not isinstance(liuqin_text, str) or not subject:
        return ""
    label = _LIUQIN_SECTION_LABEL.get(subject, "")
    if not label or label not in liuqin_text:
        return liuqin_text[:300]  # fallback: whole text snippet
    start = liuqin_text.index(label) + len(label)
    next_label = liuqin_text.find("【", start)
    return liuqin_text[start:next_label if next_label != -1 else len(liuqin_text)]


_SUBJ_FIELD_KEYS = {
    "father": ["father"], "mother": ["mother"], "spouse": ["spouse"],
    "child": ["son", "daughter"], "sibling": ["brother", "sister"],
}


def _field_strength(strength_field, subj: str) -> str:
    """Read the structured `liuqin_strength` echo for subj → 强/弱/?.

    Pure adoption signal: did the LLM copy the injected verdict into the
    dedicated field? Unaffected by prose keyword noise.
    """
    for key in _SUBJ_FIELD_KEYS.get(subj, []):
        val = (strength_field or {}).get(key)
        if isinstance(val, str):
            v = val.strip()
            if v and "弱" in v and "强" not in v:
                return "弱"
            if v and "强" in v and "弱" not in v:
                return "强"
    return "?"


def _liuqin_compare(master: str, engine_lq, strength_field=None) -> Dict:
    subj = _detect_liuqin_subject(master)
    if not subj:
        return {"subject": "", "compared": False}
    sec = _engine_liuqin_section(engine_lq or "", subj)
    m_dir = _strength_dir(_master_subject_section(master, subj))
    e_prose = _strength_dir(sec)                      # real reading (narrative)
    e_field = _field_strength(strength_field, subj)   # adoption echo (structured)
    subj_zh = {"father": "父亲", "spouse": "配偶", "mother": "母亲",
               "child": "子女", "sibling": "兄弟姐妹"}[subj]
    return {
        "subject": subj_zh,
        "compared": True,
        "master_strength": m_dir,
        "engine_strength": e_prose,       # headline: the prose the user reads
        "field_strength": e_field,        # diagnostic: did LLM echo injected verdict?
        "strength_match": (m_dir != "?" and e_prose != "?" and m_dir == e_prose),
        "field_match": (m_dir != "?" and e_field != "?" and m_dir == e_field),
        "engine_section": sec.strip()[:200],
    }


def _load_cases(limit: int) -> List[Dict]:
    recs = [json.loads(l) for l in CASES.open(encoding="utf-8") if l.strip()]
    out = []
    for r in recs:
        if r.get("gender") and r.get("bazi") and r.get("analysis_corrected"):
            out.append(r)
        if len(out) >= limit:
            break
    return out


async def _run_one(case: Dict, args) -> Dict:
    gender = case["gender"]
    if gender not in ("male", "female"):
        gender = "female" if gender in ("女",) else "male"
    try:
        result = await analyze_bazi(
            case["bazi"],
            gender=gender,
            cases_path=Path("bazi_knowledge/cases.jsonl"),
            knowledge_base_path=Path("bazi_knowledge/rule_primer.md"),
            extra_cases_paths=EXTRA_CASES,
            extra_knowledge_base_paths=EXTRA_KNOWLEDGE,
            api_key=args.api_key,
            base_url=args.base_url or "https://api.deepseek.com/v1",
            model=args.model,
        )
    except Exception as exc:  # noqa: BLE001
        return {"bazi": case["bazi"], "error": str(exc)}
    return {"bazi": case["bazi"], "gender": case["gender"], "result": result,
            "master": case["analysis_corrected"], "domains": case.get("domains", {})}


def _compare(rec: Dict) -> Dict:
    res = rec.get("result", {})
    master = rec.get("master", "")
    da = res.get("domain_analysis", {}) or {}
    eng_career = da.get("career", "") + da.get("wealth", "")
    eng_health = da.get("health", "")
    eng_wealth = res.get("wealth_level", "?")

    m_wealth = _bucket(master)
    e_wealth = _engine_wealth_bucket(eng_wealth)
    wealth_match = (m_wealth != "?" and e_wealth != "?" and m_wealth == e_wealth)

    m_career = _hits(master, _CAREER)
    e_career = _hits(eng_career, _CAREER)
    career_overlap = sorted(set(m_career) & set(e_career))

    m_health = _hits(master, _HEALTH)
    e_health = _hits(eng_health, _HEALTH)
    health_overlap = sorted(set(m_health) & set(e_health))

    return {
        "格局(engine)": (res.get("basic_info", {}) or {}).get("pattern", ""),
        "财富(engine)": eng_wealth,
        "财富(master_bucket)": m_wealth,
        "财富_match": wealth_match,
        "职业(master)": m_career,
        "职业(engine)": e_career,
        "职业_overlap": career_overlap,
        "健康(master)": m_health,
        "健康(engine)": e_health,
        "健康_overlap": health_overlap,
        "engine_health_text": eng_health[:160],
        "engine_career_text": eng_career[:160],
        "master_snippet": master[:200],
        "liuqin": _liuqin_compare(master, res.get("liuqin_analysis"),
                                 res.get("liuqin_strength") or {}),
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--output", default=None, help="Optional JSON output path")
    args = ap.parse_args()

    cases = _load_cases(args.limit)
    print(f"Validating {len(cases)} real cases on {args.model}...\n", file=sys.stderr)
    records = []
    for i, c in enumerate(cases, 1):
        rec = await _run_one(c, args)
        if "error" in rec:
            print(f"[{i}] {rec['bazi']} ERROR: {rec['error']}", file=sys.stderr)
            continue
        cmp = _compare(rec)
        records.append({**rec, "cmp": cmp})
        print(f"===== [{i}] {rec['bazi']} ({rec['gender']}) =====")
        print(f"  格局: {cmp['格局(engine)']}  |  财富 engine={cmp['财富(engine)']} master={cmp['财富(master_bucket)']} "
              f"→ {'✓' if cmp['财富_match'] else '✗'}")
        print(f"  职业 overlap: {cmp['职业_overlap'] or '—'}")
        print(f"    master职业象: {cmp['职业(master)']}")
        print(f"    engine职业象: {cmp['职业(engine)']}")
        print(f"  健康 overlap: {cmp['健康_overlap'] or '—'}")
        print(f"    engine健康: {cmp['engine_health_text']}")
        lq = cmp.get("liuqin", {})
        if lq.get("compared"):
            mark = "✓" if lq["strength_match"] else "✗"
            print(f"  六亲[{lq['subject']}] 强弱: master={lq['master_strength']} "
                  f"engine={lq['engine_strength']} field={lq.get('field_strength', '?')} → {mark}")
            print(f"    engine断: {lq['engine_section']}")
        else:
            print(f"  六亲: (master 未聚焦单一六亲，跳过自动比对)")
        print(f"  master原断(节选): {cmp['master_snippet']}")
        print()

    n = len(records)
    if not n:
        print("no records", file=sys.stderr); return
    wealth_rate = sum(1 for r in records if r["cmp"]["财富_match"]) / n
    career_rate = sum(1 for r in records if r["cmp"]["职业_overlap"]) / n
    health_rate = sum(1 for r in records if r["cmp"]["健康_overlap"]) / n
    lq_cases = [r for r in records if r["cmp"].get("liuqin", {}).get("compared")]
    lq_rate = (sum(1 for r in lq_cases if r["cmp"]["liuqin"]["strength_match"])
               / len(lq_cases)) if lq_cases else 0.0
    print(f"\n{'='*50}")
    print(f"结构层命中（n={n}，粗粒度）:")
    print(f"  财富方向一致: {wealth_rate:.0%}  (注意: 杨炎案例多断家人，命主财富常缺失→假阴性)")
    print(f"  职业象有交集: {career_rate:.0%}  (同上，多为家人职业)")
    print(f"  健康象有交集: {health_rate:.0%}  (健康指命主，较可信)")
    print(f"  六亲强弱一致: {lq_rate:.0%}  (n={len(lq_cases)}，apples-to-apples，最可信)")
    lq_field_rate = (sum(1 for r in lq_cases if r["cmp"]["liuqin"].get("field_match"))
                     / len(lq_cases)) if lq_cases else 0.0
    print(f"  六亲强弱(字段采纳): {lq_field_rate:.0%}  (LLM 逐字复述注入判定；应≈确定性层，高于prose则=采纳)")

    if args.output:
        Path(args.output).write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
