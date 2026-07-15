#!/usr/bin/env python3
"""Convert BaziQA questions into MingMirror cases.jsonl format.

Each BaziQA question becomes a case record with:
- bazi, day_master, month_branch extracted from the person profile
- source_video set to the BaziQA question_id
- analysis_corrected with Q/A, domain, structural facts, and a short reasoning skeleton
- key_terms, conclusions, domains, key_years for RAG retrieval

v2 (2026-07-13): richer structural tags so RAG can transfer by domain + 十神/旺衰
instead of only same-bazi sibling questions.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.bazi_ai import bazi_structural
from tools.bazi_ai.baziqa_eval import load_baziqa, person_to_bazi


def _detect_domain(question_text: str, options: List[str]) -> str:
    """Map a BaziQA question to a MingMirror domain."""
    text = question_text + " " + " ".join(options)
    keywords = {
        "marriage": ["结婚", "离婚", "婚姻", "配偶", "妻子", "丈夫", "感情", "桃花", "恋爱", "嫁", "娶"],
        "wealth": ["财", "富", "穷", "钱", "收入", "资产", "投资", "买房", "置业", "贫富"],
        "career": ["职业", "工作", "事业", "升职", "创业", "公司", "职位", "跳槽", "从事", "行业"],
        "health": ["病", "疾", "健康", "手术", "医院", "身体", "受伤", "骨折", "困扰"],
        "kinship": ["父", "母", "子", "女", "兄弟", "姐妹", "六亲", "家庭", "小孩", "子女"],
        "education": ["学历", "读书", "学业", "毕业", "学校", "大学", "文凭"],
    }
    scores = {domain: 0 for domain in keywords}
    for domain, kws in keywords.items():
        for kw in kws:
            if kw in text:
                scores[domain] += 1
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "general"


def _extract_years(text: str) -> List[int]:
    return sorted({int(y) for y in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text)})


def _structural_blurb(bazi: str, gender: str) -> str:
    """One-line structural summary for RAG text."""
    profile = bazi_structural.structural_profile(bazi) or {}
    strength = profile.get("strength", "")
    useful = profile.get("useful_gods") or []
    taboo = profile.get("taboo_gods") or []
    stem_ss = profile.get("stem_shishen") or {}
    flags = []
    for lab, ss in stem_ss.items():
        if lab == "日干":
            continue
        if ss in ("正官", "七杀", "正印", "偏印", "食神", "伤官", "正财", "偏财", "劫财", "比肩"):
            flags.append(f"{lab}{ss}")
    flag_txt = "、".join(flags[:6]) if flags else "—"
    return (
        f"结构：日主{profile.get('day_master', '')}，月令{profile.get('month_branch', '')}，"
        f"旺衰{strength}，用神{useful or '—'}，忌神{taboo or '—'}；十神透干：{flag_txt}"
    )


def _reasoning_skeleton(
    domain: str,
    profile: Dict[str, Any],
    answer_text: str,
    qtext: str,
) -> str:
    """Compact transfer-friendly reasoning (not full LLM CoT)."""
    strength = profile.get("strength", "中和")
    useful = profile.get("useful_gods") or []
    stem_ss = list((profile.get("stem_shishen") or {}).values())
    has = {
        "官杀": any(x in ("正官", "七杀") for x in stem_ss),
        "印": any(x in ("正印", "偏印") for x in stem_ss),
        "食伤": any(x in ("食神", "伤官") for x in stem_ss),
        "财": any(x in ("正财", "偏财") for x in stem_ss),
    }
    bits = [f"身{strength}"]
    if domain == "career":
        if has["官杀"] and has["印"]:
            bits.append("官印相生→公职/机构象")
        if has["食伤"] and has["财"]:
            bits.append("食伤生财→技艺/商贸象")
        elif has["食伤"]:
            bits.append("食伤泄秀→技术/自由象")
        if has["财"] and not has["官杀"]:
            bits.append("财显官弱→商业求财象")
    elif domain == "education":
        bits.append("印星有力→学历偏高" if has["印"] else "印弱→学历未必高")
    elif domain == "wealth":
        if strength == "偏旺" and has["财"]:
            bits.append("身旺有财→能任财")
        elif strength == "偏弱" and has["财"]:
            bits.append("身弱财重→难稳任")
        else:
            bits.append("看财星透根与日主能否担")
    elif domain == "health":
        bits.append(f"忌神{profile.get('taboo_gods') or '—'}对应脏腑优先")
    elif domain == "marriage":
        bits.append("看夫妻宫(日支)与配偶星清浊、冲合")
    elif domain == "kinship":
        bits.append("看对应六亲星宫是否受克/引动")
    if useful:
        bits.append(f"用神{useful}")
    bits.append(f"故取「{answer_text[:40]}」")
    return "；".join(bits)


def _build_analysis(
    person: Dict[str, Any],
    question: Dict[str, Any],
    domain: str,
    bazi: str,
    profile: Dict[str, Any],
) -> str:
    """Build a concise corrected analysis from a BaziQA Q&A + structure."""
    qtext = question.get("question", "")
    options = question.get("options", [])
    answer = question.get("answer", "")
    answer_idx = ord(answer.upper()) - ord("A") if answer else -1
    answer_text = options[answer_idx] if 0 <= answer_idx < len(options) else ""

    birth = person.get("profile", {}).get("birth", {})
    gender = person.get("profile", {}).get("gender", "")
    gender_label = "男" if gender == "male" else "女" if gender == "female" else ""

    lines = [
        f"命主：{person.get('name', '')}，{gender_label}命",
        f"八字：{bazi}",
        _structural_blurb(bazi, gender or "male"),
        f"出生：{birth.get('year')}年{birth.get('month')}月{birth.get('day')}日 "
        f"{birth.get('hour', 0)}:{birth.get('minute', 0):02d}",
        f"问题：{qtext}",
        "选项：",
    ]
    for i, opt in enumerate(options):
        mark = " ✓" if chr(ord("A") + i) == (answer or "").upper() else ""
        lines.append(f"  {chr(ord('A') + i)}. {opt}{mark}")
    lines.append(f"正确答案：{answer}. {answer_text}")
    lines.append(f"领域：{domain}")
    lines.append(f"推理要点：{_reasoning_skeleton(domain, profile, answer_text, qtext)}")
    return "\n".join(lines)


def convert(
    data_dir: Path,
    *,
    datasets: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Convert BaziQA questions to case records."""
    contest_records, celebrity_records = load_baziqa(data_dir)
    datasets = datasets or ["contest8", "celebrity50"]
    sources: List[tuple] = []
    if "contest8" in datasets:
        sources.append(("contest8", contest_records))
    if "celebrity50" in datasets:
        sources.append(("celebrity50", celebrity_records))

    cases: List[Dict[str, Any]] = []
    for dataset_name, records in sources:
        for person in records:
            bazi = person_to_bazi(person)
            if not bazi:
                continue
            parts = bazi.split()
            day_master = parts[2][0] if len(parts) == 4 else ""
            month_branch = parts[1][1] if len(parts) == 4 else ""
            gender = person.get("profile", {}).get("gender", "male")
            profile = bazi_structural.structural_profile(bazi) or {}

            for q in person.get("questions", []):
                domain = _detect_domain(q.get("question", ""), q.get("options", []))
                analysis = _build_analysis(person, q, domain, bazi, profile)
                options = q.get("options", [])
                answer = q.get("answer", "")
                answer_idx = ord(answer.upper()) - ord("A") if answer else -1
                answer_text = options[answer_idx] if 0 <= answer_idx < len(options) else ""
                years = _extract_years(q.get("question", "") + " " + " ".join(options))
                key_years = _extract_years(answer_text) or years[:1]

                case = {
                    "bazi": bazi,
                    "day_master": day_master,
                    "month_branch": month_branch,
                    "source_video": q.get("question_id", ""),
                    "analysis_raw": analysis,
                    "analysis_corrected": analysis,
                    "master_feedback": [],
                    "key_terms": [
                        q.get("question", "")[:24],
                        answer_text[:24],
                        domain,
                        profile.get("strength", ""),
                    ],
                    "conclusions": [
                        f"{q.get('question', '')} 答案：{answer}. {answer_text}",
                        _reasoning_skeleton(
                            domain, profile, answer_text, q.get("question", "")
                        ),
                    ],
                    "domains": {
                        domain: [answer_text] if answer_text else [q.get("question", "")[:40]]
                    },
                    "key_years": key_years,
                    "patterns": {
                        "strength": profile.get("strength"),
                        "useful_gods": profile.get("useful_gods"),
                        "taboo_gods": profile.get("taboo_gods"),
                    },
                    "dataset": dataset_name,
                }
                cases.append(case)

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert BaziQA to MingMirror cases")
    parser.add_argument("--data", default="benchmarks/baziqa/data", help="BaziQA data directory")
    parser.add_argument(
        "--output",
        default="bazi_knowledge/cases_baziqa.jsonl",
        help="Output cases file",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=["contest8", "celebrity50"],
        default=["contest8", "celebrity50"],
    )
    args = parser.parse_args()

    cases = convert(Path(args.data), datasets=args.datasets)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    from collections import Counter

    dom = Counter()
    ds = Counter()
    for c in cases:
        ds[c.get("dataset", "?")] += 1
        for d in (c.get("domains") or {}):
            dom[d] += 1
    print(f"Converted {len(cases)} BaziQA questions to {output}")
    print(f"  by dataset: {dict(ds)}")
    print(f"  by domain:  {dict(dom)}")


if __name__ == "__main__":
    main()
